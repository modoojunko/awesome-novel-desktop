"""卷域 AI（volume-plan-ai）：3 套可行走法 / 展开卷纲草稿 / 卷纲体检。

- 素材取自非章域单源（0 章书可用）：主线（story.yaml.story_arc 归一）、世界摘要（world_model）、
  核心人物（characters 表）、伏笔台账（prompt/context 台账块）、题材段（genres.service）、
  上一卷的结尾（resolve_prev_ending：事实优先——有归档章取实际收尾，否则取卷纲预期结局）。
- 三端点均不落库：产出为草稿/报告，由前端表单承接、走既有保存链；解析失败 502 可重试。
- 门禁：options/expand 归 PRO（require_ai_access）；check 免费（只读例外：不挂 require_ai_access，
  仍挂 require_novel_model——没配模型给 503，前端引导先接模型）。
- 记账：每次尝试（含失败）走 record_usage，operation 名 volume_options/_fail 等。
- 模型：`haiku` 符号别名（落到本书模型，与章纲起草同口径）；max_tokens 4096
  （判定类先例：2048 偶发「无文本输出」，见 settings/ai_router.py 注释）。
"""

import difflib
import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import ai_feature, require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from chapters.schemas import clip_sentence
from db import get_db
from filesystem.storage import get_storage
from genres.service import build_genre_section, resolve_genre_context
from novels.events import log_event_async
from novels.router import _arc_normalize
from novels.service import get_novel
from prompt.context import load_active_hooks, render_hooks_block
from prompts import load as load_prompt
from prompts import load_layers
from repositories import volume_repo
from settings import character_service
from settings.world_model import render_red_lines, world_summary_text
from volumes.render import volume_outline_text
from volumes.service import resolve_prev_ending

logger = logging.getLogger("uvicorn.error")  # 同 volumes/service.py 口径
router = APIRouter(prefix="/api/novels/{project_id}/volumes", tags=["volumes"])

_MODEL = "haiku"  # 符号别名，落到本书模型（D12；与章纲起草同口径）
_MAX_TOKENS = 4096  # 判定类先例：2048 偶发「无文本输出」（settings/ai_router.py 注释）
SPINE_SIM_LIMIT = 0.6  # 两套走向相似度超过此值视为同质（触发一次复核）
FOCUS_AXES = ("代价", "关系", "认知", "节奏", "势力", "线索")
MAX_PLANS = 3
LINE_MAX = 150


async def _generate(
    project, system: str, user_msg: str, *, temperature: float, db, user, operation: str,
    max_tokens: int = _MAX_TOKENS,
) -> tuple[str, dict]:
    """单次生成 ＋ 失败重试一次（把失败原因喂回）＋ 全程计量（含失败留痕）。

    max_tokens：默认 4096 不动；单次多版产物的端点自己抬（c-plot-split 三版剧情 8192）。
    """
    client = await get_ai_client_for_novel(project.id)
    usage: dict = {}
    try:
        raw = await client.chat(
            model=_MODEL, system=system, messages=[{"role": "user", "content": user_msg}],
            max_tokens=max_tokens, temperature=temperature, usage=usage,
            operation=operation,
        )
    except AITimeoutError:
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=user["id"], project_id=project.id, operation=f"{operation}_fail",
            model=effective_model(project) or _MODEL,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0), force=True,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001 — 模型/网络错误：留痕后可重试
        from api_configs.usage import record_usage

        await record_usage(
            db, user_id=user["id"], project_id=project.id, operation=f"{operation}_fail",
            model=effective_model(project) or _MODEL,
            tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0), force=True,
        )
        raise HTTPException(502, f"AI 调用失败，可重试：{e!s}") from e

    from api_configs.usage import record_usage

    await record_usage(
        db, user_id=user["id"], project_id=project.id, operation=operation,
        model=effective_model(project) or _MODEL,
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
    )
    if raw.strip():
        return raw, usage

    # 空 text 块（偶发：预算全用在思考/供应商只回 thinking）——照 _judge_chat 口径重试一次
    retry: dict = {}
    raw2 = await client.chat(
        model=_MODEL, system=system,
        messages=[
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": "（上一条没有输出正文）"},
            {"role": "user", "content": "请输出正文。"},
        ],
        max_tokens=max_tokens, temperature=min(temperature, 0.2), usage=retry,
    )
    from api_configs.usage import record_usage

    await record_usage(
        db, user_id=user["id"], project_id=project.id, operation=f"{operation}_retry",
        model=effective_model(project) or _MODEL,
        tokens_in=retry.get("tokens_in", 0), tokens_out=retry.get("tokens_out", 0),
    )
    return raw2, usage


class ExcludeItem(BaseModel):
    """重抽排除项（c-plan-draw-exclude）：已出批的轴＋一句话。请求携带，SHALL NOT 落库。"""

    axis: str = Field(default="", max_length=20)
    line: str = Field(default="", max_length=40)


