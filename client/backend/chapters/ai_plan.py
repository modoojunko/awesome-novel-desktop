"""卷下拆章 · AI 链路（c-chapter-plan-ai）

- 出卡：POST /api/novels/{id}/volumes/{ref}/chapters/ai-directions（PRO；生成类）
- 自检：POST /api/novels/{id}/chapters/ai-selfcheck（免费；只读例外——不挂 require_ai_access；卡面草稿随请求携带）
- 进场：GET  /api/novels/{id}/volumes/{ref}/next-chapter-anchor（全档；手写路径也要进场）

复用纪律（D19）：生成/解析/降级/越纲对拍一律复用 volumes.ai_plan 的既有实现，
本模块只加章级素材装配、四维名次→字母、互斥验收与两个端点，不新写第二套链路。
"""

from __future__ import annotations

import difflib
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import (
    ai_feature,
    get_current_user,
    require_ai_access,
    require_novel_model,
)
from db import get_db
from novels.service import get_novel
from prompts import load_layers
from volumes.ai_plan import (
    ExcludeItem,
    _book_material,
    _cardless_brief,
    _cardless_cast_rows,
    _degrade_text,
    _entity_warnings,
    _exclude_block,
    _generate,
    _parse_json,
    _render,
    load_fragment,
)
from volumes.render import volume_outline_text
from workflow.engine import strip_suffix

router = APIRouter(prefix="/api/novels/{project_id}", tags=["chapter-plan-ai"])

logger = logging.getLogger(__name__)


def _vol_no(vol_ref: str) -> int:
    """`vol-{N}` → N；非法引用 400（c-backend-infra-hygiene）——原裸 int() 会把
    非法引用炸成未处理异常（500）。"""
    raw = strip_suffix(vol_ref or "").replace("vol-", "")
    if not raw.isdigit():
        raise HTTPException(400, "卷引用不合法")
    return int(raw)

SPLIT_AXES = ("加速", "关系", "线索", "代价", "危机", "收束")
DIMENSIONS = ("反转", "递增", "推进", "拉力")  # 四维：反转/冲突层层递增/剧情推进/结尾拉力
STAGE_SET = ("开局铺垫", "冲突初现", "矛盾升级", "重要转折", "高潮爆发", "卷末收束")
SIM_LIMIT = 0.6  # (plot, ending) 相似度阈值（照卷级 SPINE_SIM_LIMIT 先例）
MAX_ATTEMPTS = 3  # 重试预算：3 次尝试后仍不足 2 张 → degraded

# —— 位置感知（c-plan-pacing-rules）：角色 → 片段文件；低三档停同档 3 章 → 升档提醒 ——
POS_FRAGMENTS = {"ch1": "pos_ch1", "golden3": "pos_golden3", "vol_start": "pos_vol_start"}
_NEXT_STAGE = {"开局铺垫": "冲突初现", "冲突初现": "矛盾升级", "矛盾升级": "重要转折"}

_LIMITS = {"title": 12, "plot": 150, "obstacle": 60, "ending": 80, "why": 30, "gap": 30}
_PLACE_SPLIT_RE = re.compile(r"[、，,；;。\n\r\t 　]+")


# ═══════════════ 进场（章级；has_prose 分流） ═══════════════


async def resolve_prev_chapter_ending(db, project, vol, ch_no: int) -> dict:
    """本章进场：上一章有正文 → 正文末段（取自正文结尾）；无正文 → 上一章章末落点（拟定）。
    卷首章复用既有卷级取法（resolve_prev_ending，事实优先）。返回 {text, source}。"""
    if ch_no <= 1:
        from volumes.service import resolve_prev_ending

        return await resolve_prev_ending(db, project, vol.volume_no)
    from repositories import chapter_repo

    rows = [
        c
        for c in await chapter_repo.list_by_volume(db, vol.id)
        if not c.ghost_of and c.chapter_no < ch_no
    ]
    if not rows:
        return {"text": "（还没有上一章）", "source": "本章是这一卷的第一章"}
    prev = max(rows, key=lambda c: c.chapter_no)
    if prev.has_prose:
        from chapters.store import assemble_chapter
        from write.chapter_writer import clip_tail_to_sentence_boundary

        prose = str(assemble_chapter(prev).get("prose") or "").strip()
        paras = [p.strip() for p in prose.split("\n") if p.strip()]
        if paras:
            # c-chapter-seam-hardcut：句边界回退单源（与写作端上章结尾同口径），
            # 超长末段不再 [:200] 硬切成残句开头
            return {
                "text": clip_tail_to_sentence_boundary(paras[-1], 200),
                "source": f"第{prev.chapter_no}章 · 取自正文结尾（写到那里之后，这里以实际为准）",
            }
    exit_text = (prev.ladder_exit or "").strip()
    return {
        "text": exit_text or "（上一章还没写结尾）",
        "source": f"第{prev.chapter_no}章 · 拟定，取自章纲落点",
    }


