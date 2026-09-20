"""卷域 AI（volume-plan-ai）：3 套可行走法 / 展开卷纲草稿 / 卷纲体检。

- 素材取自非章域单源（0 章书可用）：主线（story.yaml.story_arc 归一）、世界摘要（world_model）、
  核心人物（characters 表）、伏笔台账（prompt/context 台账块）、题材段（genres.service）、
  上一卷的结尾（resolve_prev_ending：事实优先——有归档章取实际收尾，否则取卷纲预期结局）。
- 三端点均不落库：产出为草稿/报告，由前端表单承接、走既有保存链；解析失败 502 可重试。
- 门禁：options/expand 归 PRO（require_ai_access）；check 免费（只读例外：不挂 require_ai_access，
  仍挂 require_novel_model——没配模型给 503，前端引导先接模型）。
- 记账：每次尝试（含失败）走 record_usage，operation 名 volume_options/_fail 等。
- 模型：`haiku` 符号别名（落到本书模型，与章纲起草同口径）；max_tokens 4096
  （判定类先例：2048 偶发「无文本输出」，见 settings/ai_router.py）。
"""

import difflib
import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from filesystem.storage import get_storage
from genres.service import build_genre_section, resolve_genre_context
from novels.router import _arc_normalize
from novels.service import get_novel
from prompt.context import load_active_hooks, render_hooks_block
from prompts import load as load_prompt
from settings import character_service
from volumes.render import volume_outline_text
from volumes.service import resolve_prev_ending

router = APIRouter(prefix="/api/novels/{project_id}/volumes", tags=["volumes"])

_MODEL = "haiku"  # 符号别名，落到本书模型（D12；与章纲起草同口径）
_MAX_TOKENS = 4096  # 判定类先例：2048 偶发「无文本输出」（settings/ai_router.py 注释）
SPINE_SIM_LIMIT = 0.6  # 两套走向相似度超过此值视为同质（触发一次复核）
FOCUS_AXES = ("代价", "关系", "认知", "节奏", "势力", "线索")

_LINE_MAX = 150
_PLAN_FIELDS = ("spine", "conflict", "ending", "focus_note")
_EXPAND_LIMITS = {"summary": 80, "conflict": 60, "goal": 60, "ending": 60}


class PlanLineBody(BaseModel):
    """作者那一句（可空——空则走 3 套方案）。"""

    line: str = Field(default="", max_length=_LINE_MAX)


class PlanPickBody(BaseModel):
    """选中的那套走法：走向 + 侧重（轴 + 一句话），填回输入框并直接展开。"""

    spine: str = Field(min_length=1, max_length=_LINE_MAX)
    conflict: str = Field(default="", max_length=150)
    ending: str = Field(default="", max_length=300)
    focus_note: str = Field(default="", max_length=60)


# ── 素材（非章域单源；0 章书可用）────────────────────────────────────────────


async def _book_material(db, project, *, hooks: bool) -> dict:
    """主线（arc 归一）＋世界摘要（铁律全量）＋核心人物＋伏笔台账＋题材段。"""
    storage = get_storage()
    story = await storage.read_yaml(project.root_path, "story.yaml") or {}
    arc = _arc_normalize(story.get("story_arc") or {})
    world_raw = await storage.read_yaml(project.root_path, "settings/world-setting.yaml") or {}
    gctx = await resolve_genre_context(project.root_path, project.id)
    chars = await character_service.list_characters(db, project.id)
    cast_brief = "\n".join(
        f"- {it.get('name', '')}（{it.get('role', '')}）：{(it.get('persona') or '')[:80]}"
        for it in chars.get("items", [])[:6]
    )
    hooks_block = ""
    if hooks:
        hooks_view = await load_active_hooks(project.id)
        hooks_block = render_hooks_block(hooks_view)
    return {
        "fullstory": arc["fullstory"],
        "ending": arc["ending"],
        "world_brief": world_summary_text(world_raw, 1200),
        "cast_brief": cast_brief,
        "hooks_block": hooks_block,
        "genre_section": build_genre_section(gctx),
        "genre_name": (gctx or {}).get("genre_id") or "",
    }