class PlanLineBody(BaseModel):
    """抽卡/四问约束（可空——空则 AI 自由推）。作家已答的照抄不改写。

    `vol_no` ＝本次规划的目标卷号（c-vol-options-prev-ending）：上一卷结尾按它解析，
    缺省＝下一卷（与 ExpandBody 同构；老客户端回落，重规划已有卷须显式带）。
    """

    line: str = Field(default="", max_length=LINE_MAX)
    conflict: str = Field(default="", max_length=150)
    antagonist_type: str = Field(default="", max_length=20)
    antagonist_line: str = Field(default="", max_length=150)
    ending: str = Field(default="", max_length=300)
    exclude: list[ExcludeItem] = Field(default_factory=list, max_length=9)
    vol_no: int | None = Field(default=None, ge=1, le=99)


def _exclude_block(exclude: list[tuple[str, str]]) -> str:
    """重抽禁令块（D21）：中性措辞（不贴负面评判标签，防模型过度纠偏）。

    服务端拼进素材串（<<material_blocks>> 吸纳），SHALL NOT 改模板——对拍三件套不受影响。
    """
    if not exclude:
        return ""
    lines = [f"- {a}｜{l}" for a, l in exclude]
    return (
        "\n\n【已出过的方向（作者已否决）】\n" + "\n".join(lines)
        + "\n重抽时给出结构上不同的新方向：同轴也可以，但走向一句话不得与上面雷同。"
    )


class ExpandBody(BaseModel):
    """展开：作者那一句（或选中的走法）→ 卷纲草稿。`vol_no` 缺省＝下一卷。

    line 放行空串（422 由端点给人类可读提示，不走 Pydantic 默认报文）。
    """

    line: str = Field(default="", max_length=LINE_MAX)
    conflict: str = Field(default="", max_length=150)
    antagonist_type: str = Field(default="", max_length=20)
    antagonist_line: str = Field(default="", max_length=150)
    ending: str = Field(default="", max_length=300)
    vol_no: int | None = Field(default=None, ge=1, le=99)


# ═══════════════ 素材（非章域单源；0 章书可用）═══════════════


def _rules_sections() -> tuple[str, str]:
    """八条硬规则与体检判据的文本单源（spec：两个模板用占位符引用，配逐字对拍测试）。"""
    src = load_prompt("volume_rules")
    i = src.find("【体检判据】")
    if i < 0:
        return src.strip(), ""
    return src[:i].strip(), src[i:].strip()


def load_fragment(name: str) -> str:
    """节奏片段加载（c-plan-pacing-rules）：剥掉文件头 `## ` 版本注释行（changelog 用，不入模型提示词）。

    无片段场景由调用方不注入（占位符渲染为空串、连标题不留——spec 口径）。
    """
    lines = load_prompt(name).splitlines()
    i = 0
    while i < len(lines) and lines[i].lstrip().startswith("##"):
        i += 1
    return "\n".join(lines[i:]).strip()


def _faction_names(world_raw: dict) -> list[str]:
    """世界设定里已命名的势力名（实体集合差的已知侧）。"""
    out: list[str] = []
    for f in world_raw.get("factions") or []:
        if isinstance(f, dict):
            n = str(f.get("name") or "").strip()
            if n:
                out.append(n)
    return out


async def _closed_hooks_summary(novel_id: str) -> str:
    """已收/已弃伏笔各一条摘要——体检判「漏收/提前揭」需台账全貌，只看 active 不够。"""
    if not novel_id:
        return ""
    from db import async_session
    from models.hook import NovelHook

    async with async_session() as session:
        rows = (
            await session.scalars(
                select(NovelHook).where(
                    NovelHook.novel_id == novel_id,
                    NovelHook.status.in_(["resolved", "abandoned"]),
                )
            )
        ).all()
    lines: list[str] = []
    for status, label in (("resolved", "已收"), ("abandoned", "已弃")):
        row = next((r for r in rows if r.status == status), None)
        if row is not None:
            lines.append(f"- {label}：[H-{row.seq:04d}] {row.description[:60]}")
    return "\n".join(lines)


