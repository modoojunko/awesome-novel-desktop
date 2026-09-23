"""卷下拆章 · AI 链路（c-chapter-plan-ai）

- 出卡：POST /api/novels/{id}/volumes/{ref}/chapters/ai-directions（PRO；生成类）
- 自检：POST /api/novels/{id}/chapters/ai-selfcheck（免费；只读例外——不挂 require_ai_access；卡面草稿随请求携带）
- 进场：GET  /api/novels/{id}/volumes/{ref}/next-chapter-anchor（全档；手写路径也要进场）

复用纪律（D19）：生成/解析/降级/越纲对拍一律复用 volumes.ai_plan 的既有实现，
本模块只加章级素材装配、四维名次→字母、互斥验收与两个端点，不新写第二套链路。
"""

from __future__ import annotations

import difflib
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user, require_ai_access, require_novel_model
from db import get_db
from novels.service import get_novel
from prompts import load as load_prompt
from volumes.ai_plan import (
    _book_material,
    _degrade_text,
    _entity_warnings,
    _generate,
    _parse_json,
    _render,
)
from volumes.render import volume_outline_text

router = APIRouter(prefix="/api/novels/{project_id}", tags=["chapter-plan-ai"])

SPLIT_AXES = ("加速", "关系", "线索", "代价", "危机", "收束")
DIMENSIONS = ("反转", "递增", "推进", "拉力")  # 四维：反转/冲突层层递增/剧情推进/结尾拉力
STAGE_SET = ("开局铺垫", "冲突初现", "矛盾升级", "重要转折", "高潮爆发", "卷末收束")
SIM_LIMIT = 0.6  # (plot, ending) 相似度阈值（照卷级 SPINE_SIM_LIMIT 先例）
MAX_ATTEMPTS = 3  # 重试预算：3 次尝试后仍不足 2 张 → degraded

_LIMITS = {"title": 12, "plot": 150, "obstacle": 60, "ending": 80, "why": 30, "gap": 30}
_PLACE_SPLIT_RE = re.compile(r"[、，,；;。\n\r\t 　]+")
_ACT_MAX_LINES, _ACT_MAX_LEN = 4, 60


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

        prose = str(assemble_chapter(prev).get("prose") or "").strip()
        paras = [p.strip() for p in prose.split("\n") if p.strip()]
        if paras:
            return {
                "text": paras[-1][:200],
                "source": f"第{prev.chapter_no}章 · 取自正文结尾（写到那里之后，这里以实际为准）",
            }
    exit_text = (prev.ladder_exit or "").strip()
    return {
        "text": exit_text or "（上一章还没写结尾）",
        "source": f"第{prev.chapter_no}章 · 拟定，取自章纲落点",
    }


# ═══════════════ 素材装配（①→⑧；预算见 prompt-draft §5） ═══════════════


