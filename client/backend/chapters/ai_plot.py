"""章内剧情 · AI 帮写剧情（c-plot-split）：一次出 3 版剧情清单（PRO；生成类）。

- 出 3 版：POST /api/novels/{project_id}/chapters/{chapter_ref}/plot/ai-draw

复用纪律：生成/解析/渲染一律复用 volumes.ai_plan 既有实现（_generate/_parse_json/_render），
本模块只加三版剧情的素材装配、首尾共用装配、名次→字母与句读截断。重试阶梯照拆章
（MAX_ATTEMPTS=3、温度 0.7→0.3），且只认「0 可用版本」触发——判读类问题（名次缺失、
条目超长）一律不重抽（2ccbbf39 教训）。生成预算（每版 4–12 条×≤200 字、三版 ≤9000 字）
与存储预算（chapters.schemas：≤200 字/条、≤12 条）分离。

c-scene-density（2026-10-13，与 prompts 仓 chapter_plot_draw v3 同批）：剧情清单条数
联动本章字数目标——素材恒带【本章字数】（与 write_chapter 同一 clamp 单源），并把
「建议拆几条」按 plot_count_hint 算好直给（<2000 字 4–6 条、2000–2999 字 6–8 条、
3000–3999 字 8–10 条、≥4000 字 10–12 条；上限钉 PLOT_MAX_ITEMS=12 存储单源；
对照表单源在 plot_count_hint，模板只说照建议拆）。此前条数与字数
目标脱钩（2–6 条上限），写作侧再被落点停笔约束，2500 字的章只能写出 ~1300 字。
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import (
    ai_feature,
    get_current_user,
    require_ai_access,
    require_novel_model,
)
from chapters.ai_plan import (
    _global_chapter_no,
    chapter_position_tags,
    position_label,
    resolve_prev_chapter_ending,
)
from chapters.schemas import PLOT_MAX_LEN, clip_sentence
from db import get_db
from filesystem.paths import BOOK_PREFS_PATH
from filesystem.storage import get_storage
from novels.service import get_novel
from prompts import load_layers
from settings.book_prefs_model import clamp_word_target, effective_chapter_word_target
from volumes.ai_plan import _blocks, _book_material, _generate, _parse_json, _render
from workflow.engine import _validate_ref, strip_suffix

router = APIRouter(prefix="/api/novels/{project_id}/chapters/{chapter_ref}/plot", tags=["chapter-plot"])

MAX_ATTEMPTS = 3  # 重试封顶（照拆章）
# 每版 4–12 条（c-scene-density）：首尾共用占 2，中段 2–10。12＝chapters.schemas
# PLOT_MAX_ITEMS 存储单源（前端「最多 12 条」同此）——建议档位一路爬到存储上限封顶，
# 字数才在全域有区分度（2500 与 4000 同上限＝档位饱和，2026-10-13 用户否掉）。
_MAX_MIDDLE = 10

# 抽卡生成预算（c-scene-density 评审定）：满产 ~7200 字≈6.5-9k token，16384 留量；
# 本书模型输出上限 <16k 时（Anthropic 格式 8k 档）首发被打回→降级 8192 重打一次。
_DRAW_BUDGET = 16384
_DRAW_BUDGET_FLOOR = 8192


def _is_max_tokens_rejection(detail: str) -> bool:
    """端点按输出上限打回请求的判据（形状仿 ai_client._is_thinking_rejection）。

    要 max_tokens 字样与上限语义同现才降级——判不准宁可不降：多一次原样重抽
    好于错降 8192 后 12 条档静默截断 JSON（确定性 400 变质量劣化更难排查）。"""
    low = str(detail).lower()
    if "max_tokens" not in low and "max tokens" not in low and "max token" not in low:
        return False
    return any(
        k in low
        for k in ("maximum", "at most", "too large", "limit", ">", "上限", "最大", "不支持")
    )


def plot_count_hint(word_target: int) -> str:
    """字数→建议条数（c-scene-density 单源）：模板只说「照建议拆」，对照表住这里——
    改档位只动本函数。≥2000 字档密度 330–500 字/条、单调爬升，上限钉
    PLOT_MAX_ITEMS=12（线性比率会越过存储上限，锚点不会；最低档受 4 条下限饱和，
    小目标章密度自然更疏，作者可自行删条）。前端 chapterTarget.plotCountHint 同档对拍。"""
    if word_target >= 4000:
        return "10–12 条场景"
    if word_target >= 3000:
        return "8–10 条场景"
    if word_target >= 2000:
        return "6–8 条场景"
    return "4–6 条场景"
_GRADE_BY_RANK = {1: "S", 2: "A", 3: "B"}  # 拍板⑧：模型给名次（1–3），服务端映射字母
_SENT_ENDS = "。！？；…"


class PlotDrawBody(BaseModel):
    """抽卡请求体（c-scene-density 联动）：章纲表单「本章目标字数」填了随请求直发——
    页面显示的建议条数与素材里的字数/建议条数不打劈叉（表单可能未保存）；
    空＝回退本章存值 → 本书偏好「章节默认字数」（clamp 单源同一）。"""

    word_target: int | None = None


def clip_plot_item(text, limit: int = PLOT_MAX_LEN) -> str:
    """条目截断（生成侧）：委托 schemas.clip_sentence（c-field-truncation-alignment 起单源下沉）；
    超预算截到最后一个句读点（末句不腰斩）；全条无句读才硬截。保留函数名供既有调用方。"""
    return clip_sentence(text, limit)


def _sanitize_versions(parsed: dict | None) -> tuple[list[dict], list[str]]:
    """三版装配（首条＋中段＋末条）；可用版本不足 3 由调用方判失败（绝不 2 版将就）。

    只断言最小结构（字符串＋预算内）：越界条目按句读截断不重试，非列表中段丢该版。
    返回 (versions, warnings)。
    """
    warn: list[str] = []
    if not isinstance(parsed, dict):
        return [], ["AI 没有返回可读的结果"]
    entry = str(parsed.get("entry") or "").strip()
    exit_ = str(parsed.get("exit") or "").strip()
    if not entry or not exit_:
        return [], ["首条（接进场）或末条（收结尾）没给出来"]
    middles = parsed.get("middles")
    middles = middles if isinstance(middles, list) else []
    versions: list[dict] = []
    for slot in middles[:3]:
        if not isinstance(slot, list):
            warn.append("有一版的中段不合法，已丢这一版")
            continue
        if len(slot) > _MAX_MIDDLE:
            # 超发剪至上限属判读类处理（不重抽）——剪了要说（评审：用户被告知建议
            # 10–12 条却拿到剪过的清单时，警示区不能是空的）
            warn.append(f"有一版中段超发（{len(slot)} 条），已剪至 {_MAX_MIDDLE} 条")
        items: list[str] = []
        for it in slot[:_MAX_MIDDLE]:
            s = str(it or "").strip()
            if s:
                items.append(s)  # c-field-truncation-alignment 终版：单条完整直通，不截
        versions.append({"items": [entry, *items, exit_]})
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


def _plot_blocks(
    mat: dict, row, entry: dict, position: str = "", word_target: int | None = None
) -> str:
    """素材块：⓪进场（单源取数）→ ⓪'本章位置（首章/开篇期才带，驱动 system 开篇期规则）
    → ⓪''本章字数（c-scene-density，恒带：条数按它给足）→ ①本章三要素
    → ②主线与设定口径（不带伏笔台账，防提前揭）。"""
    parts = [
        f"【进场（本章从哪接）】\n{entry['text']}（{entry['source']}）",
    ]
    if position:
        parts.append(f"【本章位置】\n{position}")
    if word_target:
        parts.append(
            f"【本章字数】\n这一章正文要写满 {word_target} 字，"
            f"建议拆 {plot_count_hint(word_target)}；条数要给足，撑得起这个字数。"
        )
    parts.extend(
        [
            f"【本章概要】\n{(row.summary or '').strip()}",
            f"【碰到的挑战】\n{(row.challenge or '').strip()}",
            f"【本章结尾（收束到这）】\n{(row.ladder_exit or '').strip()}",
            _blocks(mat, hooks=False),
        ]
    )
    if mat.get("world_rules"):
        parts.append(f"【世界铁律】\n{mat['world_rules']}")
    return "\n\n".join(p for p in parts if p)


@router.post("/ai-draw")
@ai_feature("ai-plan")
async def ai_plot_draw(
    project_id: str,
    chapter_ref: str,
    body: PlotDrawBody = Body(default_factory=PlotDrawBody),
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
    global_ch = await _global_chapter_no(db, project.id, row.volume, row.chapter_no)
    position = position_label(global_ch, chapter_position_tags(global_ch, row.chapter_no))
    # 本章字数目标（c-scene-density）：表单现值（body，可能未保存）→ 本章存值 →
    # 本书偏好「章节默认字数」（clamp 单源与 write_chapter 同一）——页面建议条数
    # 与素材【本章字数】恒等。注意越界语义：clamp 是「同落 default」而非逐层回落
    # （body=7000 且本章存值=4000 时结果是 default，不是 4000——评审 2026-10-13 定注释）
    book_prefs = await get_storage().read_yaml(project.root_path, BOOK_PREFS_PATH)
    word_target = clamp_word_target(
        body.word_target if body.word_target is not None else row.word_target,
        default=effective_chapter_word_target(book_prefs),
    )
    _sys_t, _usr_t = load_layers("chapter_plot_draw")
    system = _sys_t
    material_user = _render(
        _usr_t, material_blocks=_plot_blocks(mat, row, entry, position, word_target)
    )
    user_msg = material_user + f"\n\n请给出第 {row.chapter_no} 章剧情清单的 3 版（只输出 JSON）。"

    # 生成预算（c-scene-density 抬参）：每版 4–12 条×≤200 字、三版满产 ~7200 字
    # （entry/exit 共用只出一次）≈6.5-9k token——8192 在 12 条档截断 JSON，端点自抬
    # 参数既有先例（c-plot-split 4096→8192）。降级兜底（架构评审 2026-10-13）：本书
    # 模型输出上限 <16k 时（Anthropic 格式配置的 8k 档）16384 被确定性打回 400→502，
    # 这批模型会从「能抽」变「全挂」——仿 ai_client 思考参数被拒去参重试一次，
    # 降 8192 重打首发（阶梯与循环共用降级后的预算）。
    budget = _DRAW_BUDGET
    try:
        raw, _u = await _generate(
            project, system, user_msg,
            temperature=0.7, db=db, user=user,
            operation="chapter_plot_fill", max_tokens=budget,
        )
    except HTTPException as e:
        if e.status_code != 502 or not _is_max_tokens_rejection(str(e.detail or "")):
            raise
        budget = _DRAW_BUDGET_FLOOR
        raw, _u = await _generate(
            project, system, user_msg,
            temperature=0.7, db=db, user=user,
            operation="chapter_plot_fill", max_tokens=budget,
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
            operation="chapter_plot_fill_retry", max_tokens=budget,
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