async def _cardless_cast_rows(
    db: AsyncSession, project_id: str, carded: set[str], volume_id: str | None = None
) -> list[dict]:
    """已拆章出场名单中的无卡名字（派生块，零新存储；剔旧稿支线，与 `_aggregate_cast` 同口径）。

    `carded`＝角色表名字＋别名（命中即有卡）；`volume_id` 限本卷（拆章用），None＝全书（拆卷用）。
    """
    from models.chapter import Chapter, ChapterCharacter
    from models.volume import Volume

    stmt = (
        select(Volume.volume_no, Chapter.chapter_no, ChapterCharacter.character_name)
        .join(Chapter, Chapter.id == ChapterCharacter.chapter_id)
        .join(Volume, Volume.id == Chapter.volume_id)
        .where(Chapter.project_id == project_id, Chapter.ghost_of.is_(None))
        .order_by(Volume.volume_no, Chapter.chapter_no, ChapterCharacter.sort_order)
    )
    if volume_id is not None:
        stmt = stmt.where(Chapter.volume_id == volume_id)
    rows = (await db.execute(stmt)).all()
    seen: dict[str, list[str]] = {}
    for _vol_no, chapter_no, raw_name in rows:
        nm = (raw_name or "").strip()
        if not nm or nm in carded:
            continue
        seen.setdefault(nm, []).append(str(chapter_no))
    return [{"name": nm, "chapters": chs} for nm, chs in seen.items()]


def _cardless_brief(rows: list[dict]) -> str:
    out = []
    for r in rows:
        chs = r["chapters"]
        tail = f"…等{len(chs)}章" if len(chs) > 6 else ""
        out.append(f"- {r['name']}（第{'、'.join(chs[:6])}章{tail}）")
    return "\n".join(out)


async def _book_material(
    db, project, *, with_hooks: bool, author_line: str = "", exclude_vol_no: int | None = None
) -> dict:
    """主线（arc 归一）＋世界块（全量）＋核心人物全名单＋已拆卷清单＋无卡出场名单＋伏笔台账＋题材段。

    人物口径（c-plan-material-fullinfo）：全名单一行卡，主角置顶，不设数量上限（6 张×80 与聚光单换位已退役）。
    另带 known_entities（角色 name+aliases＋势力名＋出场名单无卡名字）供模型申报实体的集合差。
    `exclude_vol_no`：已拆卷清单排除该卷（expand 展开目标卷自身时用）。
    """
    storage = get_storage()
    story = await storage.read_yaml(project.root_path, "story.yaml") or {}
    arc = _arc_normalize(story.get("story_arc") or {})
    world_raw = await storage.read_yaml(project.root_path, "settings/world-setting.yaml") or {}
    gctx = await resolve_genre_context(project.root_path, project.id)
    chars = await character_service.list_characters(db, project.id)
    items = list(chars.get("items", []))
    items.sort(key=lambda it: 0 if it.get("role") == "主角" else 1)

    known: set[str] = set(_faction_names(world_raw))
    card_names: set[str] = set()
    for it in items:
        nm = str(it.get("name") or "").strip()
        if nm:
            known.add(nm)
            card_names.add(nm)
        for a in it.get("aliases") or []:
            na = str(a).strip()
            if na:
                known.add(na)
                card_names.add(na)

    cast_brief = "\n".join(
        f"- {it.get('name', '')}（{it.get('role', '')}）：{(it.get('persona') or '')[:80]}"
        for it in items
    )

    vols = await volume_repo.list_by_project(db, project.id)
    vols.sort(key=lambda v: v.volume_no)
    vol_lines: list[str] = []
    for v in vols:
        if exclude_vol_no is not None and v.volume_no == exclude_vol_no:
            continue
        ant = (
            (v.antagonist_type or "")
            + ("·" if v.antagonist_type and v.antagonist_line else "")
            + (v.antagonist_line or "")
        ).strip()
        line = f"卷{v.volume_no}·{v.title}｜{v.summary or ''}"
        if ant:
            line += f"｜坎：{ant}"
        if v.ending:
            line += f"｜卷末：{v.ending or ''}"
        vol_lines.append(line)

    cardless_rows = await _cardless_cast_rows(db, project.id, card_names)
    known |= {r["name"] for r in cardless_rows}

    hooks_view = await load_active_hooks(project.id)
    return {
        "fullstory": arc["fullstory"],
        "ending": arc["ending"],
        "world_brief": world_summary_text(world_raw, None),
        # c-ai-material-audit：v2 契约下 constraints 是 list[dict]，旧写法 isinstance(str) 恒假
        # → 拆章 ⑦【世界铁律】永不渲染、卷体检恒印假话「未登记铁律」。走红线单源同口径。
        "world_rules": "\n".join(render_red_lines(world_raw)),
        "cast_brief": cast_brief,
        "card_names": card_names,
        "volumes_brief": "\n".join(vol_lines),
        "cardless_brief": _cardless_brief(cardless_rows),
        "hooks_block": render_hooks_block(hooks_view),
        "closed_hooks": await _closed_hooks_summary(project.id),
        "genre_section": build_genre_section(gctx),
        "genre_name": (gctx or {}).get("genre_id") or "",
        "genre_theme": f"{(gctx or {}).get('theme', '')}{(gctx or {}).get('sub_genre', '')}",
        "known_entities": known,
    }