# ═══════════════ 位置感知（c-plan-pacing-rules）：全局章号／角色选择器／升档提醒 ═══════════════


def chapter_position_tags(global_ch: int, ch_no: int) -> list[str]:
    """位置角色（纯函数，只依赖入参——同状态同输出，重拆幂等）：
    全书第 1 章 → ch1；第 2–3 章 → golden3；各卷第 1 章且非全书第 1 章 → vol_start；其余无片段。"""
    tags: list[str] = []
    if global_ch == 1:
        tags.append("ch1")
    elif global_ch <= 3:
        tags.append("golden3")
    if ch_no == 1 and global_ch != 1:
        tags.append("vol_start")
    return tags


async def _global_chapter_no(db, project_id, vol, ch_no: int) -> int:
    """全书全局章号＝前面各卷已拆章数（滤 ghost）＋本章卷内序号（插卷/回改后随当前状态重算）。"""
    if vol.volume_no <= 1:
        return ch_no
    from repositories import chapter_repo, volume_repo

    early = {
        v.id
        for v in await volume_repo.list_by_project(db, project_id)
        if v.volume_no < vol.volume_no
    }
    if not early:
        return ch_no
    rows = [c for c in await chapter_repo.list_by_project(db, project_id) if not c.ghost_of]
    return sum(1 for c in rows if c.volume_id in early) + ch_no


async def global_chapter_position(db, project_id: str, vol_no: int, ch_no: int) -> tuple[int, list[str]]:
    """按卷号＋卷内章号算全局章号与位置标签（剧情抽卡／正文组装两路共用单源）。

    卷行查不到（数据未建卷）→ (0, [])，调用方按「无位置标注」降级。
    """
    from repositories import volume_repo

    vol = await volume_repo.get_by_volume_no(db, project_id, vol_no)
    if vol is None:
        return 0, []
    global_ch = await _global_chapter_no(db, project_id, vol, ch_no)
    return global_ch, chapter_position_tags(global_ch, ch_no)


def position_label(global_ch: int, tags: list[str]) -> str:
    """位置标注文案（素材【本章位置】／正文「本章位置：」两路同词）：首章／开篇期，其余空。"""
    if "ch1" in tags:
        return "全书第 1 章（首章）"
    if "golden3" in tags:
        return f"全书第 {global_ch} 章（开篇期）"
    return ""


def cadence_reminder(rows, *, is_final: bool, target: int) -> str:
    """本地升档提醒（软信号：只进素材装配与作者可见提示，SHALL NOT 进出卡校验/重试链路）。

    触发＝本卷末 3 章 stage 同档且落在低三档（rows 只含本卷——跨卷边界自然重置）且
    本章非末章、目标已设时剩余配额 > 1（末章义务是收束不是升档；目标未设无末章约束）。
    高三档（重要转折/高潮爆发/卷末收束）已到顶或属收束、stage 未定的手写章，均不触发。
    """
    if is_final:
        return ""
    if target and len(rows) >= target - 1:
        return ""  # 剩余配额 ≤ 1：升档义务让位于收束
    stages = [(c.plot_stage or "").strip() for c in rows][-3:]
    if len(stages) < 3 or len(set(stages)) != 1:
        return ""
    stuck = stages[0]
    nxt = _NEXT_STAGE.get(stuck)
    if nxt is None:
        return ""
    return (
        f"【节奏提醒】已连续 3 章停在「{stuck}」没升档：本章三个方向都必须把冲突推上新台阶，"
        f"stage 至少「{nxt}」；上一章的坎要在这一章撞出更大的。"
    )


# ═══════════════ 素材装配（⓪位置 → ①→⑧ → ⑨节奏提醒；预算见 prompt-draft §5） ═══════════════


