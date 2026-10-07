"""剧情推演（plot-sim，storyline.html 四期尾）：从上一章结尾，按回合走一遍本章。

策略：AI 按章纲＋上一章结尾生成 2-4 个回合（每回合含顺/拗两条走法结果）；
调用失败或产物不合格时回落原型同款确定性推演（剧情条目环＋模板走法），
保证弹窗永远可用。产物只返回不落库；「收进章纲」由前端把走法行**追加为本章
一条剧情条目**（c-og-slim-v2：原落点「预期策略」随该字段退役）。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from auth_local.deps import ai_feature, require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from prompts import load_layers
from workflow.engine import _validate_ref, load_chapter
from write.chapter_writer import _prev_chapter_ref, strip_code_fences

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/simulate", tags=["plot-sim"]
)

MAX_ROUNDS = 4
_DEFAULT_BEAT = "把这一章的核心任务往前推一格"


def _s(v, limit: int = 300) -> str:
    return str(v or "").strip()[:limit]


def _str_list(v, limit: int = 8) -> list[str]:
    if not isinstance(v, list):
        return []
    return [str(x).strip() for x in v if str(x).strip()][:limit]


def _moves(who: str, ok: str, warn: str) -> list[dict]:
    """两条走法（原型 simMovesOf 口径）：k 顺/拗，label 角色动作，out 结果句。"""
    return [
        {"k": "顺", "tone": "ok", "label": f"{who}顺着当前节奏动手", "out": ok},
        {"k": "拗", "tone": "warn", "label": f"{who}先被外力打断一下", "out": warn},
    ]


def _parse_rounds(text: str) -> list[dict]:
    """AI 产物清洗：beat/ok/warn 三者缺一即丢整回合；上限 MAX_ROUNDS。"""
    if not text:
        return []
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except Exception:  # noqa: BLE001 — 产物损坏按无产物处理（走兜底）
        return []
    items = data.get("rounds") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        beat = _s(item.get("beat"), 200)
        ok = _s(item.get("ok"))
        warn = _s(item.get("warn"))
        if not beat or not ok or not warn:
            continue
        who = _s(item.get("who"), 50)
        out.append({
            "beat": beat,
            "who": who,
            "place": _s(item.get("place"), 100),
            "time": _s(item.get("time"), 100),
            "at": _s(item.get("at"), 200),
            "shift": _s(item.get("shift")),
            "ok": ok,
            "warn": warn,
        })
        if len(out) >= MAX_ROUNDS:
            break
    return out


def _fallback_rounds(
    outline: dict,
    memo: dict,
    emotional: dict,
    cast: list[str],
    entry: str,
    plot_items: list[str] | None = None,
) -> list[dict]:
    """原型 simBuild 的确定性推演：剧情条目环＋模板走法（AI 不可用时的保底）。

    c-og-slim-v2：环源由「关键事件」改为「剧情条目」（章纲主干）；条目空则回落概要，
    连概要也没有才用固定句。
    """
    beats = _str_list(plot_items) or []
    if not beats:
        summary = _s(outline.get("summary"), 200)
        beats = [summary] if summary else []
    if not beats:
        beats = [_DEFAULT_BEAT]
    beats = beats[:MAX_ROUNDS]

    payoffs = memo.get("payoff_plan") if isinstance(memo.get("payoff_plan"), dict) else {}
    suspense = _str_list(payoffs.get("must_hold"))
    mood = _s((emotional or {}).get("primary_mood"), 50) or "紧张"
    change = _str_list(memo.get("required_changes"), 1)
    who_pool = cast or ["主角"]

    rounds: list[dict] = []
    for i, beat in enumerate(beats):
        last = i == len(beats) - 1
        who = who_pool[i % len(who_pool)]
        if i == 0:
            at = f"承上：{entry}"
        elif last:
            at = "推向本章结尾"
        else:
            at = "继续往下走"
        if last:
            tail_txt = change[0] if change else (_s(outline.get("summary"), 200) or "本章收束")
        elif suspense:
            tail_txt = f"维持悬念：{suspense[i] if i < len(suspense) else suspense[0]}"
        else:
            # （c-og-slim-v2：原 `elif strategy` 分支随「预期策略」退役——
            #   赋值已删而分支未删曾致兜底 NameError、端点 500）
            tail_txt = "局势往前一格"
        suspend_tail = (
            f"「{suspense[0]}」被压得更紧" if suspense else "悬念再多压一层"
        )
        rounds.append({
            "beat": beat,
            "who": who,
            # place/time 的来源（章纲 location/time）已随 c-og-slim-v2 退役：兜底恒空串
            "place": "",
            "time": "",
            "at": at,
            "shift": tail_txt,
            "ok": f"事件按章纲落地，主情绪停在「{mood}」，不多加波折。",
            "warn": f"多出一次波折，{suspend_tail}，收束前再拉回主线。",
        })
    return rounds


def _material(chapter: dict, prev: dict | None, entry: str) -> str:
    outline = chapter.get("outline") if isinstance(chapter.get("outline"), dict) else {}
    memo = chapter.get("memo") if isinstance(chapter.get("memo"), dict) else {}
    emotional = (
        chapter.get("emotional_design")
        if isinstance(chapter.get("emotional_design"), dict)
        else {}
    )
    blocks: list[str] = []
    chapter_lines = [f"概要：{_s(outline.get('summary'), 300) or '（未填）'}"]
    # c-og-slim-v2：关键事件/场景/预期策略退役，素材改取剧情条目
    items = _str_list(chapter.get("plot_items"), 12)
    if items:
        chapter_lines.append("剧情条目：\n" + "\n".join(f"- {x}" for x in items))
    cast = _str_list(outline.get("characters"))
    if cast:
        chapter_lines.append("出场角色：" + "、".join(cast))
    if _s(chapter.get("challenge")):
        chapter_lines.append("碰到的挑战：" + _s(chapter.get("challenge"), 150))
    if _s(chapter.get("plot_stage")):
        chapter_lines.append("本章在卷剧情里的位置：" + _s(chapter.get("plot_stage"), 20))
    if _s(emotional.get("primary_mood")):
        chapter_lines.append("主情绪：" + _s(emotional.get("primary_mood"), 50))
    payoffs = memo.get("payoff_plan") if isinstance(memo.get("payoff_plan"), dict) else {}
    suspense = _str_list(payoffs.get("must_hold"))
    if suspense:
        chapter_lines.append("必须维持悬念：" + "；".join(suspense))
    changes = _str_list(memo.get("required_changes"))
    if changes:
        chapter_lines.append("必须完成的变化：" + "；".join(changes))
    blocks.append("【本章章纲】\n" + "\n".join(chapter_lines))

    prev_lines = [f"结尾处境：{entry}"]
    if prev:
        p_outline = prev.get("outline") if isinstance(prev.get("outline"), dict) else {}
        if _s(p_outline.get("summary")):
            prev_lines.append("上一章概要：" + _s(p_outline.get("summary"), 300))
        p_items = _str_list(prev.get("plot_items"), 4)
        if p_items:
            prev_lines.append("上一章剧情：" + "；".join(p_items))
        # 截断方向：先放宽到全书量级再取尾 120——直接默认截断会把「结尾摘录」摘成中段
        prose = _s(prev.get("prose"), 100000) or ""
        if prose:
            prev_lines.append("上一章正文结尾摘录：" + prose[-120:])
    blocks.append("【上一章结尾】\n" + "\n".join(prev_lines))
    return "\n\n".join(blocks)


@router.post("")
@ai_feature("ai-plot")
async def plot_simulate(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """按回合推演本章：AI 产物不合格时回落确定性推演（source 字段标注来源）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)

    chapter = await load_chapter(project.root_path, chapter_ref) or {}
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    outline = chapter.get("outline") if isinstance(chapter.get("outline"), dict) else {}
    memo = chapter.get("memo") if isinstance(chapter.get("memo"), dict) else {}
    emotional = (
        chapter.get("emotional_design")
        if isinstance(chapter.get("emotional_design"), dict)
        else {}
    )
    cast = _str_list(outline.get("characters"))

    # 上一章结尾（承上起点）：正文末段优先，无正文回退章纲概要
    vol_no = chapter.get("volume") if isinstance(chapter.get("volume"), int) else None
    ch_no = chapter.get("chapter") if isinstance(chapter.get("chapter"), int) else None
    prev = None
    prev_label = "开书"
    if vol_no and ch_no:
        prev_ref = await _prev_chapter_ref(project.root_path, vol_no, ch_no)
        if prev_ref:
            prev = await load_chapter(project.root_path, prev_ref) or None
            if prev:
                prev_label = f"第 {prev.get('chapter', '?')} 章"
    if prev:
        prose = _s(prev.get("prose"), 100000)
        p_outline = prev.get("outline") if isinstance(prev.get("outline"), dict) else {}
        entry = (prose[-60:] if prose else "") or _s(p_outline.get("summary"), 300) or "上一章就此收束。"
    else:
        entry = "开书第一章：全书设定还是空白，这一章从零长出来。"

    change = _str_list(memo.get("required_changes"), 1)
    exit_text = change[0] if change else (_s(outline.get("summary"), 200) or "本章收束")

    # ── AI 尝试（失败不抛错：回落确定性推演）───────────────────────────
    rounds: list[dict] = []
    source = "fallback"
    model = "haiku"
    usage: dict = {}
    try:
        client = await get_ai_client_for_novel(project.id)
    except Exception:  # noqa: BLE001 — 模型未就绪：调用未发生，不记账
        client = None
    if client is not None:
        material = _material(chapter, prev, entry)
        _sys_t, _usr_t = load_layers("plot_sim")
        system = _sys_t
        _user = _usr_t.format(material=material)
        try:
            raw = await client.chat(
                model=model,
                max_tokens=1600,
                system=system,
                messages=[{"role": "user", "content": _user}],
                operation="plot_sim",
                usage=usage,
            )
        except AITimeoutError:
            from api_configs.usage import record_usage

            await record_usage(
                db, user_id=user["id"], project_id=project.id,
                chapter_id=chapter_ref, operation="plot_sim_fail", model=model,
                tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
                force=True,
            )
            await db.commit()
            raw = ""
        except Exception:  # noqa: BLE001 — 模型/网络错误：同上回落
            from api_configs.usage import record_usage

            await record_usage(
                db, user_id=user["id"], project_id=project.id,
                chapter_id=chapter_ref, operation="plot_sim_fail", model=model,
                tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
                force=True,
            )
            await db.commit()
            raw = ""

        if raw:
            # 记账先于解析：调用已完成（钱已花），产物不合格也留痕
            # （独立于调用 try——记账异常不得被误判为调用失败而二次记账）
            from api_configs.usage import record_usage

            await record_usage(
                db,
                user_id=user["id"],
                project_id=project.id,
                chapter_id=chapter_ref,
                operation="plot_sim",
                model=model,
                tokens_in=usage.get("tokens_in", 0),
                tokens_out=usage.get("tokens_out", 0),
            )
            await db.commit()
            rounds = _parse_rounds(strip_code_fences(raw))
            if rounds:
                source = "ai"

    if not rounds:
        rounds = _fallback_rounds(
            outline,
            memo,
            emotional,
            cast,
            entry,
            _str_list(chapter.get("plot_items"), 12),
        )

    # 回合编号 + 走法结构化（label/out 由后端定形，前端只做展示与选择）
    out_rounds = []
    who_pool = cast or ["主角"]
    for i, r in enumerate(rounds):
        who = r.get("who") or who_pool[i % len(who_pool)]
        out_rounds.append({
            "n": i + 1,
            "beat": r["beat"],
            "who": who,
            "place": r.get("place", ""),
            "time": r.get("time", ""),
            "at": r.get("at", ""),
            "shift": r.get("shift", ""),
            "moves": _moves(who, r["ok"], r["warn"]),
        })

    return {
        "ok": True,
        "source": source,
        "entry": entry,
        "exit": exit_text,
        "prev_label": prev_label,
        "cast": cast,
        "rounds": out_rounds,
    }