# boss 台阶默认提示（FR-11）：只对「阶段性大敌是类型期待」的题材追加。
# 落点在本模块的卷体检素材里——不动 `build_genre_section` 共享单源，
# 因此写章链 system 不含这条（题材段是同一份）。
_BOSS_STEP_GENRE_HINTS = ("玄幻", "奇幻", "仙侠", "都市")


def _boss_step_hint(genre_theme: str) -> str:
    if not any(k in (genre_theme or "") for k in _BOSS_STEP_GENRE_HINTS):
        return ""
    return (
        "题材提示（玄幻/都市系）：本卷若按题材期待有阶段性大敌（BOSS／台阶），"
        "请在「对主线」组判它是否在卷末有了结、与上一卷是否递进；题材无此期待则跳过。"
    )


def _blocks(mat: dict, *, hooks: bool) -> str:
    parts = [f"【全书主线】\n{mat['fullstory']}"]
    e = mat["ending"]
    parts.append(
        "【结局（作者写的）】最后一幕：{s}｜主角变成：{h}｜读者感觉：{t}".format(
            s=e.get("scene", ""), h=e.get("hero", ""), t=e.get("tone", "")
        )
    )
    if mat["world_brief"]:
        parts.append(f"【世界观摘要】\n{mat['world_brief']}")
    if mat["cast_brief"]:
        parts.append(f"【核心人物】\n{mat['cast_brief']}")
    if mat.get("volumes_brief"):
        parts.append(f"【已拆卷】\n{mat['volumes_brief']}")
    if mat.get("cardless_brief"):
        parts.append(f"【无卡出场名单】\n{mat['cardless_brief']}")
    if hooks and (mat["hooks_block"] or mat["closed_hooks"]):
        active = mat["hooks_block"] or "（还没有悬而未决的伏笔）"
        closed = "\n" + mat["closed_hooks"] if mat["closed_hooks"] else ""
        parts.append(f"【伏笔台账】\n{active}{closed}")
    if mat["genre_section"]:
        parts.append(f"【题材与节奏】\n{mat['genre_section']}")
    return "\n\n".join(parts)


# ═══════════════ JSON 解析与校验兜底 ═══════════════


def _render(tpl: str, **vals) -> str:
    """<<key>> 占位符替换（不用 str.format——模板里的 JSON 示例带花括号）。"""
    out = tpl
    for k, v in vals.items():
        out = out.replace("<<" + k + ">>", str(v))
    return out


def _parse_json(raw: str) -> dict | None:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    i, k = text.find("{"), text.rfind("}")
    if i < 0 or k <= i:
        return None
    try:
        obj = json.loads(text[i : k + 1])
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _lines(v, cap: int) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip()[:120] for x in v if str(x).strip()][:cap]


# ═══════════════ 3 套可行走法 ═══════════════


def _entity_warnings(
    declared_cast, declared_factions, known: set[str], declared_places=None
) -> list[str]:
    """模型申报实体 vs 已知集合（角色 name+aliases＋势力名[＋地点]）做差——差集非空才标记，不拦。

    地点为可选第三类（c-chapter-plan-ai 章级对拍扩项；卷级调用不传＝行为不变）。
    """
    warnings: list[str] = []
    pairs = [("人物", declared_cast), ("势力", declared_factions)]
    if declared_places is not None:
        pairs.append(("地点", declared_places))
    for kind, vals in pairs:
        for n in vals if isinstance(vals, list) else []:
            ns = str(n).strip()
            if ns and ns not in known:
                warnings.append(f"设定里没有这个{kind}：「{ns[:20]}」")
    return warnings[:5]


def _degrade_text(raw: str) -> str:
    return (raw or "").strip()[:2000]


async def _last_chapter_tail(root_path: str, chapter_ref: str) -> str:
    """末章正文末段（≤200 字）——体检「已写内容」对照用；读不到就空串，不拦。"""
    if not chapter_ref:
        return ""
    try:
        from workflow.engine import load_chapter

        ch = await load_chapter(root_path, chapter_ref) or {}
        paras = [
            ln.strip()
            for ln in str(ch.get("content") or "").split("\n")
            if ln.strip()
        ]
        return paras[-1][:200] if paras else ""
    except Exception:  # noqa: BLE001 — 素材补强失败不挡体检
        return ""