async def _chapter_material(db, project, vol, ch_no: int) -> dict:
    # c-plan-material-fullinfo：聚光退役，人物块＝全名单；无卡名单改本卷口径（覆盖 _book_material 的全书块）
    mat = await _book_material(db, project, with_hooks=False)  # 不给伏笔台账（防"提前揭"）
    cardless_rows = await _cardless_cast_rows(
        db, project.id, mat.get("card_names") or set(), volume_id=vol.id
    )
    mat["cardless_brief"] = _cardless_brief(cardless_rows)
    mat["known_entities"] |= {r["name"] for r in cardless_rows}
    entry = await resolve_prev_chapter_ending(db, project, vol, ch_no)
    from repositories import chapter_repo

    rows = sorted(
        [c for c in await chapter_repo.list_by_volume(db, vol.id) if not c.ghost_of],
        key=lambda c: c.chapter_no,
    )
    done = [
        # c-ai-material-audit：章纲 summary 列宽 300，旧 [:40] 把"已拆过什么"切没了
        f"第{c.chapter_no}章 {c.title or ''}｜{(c.summary or '').strip()}｜{c.plot_stage or '（未定阶段）'}"
        for c in rows
    ]
    target = vol.chapter_target or 0
    quota_left = max(0, target - len(rows)) if target else 0
    is_final = bool(target) and quota_left == 1
    # 已排满（含超出）：目标已设且剩余额度为 0 且不是末章
    quota_overshot = bool(target) and quota_left == 0 and not is_final
    prev_line = ""
    if rows:
        last = rows[-1]
        prev_line = f"第{last.chapter_no}章：{(last.summary or last.title or '').strip()[:60]}"
    global_ch = await _global_chapter_no(db, project.id, vol, ch_no)
    mat.update(
        {
            "entry": entry,
            "vol_outline": volume_outline_text(vol),
            "done_chapters": done,
            "quota_left": quota_left,
            "quota_overshot": quota_overshot,
            "is_final": is_final,
            "prev_line": prev_line,
            "known_places": await _known_places(db, project),
            # 位置感知（⓪数据行＋片段角色）与本地节奏提醒（⑨；软信号，不进校验链路）
            "global_ch": global_ch,
            "ch_no": ch_no,
            "vol_total": target or None,
            "position_tags": chapter_position_tags(global_ch, ch_no),
            "cadence": cadence_reminder(rows, is_final=is_final, target=target),
            "stage_hit_climax": any((c.plot_stage or "").strip() == "高潮爆发" for c in rows),
        }
    )
    return mat


async def _known_places(db, project) -> set[str]:
    """已知地点集合（越纲对拍的已知侧·地点类）。

    来源两处，都是作者已经写下的地名：①各章章纲的「地点」字段（结构化记录）；
    ②世界舞台那段自由文本里圈出的地点短语（顿号/逗号/分号切分，2–12 字）。
    判据宽松是有意的——差集只用来提醒，误报会吵到作者。
    """
    from filesystem.storage import get_storage
    from repositories import chapter_repo

    out: set[str] = set()
    rows = await chapter_repo.list_by_project(db, project.id)
    for c in rows:
        if c.ghost_of:
            continue
        loc = str(getattr(c, "location", "") or "").strip()
        if loc:
            out.add(loc[:20])
    try:
        world = await get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
        stage = str((world or {}).get("stage") or "")
        for tok in _PLACE_SPLIT_RE.split(stage):
            t = tok.strip()
            if 2 <= len(t) <= 12:
                out.add(t)
    except Exception:  # noqa: BLE001, S110 — 世界设定读不到不影响出卡
        pass
    return out


def _drop_excluded_directions(
    cards: list[dict],
    keep_map: list[int],
    one_liners: list[str],
    exclude: list[tuple[str, str]],
    warn: list[str],
) -> tuple[list[dict], list[int]]:
    """排除对拍（c-plan-draw-exclude）：**同轴且一句话相似**才判撞车丢弃。

    one_liners＝模型 diff.one_liner（按原始卡序）；keep_map 保持与保留卡对齐，
    名次映射不受丢卡影响。短串 difflib 噪声大——单轴相似不丢，须同轴且相似。
    """
    kept_cards: list[dict] = []
    kept_map: list[int] = []
    for card, oi in zip(cards, keep_map):
        line = one_liners[oi].strip() if oi < len(one_liners) else ""
        clash = any(
            e_a == card["axis"]
            and line
            and difflib.SequenceMatcher(None, line, e_l).ratio() >= SIM_LIMIT
            for e_a, e_l in exclude
        )
        if clash:
            warn.append(f"「{card['axis']}｜{line[:20]}」与已出方向雷同，已丢弃")
            continue
        kept_cards.append(card)
        kept_map.append(oi)
    return kept_cards, kept_map