def _material_blocks(mat: dict, *, with_hooks: bool) -> str:
    blocks = [f"【全书主线】\n{mat['fullstory']}"]
    ending = mat["ending"]
    blocks.append(
        "【结局（作者写的）】最后一幕：{scene}｜主角变成：{hero}｜读者感觉：{tone}".format(
            scene=ending.get("scene", ""), hero=ending.get("hero", ""), tone=ending.get("tone", "")
        )
    )
    if mat["world_brief"]:
        blocks.append(f"【世界观摘要】\n{mat['world_brief']}")
    if mat["cast_brief"]:
        blocks.append(f"【核心人物】\n{mat['cast_brief']}")
    if with_hooks and mat["hooks_block"]:
        blocks.append(f"【伏笔台账（active）】\n{mat['hooks_block']}")
    if mat["genre_section"]:
        blocks.append(f"【题材与节奏】\n{mat['genre_section']}")
    return "\n\n".join(blocks)


# ── 上一卷的结尾（事实优先）──────────────────────────────────────────────────


async def _prev_ending(db, project, plan_vol_no: int) -> tuple[str, str]:
    """进场材料：plan_vol_no-1 卷收在哪里。事实优先——有归档章取实际收尾。"""
    if plan_vol_no <= 1:
        return "（第一卷从全景的起步开始）", "起点"
    from repositories import volume_repo, chapter_repo

    prev = await volume_repo.get_by_volume_no(db, project.id, plan_vol_no - 1)
    if prev is None:
        return "（还没写到这一卷之前的内容）", "上一卷"
    archived = [
        c
        for c in await chapter_repo.list_by_volume(db, prev.id)
        if c.status == "archived" and not c.ghost_of
    ]
    if archived:
        last = max(archived, key=lambda c: c.chapter_no)
        text = (last.summary or "").strip() or last.title
        return text, f"第{plan_vol_no - 1}卷 · 实际收尾（第{last.chapter_no}章）"
    return (prev.ending or "").strip(), f"第{plan_vol_no - 1}卷 · 预期结局（还没写到，先按卷纲）"


# ── JSON 解析与校验兜底 ───────────────────────────────────────────────────────


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


def _new_entity_hints(plans: list[dict], material_text: str) -> list[str]:
    """实体名对拍（软提示）：模型申报的 cast/factions 里不在素材文本中的名字。"""
    hints: list[str] = []
    for p in plans:
        for name in p.get("cast", []) or []:
            if isinstance(name, str) and name.strip() and name.strip() not in material_text:
                hints.append(f"{p.get('k', '')}：申报了素材里没有的「{name.strip()}」")
    return hints[:3]