def _sanitize_plans(parsed: dict | None) -> dict | None:
    """逐套兜底：走向/卷末齐 + 侧重轴互不相同（同质的那套丢弃）；<2 套视为整体失败。

    出参带 note／volume_estimate 透传与 cast／factions 申报（供实体集合差）。
    """
    if not isinstance(parsed, dict):
        return None
    plans_raw = parsed.get("plans")
    if not isinstance(plans_raw, list):
        return None
    axes: list[str] = []
    out: list[dict] = []
    for p in plans_raw:
        if not isinstance(p, dict):
            continue
        spine = str(p.get("spine", "") or "").strip()
        conflict = str(p.get("conflict", "") or "").strip()
        ending = str(p.get("ending", "") or "").strip()
        if not spine or not ending:
            continue
        axis = str(p.get("focus_axis", "") or "").strip()
        if axis not in FOCUS_AXES:
            # 闭集（FR-2）：模型给的自造轴不收——落到本组未用过的下一个闭集值
            axis = next(
                (a for a in FOCUS_AXES if a not in axes),
                FOCUS_AXES[len(axes) % len(FOCUS_AXES)],
            )
        if axis in axes:
            continue  # 同轴＝同质，丢弃
        axes.append(axis)
        p_ant_type = str(p.get("antagonist_type", "") or "").strip()
        if p_ant_type not in ("人物", "难题", "环境", "自我", "势力"):
            p_ant_type = "人物" if p_ant_type else ""
        out.append(
            {
                "no": len(out) + 1,
                # 钳位＝提示词字段上限（对齐——上限说明不该被更宽的兜底架空）
                "spine": clip_sentence(spine, 40),
                "conflict": clip_sentence(conflict, 150),
                "ending": clip_sentence(ending, 300),
                "focus": str(p.get("focus", "") or "").strip()[:20],
                "focus_axis": axis,
                "antagonist_type": p_ant_type,
                "antagonist_line": str(p.get("antagonist_line", "") or "").strip()[:150],
            }
        )
        if len(out) == MAX_PLANS:
            break
    if len(out) < 2:
        return None
    return {
        "plans": out,
        "note": str(parsed.get("note", "") or "").strip()[:120],
        "volume_estimate": str(parsed.get("volume_estimate", "") or "").strip()[:20],
        "cast": [str(x).strip() for x in parsed.get("cast") or [] if str(x).strip()],
        "factions": [str(x).strip() for x in parsed.get("factions") or [] if str(x).strip()],
    }


def _antagonist_candidates(plans: list[dict]) -> list[str]:
    """从「这一卷的坎」取候选实体名（只取人物/势力型）。

    prompt 约定线形「名字——一句话」；取首个分隔段作名字，无分隔符时取前 12 字
    （够命中「执法官雷」这类短名）。名字不在设定里 → 由 _entity_warnings 提示。
    """
    names: list[str] = []
    for p in plans:
        if p.get("antagonist_type") not in ("人物", "势力"):
            continue
        line = str(p.get("antagonist_line") or "").strip()
        if not line:
            continue
        head = re.split(r"[——·，,、：:\s（(]", line, maxsplit=1)[0].strip()
        if head:
            names.append(head[:12])
    return names


def _plans_too_similar(plans: list[dict]) -> bool:
    spines = [p["spine"] for p in plans]
    for i, a in enumerate(spines):
        for b in spines[i + 1 :]:
            if difflib.SequenceMatcher(None, a, b).ratio() > SPINE_SIM_LIMIT:
                return True
    return False


def _drop_excluded_plans(plans: list[dict], exclude: list[tuple[str, str]]) -> list[dict]:
    """排除对拍（D21）：**同轴且走向相似**才判撞车——短串 difflib 噪声大，单凭相似会误杀。"""
    out: list[dict] = []
    for p in plans:
        clash = any(
            e_a == p.get("focus_axis")
            and difflib.SequenceMatcher(None, p.get("spine", ""), e_l).ratio() >= SPINE_SIM_LIMIT
            for e_a, e_l in exclude
        )
        if not clash:
            out.append(p)
    return out