def _blocks_chapter(mat: dict) -> str:
    """⓪位置 → ①进场 → ②卷纲四问 → ③已拆章节 → ④配额/末章 → ⑤题材 → ⑥人物全名单＋无卡名单 → ⑦铁律 → ⑧上一章一行 → ⑨节奏提醒（条件）→ ⑩世界观（c-plan-material-fullinfo）。"""
    pos_line = f"【本章位置】全书第 {mat['global_ch']} 章｜本卷第 {mat['ch_no']} 章"
    if mat.get("vol_total"):
        pos_line += f"（本卷共 {mat['vol_total']} 章）"
    parts = [
        pos_line,
        f"【进场（本章从哪接）】\n{mat['entry']['text']}（{mat['entry']['source']}）",
    ]
    if mat["vol_outline"]:
        parts.append(f"【本卷卷纲（四问）】\n{mat['vol_outline']}")
    if mat["done_chapters"]:
        # c-ai-material-audit：全卷给全（旧 [-12:] 让拆第 20 章时看不见前 8 章）
        parts.append("【已经拆过的章】\n" + "\n".join(mat["done_chapters"]))
    # 配额：末章 / 已排满 / 还剩 N 章 / 未设目标——四态分明（「已排满」不得报成「未设」）
    if mat["is_final"]:
        quota = "本章是本卷末章——三个方向的结尾都必须收在卷纲第四问「预期结局」上。"
    elif mat["quota_left"] > 0:
        quota = f"本卷还剩 {mat['quota_left']} 章额度。"
    elif mat["quota_overshot"]:
        quota = "本卷已排满甚至超出目标章数——可以继续拆，但建议回卷纲核对节奏。"
    else:
        quota = "（目标章数未设）"
    parts.append(f"【章数配额】\n{quota}")
    # 末章：硬规则 5 要求「收束以【结局（作者写的）】为准」——该块只在末章给（与卷级素材同源同文案）
    if mat["is_final"]:
        e = mat.get("ending") or {}
        if any(str(v or "").strip() for v in e.values()):
            parts.append(
                "【结局（作者写的）】最后一幕：{s}｜主角变成：{h}｜读者感觉：{t}".format(
                    s=e.get("scene", ""), h=e.get("hero", ""), t=e.get("tone", "")
                )
            )
    if mat["genre_section"]:
        parts.append(f"【题材与节奏】\n{mat['genre_section']}")
    if mat["cast_brief"]:
        parts.append(f"【核心人物】\n{mat['cast_brief']}")
    if mat.get("cardless_brief"):
        parts.append(f"【无卡出场名单（本卷已拆章出现、未建卡）】\n{mat['cardless_brief']}")
    if mat["world_rules"]:
        parts.append(f"【世界铁律】\n{mat['world_rules']}")
    if mat["prev_line"]:
        parts.append(f"【上一章发生了什么】\n{mat['prev_line']}")
    if mat.get("cadence"):
        parts.append(mat["cadence"])
    if mat.get("world_brief"):
        parts.append(f"【世界观】\n{mat['world_brief']}")
    return "\n\n".join(parts)


# ═══════════════ 出卡校验：字段/闭集/名次形态/同质（依据只做参考，不参与机判） ═══════════════


def _fit(v, key: str) -> str:
    return str(v or "").strip()[:_LIMITS[key]]


def _similar(a: dict, b: dict) -> bool:
    ra = f"{a.get('plot', '')}{a.get('ending', '')}"
    rb = f"{b.get('plot', '')}{b.get('ending', '')}"
    return difflib.SequenceMatcher(None, ra, rb).ratio() > SIM_LIMIT