async def _chapter_material(db, project, vol, ch_no: int) -> dict:
    mat = await _book_material(db, project, with_hooks=False)  # 不给伏笔台账（防"提前揭"）
    entry = await resolve_prev_chapter_ending(db, project, vol, ch_no)
    from repositories import chapter_repo

    rows = sorted(
        [c for c in await chapter_repo.list_by_volume(db, vol.id) if not c.ghost_of],
        key=lambda c: c.chapter_no,
    )
    done = [
        f"第{c.chapter_no}章 {c.title or ''}｜{(c.summary or '').strip()[:40]}｜{c.plot_stage or '（未定阶段）'}"
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
    except Exception:  # noqa: BLE001 — 世界设定读不到不影响出卡
        pass
    return out


def _blocks_chapter(mat: dict) -> str:
    """①进场 → ②卷纲四问 → ③已拆章节 → ④配额/末章 → ⑤题材 → ⑥人物 → ⑦铁律 → ⑧上一章一行。"""
    parts = [f"【进场（本章从哪接）】\n{mat['entry']['text']}（{mat['entry']['source']}）"]
    if mat["vol_outline"]:
        parts.append(f"【本卷卷纲（四问）】\n{mat['vol_outline']}")
    if mat["done_chapters"]:
        parts.append("【已经拆过的章】\n" + "\n".join(mat["done_chapters"][-12:]))
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
    if mat["world_rules"]:
        parts.append(f"【世界铁律】\n{mat['world_rules']}")
    if mat["prev_line"]:
        parts.append(f"【上一章发生了什么】\n{mat['prev_line']}")
    return "\n\n".join(parts)


# ═══════════════ 出卡校验：字段/闭集/依据可寻/同质 ═══════════════


def _fit(v, key: str) -> str:
    return str(v or "").strip()[:_LIMITS[key]]


def _acts(v) -> list[str]:
    out = [str(x).strip()[:_ACT_MAX_LEN] for x in (v if isinstance(v, list) else []) if str(x).strip()]
    return out[:_ACT_MAX_LINES]


def _similar(a: dict, b: dict) -> bool:
    ra = f"{a.get('plot', '')}{a.get('ending', '')}"
    rb = f"{b.get('plot', '')}{b.get('ending', '')}"
    return difflib.SequenceMatcher(None, ra, rb).ratio() > SIM_LIMIT


def _sanitize_directions(parsed: dict | None) -> tuple[list[dict], list[str]]:
    """逐卡兜底：字段/闭集不合法 → 丢卡；轴与 diff 不一致/未知轴 → 丢卡（不改写）。
    返回 (可用卡, warnings)。"""
    warn: list[str] = []
    if not isinstance(parsed, dict):
        return [], ["出卡不是合法 JSON"]
    diff = parsed.get("diff")
    diff = diff if isinstance(diff, dict) else {}  # 模型拍平（数组/字符串）时按缺失处理，不 500
    axes_raw = diff.get("axes")
    axes = [str(a).strip() for a in (axes_raw if isinstance(axes_raw, list) else [])]
    cards_in = parsed.get("directions")
    if not isinstance(cards_in, list):
        return [], ["directions 缺失"]
    out: list[dict] = []
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
        if any(c["axis"] == axis for c in out):
            warn.append(f"第 {i + 1} 张 axis「{axis}」与前面某张重复，已丢弃")
            continue
        out.append(
            {
                "axis": axis,
                "title": _fit(c.get("title"), "title"),
                "plot": plot,
                "obstacle": _fit(c.get("obstacle"), "obstacle"),
                "ending": ending,
                "acts": _acts(c.get("acts")),
                "stage": stage,
                "cast": [str(x).strip()[:20] for x in (c.get("cast") or []) if str(x).strip()][:6],
                "factions": [str(x).strip()[:20] for x in (c.get("factions") or []) if str(x).strip()][:6],
                "places": [str(x).strip()[:20] for x in (c.get("places") or []) if str(x).strip()][:6],
                "why": _fit(c.get("why"), "why"),
                "gap": _fit(c.get("gap"), "gap"),
            }
        )
    # 同质：保留先出现者（复核一次的动作由端点按 attempt 控制）
    kept: list[dict] = []
    for c in out:
        if any(_similar(c, k) for k in kept):
            warn.append(f"「{c['title'] or c['axis']}」与前面某张太像，已丢弃")
            continue
        kept.append(c)
    return kept, warn


def _reasons_verifiable(parsed: dict, cards: list[dict]) -> bool:
    """每维第一名的依据必须能在得胜卡对应字段里逐字找到（找不到判不合法 → 降级）。"""
    ranks_raw, reasons_raw = parsed.get("ranks"), parsed.get("reasons")
    ranks = ranks_raw if isinstance(ranks_raw, dict) else {}
    reasons = reasons_raw if isinstance(reasons_raw, dict) else {}
    field_of = {"反转": ("plot", "ending"), "递增": ("obstacle", "plot"), "推进": ("plot", "ending"), "拉力": ("ending",)}
    for dim in DIMENSIONS:
        rs = ranks.get(dim)
        if not isinstance(rs, list) or len(rs) != len(cards):
            return False
        reason = str(reasons.get(dim) or "").strip()
        # 依据 ≤20 字（spec 与 tasks 3.3 的预算口径）
        if not reason or len(reason) > 20:
            return False
        firsts = [i for i, r in enumerate(rs) if r == 1]
        if len(firsts) == 1:  # 唯一第一名 → 依据必须可寻
            i = firsts[0]
            fields = field_of[dim]
            hay = "".join(str(cards[i].get(f) or "") for f in fields)
            if reason not in hay:
                return False
    return True


def _as_dict(parsed: dict | None, key: str) -> dict:
    """模型把该键拍平成数组/字符串时按空对象处理（不 500；sanitize 层为这类不合形而存在）。"""
    v = (parsed or {}).get(key)
    return v if isinstance(v, dict) else {}


def _as_str_list(parsed: dict | None, key: str, limit: int) -> list[str]:
    v = (parsed or {}).get(key)
    if not isinstance(v, list):
        return []  # 字符串会被逐字符切碎——非 list 一律当空
    return [str(x).strip()[:limit] for x in v if str(x).strip()]


def _as_text(parsed: dict | None, key: str, limit: int) -> str:
    v = (parsed or {}).get(key)
    return (v if isinstance(v, str) else "").strip()[:limit]


def _grades(parsed: dict, n: int) -> list[str]:
    """四维名次 → S/A/B：唯一第一名才计入；≥3 → S，1–2 → A，0 → B（至多一张 S）。"""
    ranks_raw = parsed.get("ranks")
    ranks = ranks_raw if isinstance(ranks_raw, dict) else {}
    counts = [0] * n
    for dim in DIMENSIONS:
        rs = ranks.get(dim)
        if not isinstance(rs, list) or len(rs) != n:
            continue
        firsts = [i for i, r in enumerate(rs) if r == 1]
        if len(firsts) == 1:
            counts[firsts[0]] += 1
    return ["S" if c >= 3 else "A" if c >= 1 else "B" for c in counts]


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
    from workflow.engine import strip_suffix

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol_no = int(strip_suffix(vol_ref).replace("vol-", ""))
    vol = await volume_repo.get_by_volume_no(db, project.id, vol_no)
    if vol is None:
        raise HTTPException(404, "Volume not found")
    rows = [c for c in await chapter_repo.list_by_volume(db, vol.id) if not c.ghost_of]
    entry = await resolve_prev_chapter_ending(db, project, vol, len(rows) + 1)
    # 章号/卷号单源：卡面标题「拆第N章」、行号 0N、kicker「第X卷」都取这里，
    # 前端不再自造（曾用常量占位 → 每章都写「拆第一章」）
    return {"ok": True, **entry, "next_no": len(rows) + 1, "vol_no": vol.volume_no}


@router.post("/volumes/{vol_ref}/chapters/ai-directions")
async def ai_chapter_directions(
    project_id: str,
    vol_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),  # 生成类归 PRO
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """同一章的 3 个互斥剧情方向（不落库）。名次在模型侧、字母在服务端算。"""
    from repositories import chapter_repo, volume_repo
    from workflow.engine import strip_suffix

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    vol_no = int(strip_suffix(vol_ref).replace("vol-", ""))
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
    system = _render(
        load_prompt("chapter_split"),
        material_blocks=_blocks_chapter(mat),
        split_axes="／".join(SPLIT_AXES),
        plot_stages="／".join(STAGE_SET),
    )
    user_msg = f"请给出第 {ch_no} 章的 3 个剧情方向（只输出 JSON）。"
    raw, _u = await _generate(project, system, user_msg, temperature=0.7, db=db, user=user, operation="chapter_directions")
    parsed = _parse_json(raw)
    cards, warn = _sanitize_directions(parsed)
    attempts = 1
    # 不足 2 张**或名次依据不可寻** → 重试（原因喂回＋降温）；共最多 MAX_ATTEMPTS 次
    # （依据不可寻 = 该维第一名判不合法 → 按 spec 走降级阶梯，不得照旧出 S/A/B）
    bad_reasons = bool(parsed) and not _reasons_verifiable(parsed, cards)
    while (len(cards) < 2 or bad_reasons) and attempts < MAX_ATTEMPTS:
        cause = "；".join(warn[:2]) or ("的名次依据在得胜卡里找不到" if bad_reasons else "的方向不合法")
        retry_system = system + f"\n\n（上一次{cause}。）"
        raw, _u = await _generate(
            project, retry_system, "请给出 2 到 3 个剧情方向（只输出 JSON）。",
            temperature=0.3, db=db, user=user, operation="chapter_directions_retry",
        )
        parsed = _parse_json(raw)
        cards, warn = _sanitize_directions(parsed)
        bad_reasons = bool(parsed) and not _reasons_verifiable(parsed, cards)
        attempts += 1
    if len(cards) < 2:
        return {
            "ok": True, "degraded": True,
            "text": _degrade_text(raw),
            "hint": "出卡失败，可重试，或自己写这一章",
            "entry": mat["entry"],
        }
    # 走完阶梯仍不可寻：出卡照给（不拦作者），但**不给等级**——名次判不合法就不该落字母
    if bad_reasons:
        warn.append("名次依据在得胜卡字段里找不到，本次不出等级")
    grades = [] if bad_reasons else _grades(parsed or {}, len(cards))
    known = mat["known_entities"]
    all_cast = [n for c in cards for n in c["cast"]]
    all_factions = [n for c in cards for n in c["factions"]]
    all_places = [n for c in cards for n in c["places"]]
    # 已知地点侧＝章纲「地点」字段 ∪ 世界舞台里圈出的地名（_known_places）
    warn.extend(_entity_warnings(all_cast, all_factions, known | mat["known_places"], all_places))
    return {
        "ok": True,
        "entry": mat["entry"],
        "is_final": mat["is_final"],
        "quota_left": mat["quota_left"],
        "diff": _as_dict(parsed, "diff"),
        "directions": cards,
        "grades": grades,
        "ranks": _as_dict(parsed, "ranks"),
        "reasons": _as_dict(parsed, "reasons"),
        "checks": _as_str_list(parsed, "checks", 40)[:3],
        "note": _as_text(parsed, "note", 60),
        "warnings": warn[:5],
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
        "acts": data.get("chapter_acts") or [],
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
    acts: list[str] = []
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
    vol_no = int(strip_suffix(body.vol_ref).replace("vol-", ""))
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
    system = _render(
        load_prompt("chapter_selfcheck"),
        entry=entry["text"] + "（" + entry["source"] + "）",
        prev_line=prev_line or "（这是第一卷第一章）",
        plot=_fit(body.plot, "plot"),
        obstacle=_fit(body.challenge, "obstacle"),
        ending=_fit(body.ending, "ending"),
        acts="\n".join(f"- {a}" for a in body.acts[:_ACT_MAX_LINES]) or "（还没写）",
        stage=body.stage if body.stage in STAGE_SET else "（未定）",
    )
    out: dict = {
        "ok": True,
        "link": {"ok": link_ok, "text": "本章进场已自动接上上一章结尾" if link_ok else "上一章结尾已变化"},
        "quota": {"ok": not over, "text": quota},
    }
    try:
        raw, _u = await _generate(
            project, system, "请按四维给这一章的短评，并点出最弱一维（只输出 JSON）。",
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