@router.post("/ai/options")
@ai_feature("ai-plan")
async def ai_volume_options(
    project_id: str,
    body: PlanLineBody,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """3 套本卷可行走法（不落库）。三套都忠于全书设定与上一卷结尾，差异只在走向/冲突/侧重。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    author_line = (body.line or "").strip()
    mat = await _book_material(db, project, with_hooks=False, author_line=author_line)
    if not mat["fullstory"] and not any(mat["ending"].values()):
        raise HTTPException(422, "主线为空，请先在设定中完成主线（全景或结局三问）再拆卷")
    # 四问已答约束（作家答过的不被改写）：并入 author_line 素材位
    answered_extra = "／".join(filter(None, [
        body.conflict.strip(),
        ((body.antagonist_type + "·" + body.antagonist_line.strip()).strip("·")) if (body.antagonist_type or body.antagonist_line.strip()) else "",
        body.ending.strip(),
    ]))
    if answered_extra:
        author_line = (author_line + "｜已答：" + answered_extra) if author_line else ("已答：" + answered_extra)

    # 重抽排除（D21）：已出批的轴＋走向；中性禁令入素材，服务端对拍丢撞车套
    exclude = [(i.axis.strip(), i.line.strip()) for i in body.exclude if i.axis.strip() and i.line.strip()][:9]

    # 目标卷号：显式（前端规划流既定卷号）→ 缺省＝下一卷；上一卷结尾按它解析（事实优先）
    target_vol_no = body.vol_no or (await _next_volume_no(db, project))
    if not body.vol_no:
        logger.info("volume options: vol_no absent, resolved target=%s (project %s)", target_vol_no, project.id)
    prev = await resolve_prev_ending(db, project, target_vol_no)
    _sys_t, _usr_t = load_layers("volume_options")
    system = _render(_sys_t, focus_axes="／".join(FOCUS_AXES))
    _user = _render(
        _usr_t,
        material_blocks=_blocks(mat, hooks=False) + _exclude_block(exclude),
        prev_ending=prev["text"] + "（" + prev["source"] + "）",
        author_line=author_line or "（作者还没写——三套都要是你按设定推出的可行走法）",
    )
    raw, _u0 = await _generate(
        project, system, _user,
        temperature=0.7, db=db, user=user, operation="volume_options",
    )
    result = _sanitize_plans(_parse_json(raw))
    excluded_dropped = 0
    if exclude and result is not None:
        before = len(result["plans"])
        result["plans"] = _drop_excluded_plans(result["plans"], exclude)
        excluded_dropped = before - len(result["plans"])
    too_similar = result is not None and _plans_too_similar(result["plans"])
    below_min = result is not None and exclude != [] and len(result["plans"]) < 2
    need_retry = result is None or too_similar or below_min
    if need_retry:
        if result is None:
            reason = "不足两套或不合法"
            retry_temp = 0.3
        elif too_similar:
            reason = "有几套走向太像——请重写成结构上不同的版本"
            retry_temp = 0.3
        else:
            # 排除触发（D21）：求差异，SHALL NOT 降温——降温是保合法率的手段，与此相悖
            reason = "有的套与已出过的方向雷同——请换结构上不同的版本"
            retry_temp = 0.7
        retry_raw, _u1 = await _generate(
            project,
            system + f"\n\n（上一次{reason}。）",
            _user,
            temperature=retry_temp, db=db, user=user, operation="volume_options_retry",
        )
        retry_result = _sanitize_plans(_parse_json(retry_raw))
        if exclude and retry_result is not None:
            retry_result["plans"] = _drop_excluded_plans(retry_result["plans"], exclude)
        if retry_result is not None:
            result = retry_result
    if result is None:
        # spec：校验两次仍失败 → 降级为纯文本（不 502），提示可重试
        return {
            "ok": True, "degraded": True, "text": _degrade_text(raw),
            "hint": "AI 的输出没法结构化——可重试，或按上面这段手动定走向",
        }
    if excluded_dropped:
        # 作者可见（对齐章级丢卡提示）：静默少卡会让作者以为模型只会出两套
        tail = f"另有 {excluded_dropped} 套与已出方向雷同被剔除"
        result["note"] = ((result["note"] + "｜") if result["note"] else "") + tail
        result["note"] = result["note"][:120]
    # 实体差集：模型申报的 cast ＋ 坎（人物/势力型）点到的名字 ＋ factions（tasks 2.1 口径）
    warnings = _entity_warnings(
        _antagonist_candidates(result["plans"]) + result["cast"],
        result["factions"],
        mat["known_entities"],
    )
    return {
        "ok": True,
        "plans": result["plans"],
        "note": result["note"],
        "volume_estimate": result["volume_estimate"],
        "similar": _plans_too_similar(result["plans"]),
        "warnings": warnings,
    }


# ═══════════════ 展开卷纲草稿 ═══════════════


def _sanitize_expand(obj: dict | None) -> dict | None:
    """卷纲草稿兜底：四问必须齐（c-volume-antagonist 上限：主旨 80／冲突 60／卷末 60）。

    cast/factions 申报不入 draft，由端点提出到顶层做实体集合差；
    `goal`（整体目标）随字段瘦身退役——卷表停读停写，草稿也不再产出。
    """
    if not isinstance(obj, dict):
        return None
    summary = str(obj.get("summary", "") or "").strip()
    conflict = str(obj.get("conflict", "") or "").strip()
    ending = str(obj.get("ending", "") or "").strip()
    if not summary or not conflict or not ending:
        return None  # 四问必须齐——缺一件宁可重试/降级
    try:
        total = int(obj.get("chapter_target"))
    except (TypeError, ValueError):
        total = 0
    checks = [str(x).strip()[:40] for x in obj.get("checks", []) if str(x).strip()]
    ant_type = str(obj.get("antagonist_type", "") or "").strip()
    if ant_type not in ("人物", "难题", "环境", "自我", "势力"):
        ant_type = "人物" if ant_type else ""
    return {
        "name": str(obj.get("name", "") or "").strip()[:6],
        "summary": clip_sentence(summary, 150),
        "conflict": clip_sentence(conflict, 150),
        "ending": clip_sentence(ending, 300),
        "antagonist_type": ant_type,
        "antagonist_line": str(obj.get("antagonist_line", "") or "").strip()[:150],
        "plants": _lines(obj.get("plants"), 2),
        "reveals": _lines(obj.get("reveals"), 2),
        "chapter_target": min(9999, max(0, total)),
        "checks": checks[:3],
        "cast": [str(x).strip() for x in obj.get("cast") or [] if str(x).strip()],
        "factions": [str(x).strip() for x in obj.get("factions") or [] if str(x).strip()],
    }


async def _next_volume_no(db, project) -> int:
    return await volume_repo.max_volume_no(db, project.id) + 1


@router.post("/ai/expand")
@ai_feature("ai-plan")
async def ai_volume_expand(
    project_id: str,
    body: ExpandBody,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """把作者那一句（或选中的走法）铺成本卷卷纲草稿（不落库，前端表单承接）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    line = (body.line or "").strip()
    if not line:
        raise HTTPException(422, "先写一句这一卷想看什么——走向由你定，AI 只铺结构")
    vol_no = body.vol_no or (await _next_volume_no(db, project))
    prev = await resolve_prev_ending(db, project, vol_no)
    answered_extra = "／".join(filter(None, [
        body.conflict.strip(),
        ((body.antagonist_type + "·" + body.antagonist_line.strip()).strip("·")) if (body.antagonist_type or body.antagonist_line.strip()) else "",
        body.ending.strip(),
    ]))
    mat = await _book_material(
        db, project, with_hooks=True,
        author_line=(line + ("｜已答：" + answered_extra if answered_extra else "")),
        exclude_vol_no=vol_no,
    )
    # spec 素材契约：expand 含上一卷卷纲文本（options 不含）
    prev_vol_row = (
        await volume_repo.get_by_volume_no(db, project.id, vol_no - 1)
        if vol_no > 1
        else None
    )
    prev_outline = volume_outline_text(prev_vol_row) if prev_vol_row is not None else ""
    material_blocks = _blocks(mat, hooks=True)
    if prev_outline:
        material_blocks += f"\n\n【上一卷卷纲】\n{prev_outline}"

    _sys_t, _usr_t = load_layers("volume_expand")
    system = _render(
        _sys_t,
        hard_rules=_rules_sections()[0],
        # 首卷位置片段（c-plan-pacing-rules）：只进 expand（options 保三套互斥，节奏由 expand 统一执行）；
        # 独立占位符不拼进 hard_rules——保 rules 单源＋锚点切分＋对拍测试三件套
        volume_pos_rules=load_fragment("volume_pos_first") if vol_no == 1 else "",
    )
    _user = _render(
        _usr_t,
        material_blocks=material_blocks,
        prev_ending=prev["text"] + "（" + prev["source"] + "）",
        author_line=line,
    )
    raw, _u0 = await _generate(
        project, system, _user,
        temperature=0.4, db=db, user=user, operation="volume_expand",
    )
    draft = _sanitize_expand(_parse_json(raw))
    if draft is None:
        retry_raw, _u1 = await _generate(
            project,
            system + "\n\n（上一次输出不是合法 JSON 或四字段不齐——请只输出 JSON，四字段必须齐全。）",
            "请把这句话铺成这一卷的卷纲（只输出 JSON）。", temperature=0.2,
            db=db, user=user, operation="volume_expand_retry",
        )
        draft = _sanitize_expand(_parse_json(retry_raw))
        raw = retry_raw
    if draft is None:
        # spec：校验两次仍失败 → 降级为纯文本（不 502），提示可重试
        return {
            "ok": True, "vol_no": vol_no,
            "degraded": True, "text": _degrade_text(raw),
            "hint": "AI 的输出没法结构化——可重试，或按上面这段手动填卷纲",
        }
    # 卡面四问胜出（评审拍板：expand 只补空缺，不覆盖带入值）
    if body.conflict.strip():
        draft["conflict"] = body.conflict.strip()[:60]
    if body.antagonist_line.strip():
        draft["antagonist_type"] = body.antagonist_type or "人物"
        draft["antagonist_line"] = body.antagonist_line.strip()[:150]
    if body.ending.strip():
        draft["ending"] = body.ending.strip()[:60]
    warnings = _entity_warnings(draft.pop("cast", []), draft.pop("factions", []), mat["known_entities"])
    return {"ok": True, "vol_no": vol_no, "draft": draft, "warnings": warnings}


# ═══════════════ 卷纲体检（验证）═══════════════


def _report_groups(groups) -> list[dict] | None:
    if not isinstance(groups, list) or not groups:
        return None
    out: list[dict] = []
    for g in groups:
        if not isinstance(g, dict):
            continue
        name = str(g.get("name", "") or "").strip()
        items = []
        for it in g.get("items", []) if isinstance(g.get("items"), list) else []:
            if not isinstance(it, dict):
                continue
            status = it.get("status")
            text = str(it.get("text", "") or "").strip()
            if status in ("ok", "warn", "none") and text:
                item: dict = {"status": status, "text": text[:60]}
                ev = str(it.get("evidence", "") or "").strip()
                if ev:
                    item["evidence"] = ev[:30]
                items.append(item)
        if not name or not items:
            return None
        out.append({"name": name, "items": items})
    return out if len(out) >= 2 else None


def _count_warn(report: list[dict]) -> int:
    """体检报告里 warn 判据条数（度量 check_run{warn}）。"""
    return sum(
        1 for g in report for it in g.get("items", []) if it.get("status") == "warn"
    )


@router.post("/{ref}/ai/check")
@ai_feature("ai-plan")
async def ai_volume_check(
    project_id: str,
    ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),  # 只读体检归标准档（原免费例外随四档退役）
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """卷级验证：对主线／对设定／对节奏／对已写内容（只读、不拦、不代笔；过档位门后可重复）。"""
    from volumes.service import get_volume

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol_no = int(ref.removeprefix("vol-").split("-")[0])
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")
    detail = await get_volume(db, project, ref)
    prev = await resolve_prev_ending(db, project, vol_no)
    mat = await _book_material(db, project, with_hooks=True)

    outline_text = volume_outline_text(vol)
    written_brief = "（还没有章节——写到之后，这里换成实际写出来的对照）"
    chapters = detail.get("chapters") or []
    archived = [c for c in chapters if c.get("archived")]
    if archived:
        last = archived[-1]
        # spec：P1 只取该卷末章的摘要与末段，SHALL NOT 整卷正文入包
        tail = await _last_chapter_tail(project.root_path, str(last.get("ref") or ""))
        written_brief = (
            f"已写到第{last['chapter_no']}章「{last['title']}」｜{last.get('outline_summary') or '（无章纲）'}"
            + (f"\n末段：{tail}" if tail else "")
        )
    else:
        tail = ""

    prev_vol_row = (
        await volume_repo.get_by_volume_no(db, project.id, vol_no - 1)
        if vol_no > 1 else None
    )
    ant_pair = "上一卷的坎：" + (
        ((prev_vol_row.antagonist_type or "") + "·" + (prev_vol_row.antagonist_line or "")).strip("·")
        if prev_vol_row is not None and (prev_vol_row.antagonist_type or prev_vol_row.antagonist_line)
        else "（无记录）"
    ) + "｜本卷的坎：" + (
        ((vol.antagonist_type or "") + "·" + (vol.antagonist_line or "")).strip("·")
        if (vol.antagonist_type or vol.antagonist_line) else "（未填——判据输出 warn，不编造）"
    )
    boss_hint = _boss_step_hint(mat.get("genre_theme", ""))
    _sys_t, _usr_t = load_layers("volume_check")
    system = _render(_sys_t, criteria=_rules_sections()[1])
    _user = _render(
        _usr_t,
        vol_outline=outline_text + "\n上一卷与本卷的坎：" + ant_pair
        + (("\n" + boss_hint) if boss_hint else ""),
        fullstory=mat["fullstory"],
        world=mat["world_brief"] or "（世界设定还空着）",
        scene=mat["ending"].get("scene", ""),
        hero=mat["ending"].get("hero", ""),
        tone=mat["ending"].get("tone", ""),
        rules=mat["world_rules"] or "（世界设定未登记铁律）",
        cast=mat["cast_brief"],
        hooks=mat["hooks_block"] or "（还没有登记伏笔）",
        written=written_brief,
        prev_ending=prev["text"] + "（" + prev["source"] + "）",
    )
    raw, _u0 = await _generate(
        project, system, _user,
        temperature=0.2, db=db, user=user, operation="volume_check",
    )
    parsed = _parse_json(raw)
    report = _report_groups(parsed.get("groups") if isinstance(parsed, dict) else None)
    if report is None:
        retry_raw, _u2 = await _generate(
            project, system, "请按四组给出体检结论（只输出 JSON）。", temperature=0.1,
            db=db, user=user, operation="volume_check_retry",
        )
        parsed2 = _parse_json(retry_raw)
        report = _report_groups(
            parsed2.get("groups") if isinstance(parsed2, dict) else None
        )
    if report is None:
        # spec：校验两次仍失败 → 降级为纯文本（不 502），提示可重试
        return {
            "ok": True, "vol_no": vol_no, "name": vol.title,
            "degraded": True, "text": _degrade_text(raw),
            "hint": "AI 的输出没法结构化——可重试",
        }
    # 度量（PRD §7 check_run{warn}）：判据条数只有服务端知道
    await log_event_async(
        db, user["id"], "check_run",
        {"vol_no": vol_no, "warn": _count_warn(report)},
    )
    return {"ok": True, "vol_no": vol_no, "name": vol.title, "report": report}