def _sanitize_directions(parsed: dict | None) -> tuple[list[dict], list[int], list[str]]:
    """逐卡兜底：字段/闭集不合法 → 丢卡；轴与 diff 不一致/未知轴 → 丢卡（不改写）。
    返回 (可用卡, 各保留卡在模型输出里的原始下标, warnings)——原始下标供名次按位映射：
    丢一张卡是合法结局（「只出了 2 个方向」），不得连带作废整批名次而白烧一次生成。"""
    warn: list[str] = []
    if not isinstance(parsed, dict):
        return [], [], ["出卡不是合法 JSON"]
    diff = parsed.get("diff")
    diff = diff if isinstance(diff, dict) else {}  # 模型拍平（数组/字符串）时按缺失处理，不 500
    axes_raw = diff.get("axes")
    axes = [str(a).strip() for a in (axes_raw if isinstance(axes_raw, list) else [])]
    cards_in = parsed.get("directions")
    if not isinstance(cards_in, list):
        return [], [], ["directions 缺失"]
    out: list[tuple[int, dict]] = []
    for i, c in enumerate(cards_in):
        if not isinstance(c, dict):
            continue
        axis = str(c.get("axis") or "").strip()
        stage = str(c.get("stage") or "").strip()
        plot, ending = _fit(c.get("plot"), "plot"), _fit(c.get("ending"), "ending")
        if axis not in SPLIT_AXES or stage not in STAGE_SET or not plot or not ending:
            warn.append(f"第 {i + 1} 张字段/闭集不合法，已丢弃")
            continue
        if axes and (i >= len(axes) or axes[i] != axis):
            warn.append(f"第 {i + 1} 张 axis 与 diff 不一致，已丢弃")
            continue
        # 三轴互不相同（spec）：与已收卡同轴 → 丢卡；丢到 <2 张由端点重试阶梯接管
        if any(card["axis"] == axis for _, card in out):
            warn.append(f"第 {i + 1} 张 axis「{axis}」与前面某张重复，已丢弃")
            continue
        out.append(
            (
                i,
                {
                    "axis": axis,
                    "title": _fit(c.get("title"), "title"),
                    "plot": plot,
                    "obstacle": _fit(c.get("obstacle"), "obstacle"),
                    "ending": ending,
                    "stage": stage,
                    "cast": [str(x).strip()[:20] for x in (c.get("cast") or []) if str(x).strip()][:6],
                    "factions": [str(x).strip()[:20] for x in (c.get("factions") or []) if str(x).strip()][:6],
                    "places": [str(x).strip()[:20] for x in (c.get("places") or []) if str(x).strip()][:6],
                    "why": _fit(c.get("why"), "why"),
                    "gap": _fit(c.get("gap"), "gap"),
                },
            )
        )
    # 同质：保留先出现者（复核一次的动作由端点按 attempt 控制）；原始下标随保留卡一路带走
    kept: list[tuple[int, dict]] = []
    for i, card in out:
        if any(_similar(card, k) for _, k in kept):
            warn.append(f"「{card['title'] or card['axis']}」与前面某张太像，已丢弃")
            continue
        kept.append((i, card))
    return [c for _, c in kept], [i for i, _ in kept], warn


def _ranks_ok(rs, n_orig: int) -> bool:
    """某维名次形态：个数与模型输出卡数一致、取值 1–3、从 1 起不跳档（合法 1/1/2，非法 1/1/3）。
    形态不合法只让该维不计分——不重抽、不丢卡（等级质量不是结构性失败）。"""
    if not isinstance(rs, list) or len(rs) != n_orig:
        return False
    vals: list[int] = []
    for r in rs:
        if isinstance(r, bool) or not isinstance(r, (int, float)) or r != int(r):
            return False
        vals.append(int(r))
    if any(v < 1 or v > 3 for v in vals):
        return False
    uniq = sorted(set(vals))
    return uniq == list(range(1, len(uniq) + 1))


def _as_dict(parsed: dict | None, key: str) -> dict:
    """模型把该键拍平成数组/字符串时按空对象处理（不 500；sanitize 层为这类不合形而存在）。"""
    v = (parsed or {}).get(key)
    return v if isinstance(v, dict) else {}


def _as_reason_map(parsed: dict | None) -> dict:
    """依据＝供作者参考的文本（≤20 字 clamp）；服务端不再校验其能否逐字对上卡面字段。"""
    v = (parsed or {}).get("reasons")
    if not isinstance(v, dict):
        return {}
    return {str(k): str(x).strip()[:20] for k, x in v.items() if str(x).strip()}


def _as_str_list(parsed: dict | None, key: str, limit: int) -> list[str]:
    v = (parsed or {}).get(key)
    if not isinstance(v, list):
        return []  # 字符串会被逐字符切碎——非 list 一律当空
    return [str(x).strip()[:limit] for x in v if str(x).strip()]


def _as_text(parsed: dict | None, key: str, limit: int) -> str:
    v = (parsed or {}).get(key)
    return (v if isinstance(v, str) else "").strip()[:limit]


def _grades(
    parsed: dict,
    n_orig: int,
    keep_map: list[int],
    dims: tuple[str, ...] = DIMENSIONS,
    s_min: int = 3,
) -> list[str]:
    """名次 → S/A/B：唯一第一名才计入（并列第一不计该维）；≥s_min → S，1–s_min 之下的 1+ → A，0 → B。

    名次按模型输出的**原始卡序**给，经 keep_map 映射到保留卡后计分；某维形态不合法、
    或该维第一名所在的卡已被丢弃 ⇒ 该维不计分（丢卡/形态瑕疵不升级为整批重抽）。
    **阈值按维数传参（c-character-intro 决策 4）**：拆章 4 维＝3、提案卡 3 维＝2——
    共用函数不共用阈值（4 维若用 2 会出两张 S）。
    """
    ranks_raw = parsed.get("ranks")
    ranks = ranks_raw if isinstance(ranks_raw, dict) else {}
    counts = [0] * len(keep_map)
    for dim in dims:
        rs = ranks.get(dim)
        if not _ranks_ok(rs, n_orig):
            continue
        firsts = [i for i, r in enumerate(rs) if r == 1]
        if len(firsts) != 1 or firsts[0] not in keep_map:
            continue
        counts[keep_map.index(firsts[0])] += 1
    return ["S" if c >= s_min else "A" if c >= 1 else "B" for c in counts]


