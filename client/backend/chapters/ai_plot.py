"""章内剧情 · AI 帮写剧情（c-plot-split）：一次出 3 版剧情清单（PRO；生成类）。

- 出 3 版：POST /api/novels/{project_id}/chapters/{chapter_ref}/plot/ai-draw

复用纪律：生成/解析/渲染一律复用 volumes.ai_plan 既有实现（_generate/_parse_json/_render），
本模块只加三版剧情的素材装配、首尾共用装配、名次→字母与句读截断。重试阶梯照拆章
（MAX_ATTEMPTS=3、温度 0.7→0.3），且只认「0 可用版本」触发——判读类问题（名次缺失、
条目超长）一律不重抽（2ccbbf39 教训）。生成预算（每版 2–6 条×≤200 字、三版 ≤4000 字）
与存储预算（chapters.schemas：≤200 字/条、≤12 条）分离。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import get_current_user, require_ai_access, require_novel_model
from chapters.ai_plan import resolve_prev_chapter_ending
from chapters.schemas import PLOT_MAX_LEN
from db import get_db
from novels.service import get_novel
from prompts import load as load_prompt
from volumes.ai_plan import _blocks, _book_material, _generate, _parse_json, _render
from workflow.engine import _validate_ref, strip_suffix

router = APIRouter(prefix="/api/novels/{project_id}/chapters/{chapter_ref}/plot", tags=["chapter-plot"])

MAX_ATTEMPTS = 3  # 重试封顶（照拆章）
_MAX_MIDDLE = 4  # 每版 2–6 条：首尾共用占 2，中段 0–4 条
_GRADE_BY_RANK = {1: "S", 2: "A", 3: "B"}  # 拍板⑧：模型给名次（1–3），服务端映射字母
_SENT_ENDS = "。！？；…"


def clip_plot_item(text, limit: int = PLOT_MAX_LEN) -> str:
    """条目截断（生成侧）：超预算截到最后一个句读点（末句不腰斩）；全条无句读才硬截。

    与存储预算的静默夹（chapters.schemas.normalize_plot_items）同值不同法：
    生成产物要保结尾句完整，存储兜底只保预算。
    """
    t = str(text or "").strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    for i in range(len(cut) - 1, -1, -1):
        if cut[i] in _SENT_ENDS:
            return cut[: i + 1]
    return cut


def _sanitize_versions(parsed: dict | None) -> tuple[list[dict], list[str]]:
    """三版装配（首条＋中段＋末条）；可用版本不足 3 由调用方判失败（绝不 2 版将就）。

    只断言最小结构（字符串＋预算内）：越界条目按句读截断不重试，非列表中段丢该版。
    返回 (versions, warnings)。
    """
    warn: list[str] = []
    if not isinstance(parsed, dict):
        return [], ["AI 没有返回可读的结果"]
    entry = clip_plot_item(parsed.get("entry"))
    exit_ = clip_plot_item(parsed.get("exit"))
    if not entry or not exit_:
        return [], ["首条（接进场）或末条（收结尾）没给出来"]
    middles = parsed.get("middles")
    middles = middles if isinstance(middles, list) else []
    clipped = 0
    versions: list[dict] = []
    for slot in middles[:3]:
        if not isinstance(slot, list):
            warn.append("有一版的中段不合法，已丢这一版")
            continue
        items: list[str] = []
        for it in slot[:_MAX_MIDDLE]:
            s = str(it or "").strip()
            if not s:
                continue
            c = clip_plot_item(s)
            if len(c) < len(s):
                clipped += 1
            items.append(c)
        versions.append({"items": [entry, *items, exit_]})
    if clipped:
        warn.append(f"有 {clipped} 条超过 200 字，已截到最后一个句号")
    return versions, warn[:5]


def _grades(parsed: dict | None, n: int) -> list[str]:
    """名次→字母（拍板⑧）：缺名次/非法/并列 → 该版不出角标，卡照出不重抽。"""
    ranks_raw = parsed.get("ranks") if isinstance(parsed, dict) else None
    ranks: list[int | None] = []
    for i in range(n):
        r = ranks_raw[i] if isinstance(ranks_raw, list) and i < len(ranks_raw) else None
        if isinstance(r, bool):
            r = None
        elif isinstance(r, str) and r.strip().isdigit():
            r = int(r.strip())
        ranks.append(r if isinstance(r, int) and r in _GRADE_BY_RANK else None)
    return [_GRADE_BY_RANK[r] if r is not None and ranks.count(r) == 1 else "" for r in ranks]


def _plot_blocks(mat: dict, row, entry: dict) -> str:
    """素材块：⓪进场（单源取数）→ ①本章三要素 → ②主线与设定口径（不带伏笔台账，防提前揭）。"""
    parts = [
        f"【进场（本章从哪接）】\n{entry['text']}（{entry['source']}）",
        f"【本章概要】\n{(row.summary or '').strip()}",
        f"【碰到的挑战】\n{(row.challenge or '').strip()}",
        f"【本章结尾（收束到这）】\n{(row.ladder_exit or '').strip()}",
        _blocks(mat, hooks=False),
    ]
    if mat.get("world_rules"):
        parts.append(f"【世界铁律】\n{mat['world_rules']}")
    return "\n\n".join(p for p in parts if p)


@router.post("/ai-draw")
async def ai_plot_draw(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),  # 生成类归 PRO
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """一次出 3 版剧情清单（不落库）。名次在模型侧、字母在服务端算。"""
    from repositories import chapter_repo

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    _validate_ref(chapter_ref)
    row = await chapter_repo.get_by_ref(db, project.id, strip_suffix(chapter_ref))
    if row is None:
        raise HTTPException(404, "Chapter not found")
    # 发起门槛：概要/挑战/结尾三要素齐备（拍板⑦维持三样）
    missing = [
        label
        for label, val in (
            ("一句话概要", row.summary),
            ("碰到的挑战", row.challenge),
            ("章末落点", row.ladder_exit),
        )
        if not str(val or "").strip()
    ]
    if missing:
        raise HTTPException(422, f"这一章还没填全（{'、'.join(missing)}）——补齐后再让 AI 写剧情")

    mat = await _book_material(db, project, with_hooks=False)  # 不给伏笔台账（防提前揭）
    entry = await resolve_prev_chapter_ending(db, project, row.volume, row.chapter_no)
    system = _render(load_prompt("chapter_plot_draw"), material_blocks=_plot_blocks(mat, row, entry))
    user_msg = f"请给出第 {row.chapter_no} 章剧情清单的 3 版（只输出 JSON）。"

    raw, _u = await _generate(
        project, system, user_msg,
        temperature=0.7, db=db, user=user, operation="chapter_plot_fill", max_tokens=8192,
    )
    parsed = _parse_json(raw)
    versions, warn = _sanitize_versions(parsed)
    attempts = 1
    # 重试只认「0 可用版本」（结构性失败）；凑不满 3 版不重抽——直接判失败交给「再试一次」，
    # 绝不 2 版将就（拍板⑤）
    while not versions and attempts < MAX_ATTEMPTS:
        cause = "；".join(warn[:2]) or "输出不可解析"
        raw, _u = await _generate(
            project, system + f"\n\n（上一次{cause}。）", user_msg,
            temperature=0.3, db=db, user=user,
            operation="chapter_plot_fill_retry", max_tokens=8192,
        )
        parsed = _parse_json(raw)
        versions, warn = _sanitize_versions(parsed)
        attempts += 1
    if len(versions) < 3:
        return {"ok": False, "versions": [], "grades": [], "warnings": warn[:5]}
    return {
        "ok": True,
        "versions": versions,
        "grades": _grades(parsed or {}, len(versions)),
        "warnings": warn[:5],
    }