async def _generate(project, system: str, user_msg: str, *, temperature: float, db, user, operation: str) -> str:
    """单次生成 + 失败重试一次（把失败原因喂回）＋ 全程计量（含失败留痕）。"""
    client = await get_ai_client_for_novel(project.id)
    usage: dict = {}
    try:
        raw = await client.chat(
            model=_MODEL, system=system, messages=[{"role": "user", "content": user_msg}],
            max_tokens=_MAX_TOKENS, temperature=temperature, usage=usage,
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
        return raw

    # 空 text 块（偶发：预算全用在思考/供应商只回 thinking）——照 _judge_chat 口径重试一次
    retry: dict = {}
    try:
        raw = await client.chat(
            model=_MODEL, system=system,
            messages=[
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": "（上一条没有输出正文）"},
                {"role": "user", "content": "请输出正文。"},
            ],
            max_tokens=_MAX_TOKENS, temperature=min(temperature, 0.2), usage=retry,
        )
    except Exception:  # noqa: BLE001 — 重试失败按原样报
        raise HTTPException(502, "AI 输出为空，可重试")
    from api_configs.usage import record_usage

    await record_usage(
        db, user_id=user["id"], project_id=project.id, operation=operation,
        model=effective_model(project) or _MODEL,
        tokens_in=retry.get("tokens_in", 0), tokens_out=retry.get("tokens_out", 0),
    )
    return raw


# ── 3 套可行走法 ─────────────────────────────────────────────────────────────


@router.post("/ai/options")
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
    mat = await _book_material(db, project, hooks=False)
    if not mat["fullstory"] and not any(mat["ending"].values()):
        raise HTTPException(422, "主线为空，请先在设定中完成主线（全景或结局三问）再拆卷")

    author_line = body.line.strip()
    system = load_prompt("volume_options").format(
        fullstory=mat["fullstory"],
        scene=mat["ending"].get("scene", ""),
        hero=mat["ending"].get("hero", ""),
        tone=mat["ending"].get("tone", ""),
        world_brief=mat["world_brief"],
        cast_brief=mat["cast_brief"],
        genre=mat["genre_section"] or mat["genre_name"],
        author_line=author_line or "（作者还没写——三套都要是你按设定推出的可行走法）",
    )
    raw = await _generate(
        project, system, "请给出 3 套可行走法（只输出 JSON）。",
        temperature=0.7, db=db, user=user, operation="volume_options",
    )
    parsed = _parse_json(raw)
    if parsed is None:
        retry_raw = await _generate(
            project,
            system + "\n\n（上一次输出不是合法 JSON 或结构不完整——请只输出 JSON。）",
            "请给出 3 套可行走法（只输出 JSON）。", temperature=0.3,
            db=db, user=user, operation="volume_options_retry",
        )
        parsed = _parse_json(retry_raw)
    if parsed is None:
        raise HTTPException(502, "AI 输出无法解析，可重试")

    plans = _sanitize_plans(parsed, author_line)
    if not plans:
        raise HTTPException(502, "AI 没给出可用的走法，可重试")
    return {"ok": True, "plans": plans, "note": str(parsed.get("note", "") or "")[:200]}


def _sanitize_plans(parsed: dict, author_line: str) -> list[dict]:
    """逐套兜底：四字段齐 + 侧重轴互不相同（同质的那套丢弃）。"""
    axes: list[str] = []
    out: list[dict] = []
    for p in parsed.get("plans", []) if isinstance(parsed.get("plans"), list) else []:
        if not isinstance(p, dict):
            continue
        spine = str(p.get("spine", "") or "").strip()
        conflict = str(p.get("conflict", "") or "").strip()
        ending = str(p.get("ending", "") or "").strip()
        if not spine or not ending:
            continue
        axis = str(p.get("focus_axis", "") or "").strip() or "代价"
        if axis in axes:
            continue  # 同轴的第二套＝同质，丢弃
        axes.append(axis)
        out.append(
            {
                "k": axis,
                "spine": spine[:60],
                "conflict": conflict[:120],
                "ending": ending[:120],
                "focus": (str(p.get("focus", "") or "").strip() or axis)[:60],
                "focus_axis": axis,
            }
        )
        if len(out) == MAX_OPTIONS:
            break
    return out


# ── 展开卷纲草稿 ─────────────────────────────────────────────────────────────


@router.post("/ai/expand")
async def ai_volume_expand(
    project_id: str,
    body: PlanExpandBody,
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
    plan_vol_no = state_plan_vol_no(body)
    prev_text, prev_src = await resolve_prev_ending(db, project, plan_vol_no)
    mat = await _book_material(db, project, hooks=True)

    system = load_prompt("volume_expand").format(
        fullstory=mat["fullstory"],
        scene=mat["ending"].get("scene", ""),
        hero=mat["ending"].get("hero", ""),
        world_brief=mat["world_brief"],
        cast_brief=mat["cast_brief"],
        prev_ending=prev_text,
        prev_src=prev_src,
        author_line=line,
        genre=mat["genre_section"] or mat["genre_name"],
        hooks=mat["hooks_block"] or "（还没有登记伏笔）",
    )
    raw = await _generate(
        project, system, "请把这句话铺成这一卷的卷纲（只输出 JSON）。",
        temperature=0.4, db=db, user=user, operation="volume_expand",
    )
    draft = _sanitize_expand(_parse_json(raw))
    if draft is None:
        retry_raw = await _generate(
            project,
            system + "\n\n（上一次输出不是合法 JSON 或四字段不齐——请只输出 JSON，四字段必须齐全。）",
            "请把这句话铺成这一卷的卷纲（只输出 JSON）。", temperature=0.2,
            db=db, user=user, operation="volume_expand_retry",
        )
        draft = _sanitize_expand(_parse_json(retry_raw))
    if draft is None:
        raise HTTPException(502, "展开结果为空或结构不完整，可重试")
    return {"ok": True, "plan_line": line, "draft": draft}


def _sanitize_expand(obj: dict | None) -> dict | None:
    if not isinstance(obj, dict):
        return None
    summary = str(obj.get("summary", "") or "").strip()
    conflict = str(obj.get("conflict", "") or "").strip()
    if not summary or not conflict:
        return None
    goal = str(obj.get("goal", "") or "").strip()
    ending = str(obj.get("ending", "") or "").strip()
    if not goal or not ending:
        return None
    try:
        total = int(obj.get("chapter_target"))
    except (TypeError, ValueError):
        total = 0
    return {
        "summary": summary[:80],
        "conflict": conflict[:60],
        "goal": goal[:300],
        "ending": ending[:300],
        "plants": _lines(obj.get("plants"), 2),
        "reveals": _lines(obj.get("reveals"), 2),
        "chapter_target": min(9999, max(0, total)),
        "name": str(obj.get("name", "") or "").strip()[:6],
    }


def _lines(v, cap: int) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip()[:120] for x in v if str(x).strip()][:cap]


# ── 卷纲体检 ────────────────────────────────────────────────────────────────


@router.post("/{ref}/ai/check")
async def ai_volume_check(
    project_id: str,
    ref: str,
    user: dict = Depends(get_current_user),
    __: bool = Depends(require_novel_model),  # 只读例外：免费可用（不挂 require_ai_access）
    db: AsyncSession = Depends(get_db),
):
    """卷级验证：对主线／对设定／对已写内容（只读、不拦、不代笔；免费可重复）。"""
    from volumes.service import get_volume

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol_no = int(ref.removeprefix("vol-").split("-")[0])
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")
    detail = await get_volume(db, project, ref)
    prev_text, prev_src = await resolve_prev_ending(db, project, vol_no, detail=detail)

    system = load_prompt("volume_check").format(
        vol=volume_outline_text(vol),
        fullstory=detail.get("fullstory", ""),
        scene=detail.get("ending_scene", ""),
        rules=detail.get("world_rules", ""),
        cast=detail.get("cast_brief", ""),
        hooks=detail.get("hooks_block", ""),
        written=detail.get("written_brief", "（还没写）"),
        prev=prev_text,
    )
    raw = await _generate(
        project, system, "请按三组给出这一卷的体检结论（只输出 JSON）。",
        temperature=0.2, db=db, user=user, operation="volume_check",
    )
    parsed = _parse_json(raw)
    if parsed is None:
        retry_raw = await _generate(
            project, system, "请按三组给出体检结论（只输出 JSON）。", temperature=0.1,
            db=db, user=user, operation="volume_check_retry",
        )
        parsed = _parse_json(retry_raw)
    report = _sanitize_report(parsed)
    if report is None:
        raise HTTPException(502, "体检输出无法解析，可重试")
    return {"ok": True, "report": report}