# ═══════════════ 端点 ═══════════════


@router.get("/volumes/{vol_ref}/next-chapter-anchor")
async def next_chapter_anchor(
    project_id: str,
    vol_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """下一章的进场（全档只读）——手写路径不发 AI 请求也要进场。"""
    from repositories import chapter_repo, volume_repo

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol_no = _vol_no(vol_ref)
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")
    rows = [c for c in await chapter_repo.list_by_volume(db, vol.id) if not c.ghost_of]
    entry = await resolve_prev_chapter_ending(db, project, vol, len(rows) + 1)
    # 章号/卷号单源：卡面标题「拆第N章」、行号 0N、kicker「第X卷」都取这里，
    # 前端不再自造（曾用常量占位 → 每章都写「拆第一章」）
    return {"ok": True, **entry, "next_no": len(rows) + 1, "vol_no": vol.volume_no}


class DirectionsBody(BaseModel):
    """重抽排除（c-plan-draw-exclude）：已出批的轴＋一句话。请求携带，SHALL NOT 落库。"""

    exclude: list[ExcludeItem] = Field(default_factory=list, max_length=9)


@router.post("/volumes/{vol_ref}/chapters/ai-directions")
@ai_feature("ai-plan")
async def ai_chapter_directions(
    project_id: str,
    vol_ref: str,
    body: DirectionsBody = DirectionsBody(),
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),  # 生成类归 PRO
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """同一章的 3 个互斥剧情方向（不落库）。名次在模型侧、字母在服务端算。"""
    from repositories import chapter_repo, volume_repo

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol_no = _vol_no(vol_ref)
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")
    # 卷纲空门槛（与主线空门同构）：主旨/冲突/卷末三项——末章边界靠卷末，缺它出卡会越界
    missing = [
        label
        for label, val in (("这一卷讲什么", vol.summary), ("主要冲突", vol.core_conflict), ("卷末收在哪里", vol.ending))
        if not str(val or "").strip()
    ]
    if missing:
        raise HTTPException(422, f"卷纲还没填全（{'、'.join(missing)}）——先去卷纲补齐再拆章")
    rows = [c for c in await chapter_repo.list_by_volume(db, vol.id) if not c.ghost_of]
    ch_no = len(rows) + 1
    mat = await _chapter_material(db, project, vol, ch_no)
    # 重抽排除（D21）：已出批的轴＋一句话；中性禁令入素材，服务端同轴相似丢卡
    exclude = [(i.axis.strip(), i.line.strip()) for i in body.exclude if i.axis.strip() and i.line.strip()][:9]
    _sys_t, _usr_t = load_layers("chapter_split")
    system = _render(
        _sys_t,
        split_axes="／".join(SPLIT_AXES),
        plot_stages="／".join(STAGE_SET),
    )
    user_msg = _render(
        _usr_t,
        material_blocks=_blocks_chapter(mat) + _exclude_block(exclude),
        position_rules="\n\n".join(load_fragment(POS_FRAGMENTS[t]) for t in mat["position_tags"]),
    ) + f"\n\n请给出第 {ch_no} 章的 3 个剧情方向（只输出 JSON）。"
    raw, _u = await _generate(project, system, user_msg, temperature=0.7, db=db, user=user, operation="chapter_directions")
    parsed = _parse_json(raw)
    cards, keep_map, warn = _sanitize_directions(parsed)
    if exclude:
        one_liners = (
            [str(x).strip() for x in (parsed.get("diff", {}).get("one_liner") or [])]
            if isinstance(parsed, dict)
            else []
        )
        cards, keep_map = _drop_excluded_directions(cards, keep_map, one_liners, exclude, warn)
    attempts = 1
    # 整批重试只由**结构性失败**触发（可用卡不足 2 张：轴/阶段越界、同轴、同质丢到只剩一张、
    # 输出不可解析）。等级质量与依据可寻性一律不构成重抽理由——它们是对同一批数据的判读，
    # 重抽改不了判读，只让作者白等一次完整生成（曾因此每次固定跑满 3 次 ≈18 秒）。
    while len(cards) < 2 and attempts < MAX_ATTEMPTS:
        cause = "；".join(warn[:2]) or "的方向不合法"
        # 排除触发（D21）：求差异 SHALL NOT 降温；纯结构性失败照既有阶梯降温
        retry_temp = 0.7 if (exclude and any("与已出方向雷同" in w for w in warn)) else 0.3
        retry_system = system + f"\n\n（上一次{cause}。）"
        # 同源同文（c-chapter-draw-retry-material）：重试复用首调用同一 user 消息
        # （素材包＋位置片段＋引导句＋排除清单）——旧实现只发一句索取语，素材全丢，
        # 出卡必然脱离全书设定，且排除清单缺席会让重试卡再撞对拍被二次丢弃。
        logger.info(
            "chapter_directions retry attempt=%d/%d cause=%s novel=%s vol=%s ch=%d",
            attempts + 1, MAX_ATTEMPTS, cause, project.id, vol_no, ch_no,
        )
        raw, _u = await _generate(
            project, retry_system, user_msg,
            temperature=retry_temp, db=db, user=user, operation="chapter_directions_retry",
        )
        parsed = _parse_json(raw)
        cards, keep_map, warn = _sanitize_directions(parsed)
        if exclude:
            one_liners = (
                [str(x).strip() for x in (parsed.get("diff", {}).get("one_liner") or [])]
                if isinstance(parsed, dict)
                else []
            )
            cards, keep_map = _drop_excluded_directions(cards, keep_map, one_liners, exclude, warn)
        attempts += 1
    if len(cards) < 2:
        return {
            "ok": True, "degraded": True,
            "text": _degrade_text(raw),
            "hint": "出卡失败，可重试，或自己写这一章",
            "entry": mat["entry"],
        }
    # 字母恒按名次算（名次按模型输出的原始卡序，经 keep_map 映射到保留卡）
    n_orig = len(parsed.get("directions") or []) if isinstance(parsed, dict) else 0
    grades = _grades(parsed or {}, n_orig, keep_map)
    known = mat["known_entities"]
    all_cast = [n for c in cards for n in c["cast"]]
    all_factions = [n for c in cards for n in c["factions"]]
    all_places = [n for c in cards for n in c["places"]]
    # 已知地点侧＝章纲「地点」字段 ∪ 世界舞台里圈出的地名（_known_places）
    warn.extend(_entity_warnings(all_cast, all_factions, known | mat["known_places"], all_places))
    warn = warn[:5]  # 既有告警（丢卡＋实体差集）合计截到 5 条——排满提示在截断后 append，必在场
    # 排满提示（软信号，可忽略）：排满且从未触达「高潮爆发」——不阻断、不自动重拆（作者可写刻意的过渡卷）
    if mat["quota_overshot"] and not mat["stage_hit_climax"]:
        warn.append("这一卷已排满但还没到高潮——回卷纲核对节奏")
    return {
        "ok": True,
        "entry": mat["entry"],
        "is_final": mat["is_final"],
        "quota_left": mat["quota_left"],
        "diff": _as_dict(parsed, "diff"),
        "directions": cards,
        "grades": grades,
        "ranks": _as_dict(parsed, "ranks"),
        "reasons": _as_reason_map(parsed),
        "checks": _as_str_list(parsed, "checks", 40)[:3],
        "note": _as_text(parsed, "note", 60),
        "warnings": warn,  # ≤5 条既有告警＋1 条排满节奏提示
    }


@router.get("/chapters/{chapter_ref}/plan-card")
async def chapter_plan_card(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """回改卡面：既有拟定章的五段＋进场（与新建共用同一张卡面；全档只读）。

    spec 5.6：左树章行／卷页派生视图章行／落点卡三处通向同一张本章卡——三处都读这里。
    """
    from chapters.store import assemble_chapter
    from repositories import chapter_repo
    from workflow.engine import strip_suffix

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    row = await chapter_repo.get_by_ref(db, project.id, strip_suffix(chapter_ref))
    if row is None:
        raise HTTPException(404, "Chapter not found")
    data = assemble_chapter(row)
    entry = await resolve_prev_chapter_ending(db, project, row.volume, row.chapter_no)
    return {
        "ok": True,
        "title": data.get("title") or "",
        # summary 在 outline 内（装配口径：outline.summary 对应章纲「本章剧情」）
        "plot": (data.get("outline") or {}).get("summary") or "",
        "challenge": data.get("challenge") or "",
        "ending": data.get("ladder_exit") or "",
        "stage": data.get("plot_stage") or "",
        "entry_text": entry["text"],
        "entry_source": entry["source"],
        "next_no": row.chapter_no,
    }


class SelfcheckBody(BaseModel):
    """卡面草稿（自检发生在「排上」之前，此时章未落库——五段一律取请求体）。

    entry_text＝卡面当前显示的进场（衔接组比对用；进场系派生不落库）。
    """

    vol_ref: str
    entry_text: str = ""
    chapter_ref: str = ""
    title: str = ""
    plot: str = ""
    challenge: str = ""
    ending: str = ""
    stage: str = ""


@router.post("/chapters/ai-selfcheck")
async def ai_chapter_selfcheck(
    project_id: str,
    body: SelfcheckBody,
    user: dict = Depends(get_current_user),
    __: bool = Depends(require_novel_model),  # 只读例外：不挂 require_ai_access（免费可用）
    db: AsyncSession = Depends(get_db),
):
    """章级自检三组：衔接（本地）＋配额（本地）＋剧情吸引力（AI 只读四维短评）。

    卡面按钮在手写卡底条（未排上即可点）——故不按 ref 读章，五段取请求体；
    AI 组失败/未配模型只让该组给引导文案，本地两组照常返回（不 500）。
    """
    from repositories import chapter_repo, volume_repo
    from workflow.engine import strip_suffix

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol_no = _vol_no(body.vol_ref)
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")
    rows = sorted(
        [c for c in await chapter_repo.list_by_volume(db, vol.id) if not c.ghost_of],
        key=lambda c: c.chapter_no,
    )
    # 目标章号：已排上取该章，未排上取本卷末章 +1（进场与配额都按「这一章」算）
    ch_no = len(rows) + 1
    if body.chapter_ref:
        row = await chapter_repo.get_by_ref(db, project.id, strip_suffix(body.chapter_ref))
        if row is not None:
            ch_no = row.chapter_no
    entry = await resolve_prev_chapter_ending(db, project, vol, ch_no)
    # 衔接组（本地）：本次重新派生的进场 与 卡面当前显示进场（trim 后逐字比对）
    # 卡面没带进场（未载入/取数失败）＝无可比对，不判漂移（避免误报 warn）
    link_ok = (not body.entry_text.strip()) or entry["text"].strip() == body.entry_text.strip()
    # 配额组（本地）：这一章是否超出卷的目标章数
    target = vol.chapter_target or 0
    over = bool(target) and ch_no > target
    quota = (
        f"已排 {ch_no} 章，超出本卷目标 {target} 章——可以拆，但建议回卷纲核对节奏"
        if over
        else (f"第 {ch_no} 章，本卷目标 {target} 章" if target else "本卷还没设目标章数")
    )
    prev_line = ""
    siblings = [c for c in rows if c.chapter_no < ch_no]
    if siblings:
        last = siblings[-1]
        prev_line = f"第{last.chapter_no}章：{(last.summary or last.title or '').strip()[:60]}"
    _sys_t, _usr_t = load_layers("chapter_selfcheck")
    system = _sys_t
    user_msg = _render(
        _usr_t,
        entry=entry["text"] + "（" + entry["source"] + "）",
        prev_line=prev_line or "（这是第一卷第一章）",
        plot=_fit(body.plot, "plot"),
        obstacle=_fit(body.challenge, "obstacle"),
        ending=_fit(body.ending, "ending"),
        stage=body.stage if body.stage in STAGE_SET else "（未定）",
    )
    out: dict = {
        "ok": True,
        "link": {"ok": link_ok, "text": "本章进场已自动接上上一章结尾" if link_ok else "上一章结尾已变化"},
        "quota": {"ok": not over, "text": quota},
    }
    try:
        raw, _u = await _generate(
            project, system, user_msg,
            temperature=0.2, db=db, user=user, operation="chapter_selfcheck",
        )
    except HTTPException:
        return {**out, "degraded": True, "hint": "AI 这一眼没看成，可再试"}
    parsed = _parse_json(raw) or {}
    crit = parsed.get("critiques") or {}
    ok = (
        isinstance(crit, dict)
        and set(crit.keys()) == set(DIMENSIONS)
        and all(str(v).strip() and len(str(v)) <= 30 for v in crit.values())
        and str(parsed.get("weakest") or "") in DIMENSIONS
    )
    if not ok:
        return {**out, "degraded": True, "hint": "AI 这一眼没看成，可再试"}
    return {
        **out,
        "critiques": {k: str(crit[k]).strip()[:30] for k in DIMENSIONS},
        "weakest": parsed["weakest"],
    }
