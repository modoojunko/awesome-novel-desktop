"""章际衔接修复（c-seam-refill）：知前后补中间——draft 三选一（SSE 流式）。

- `POST …/seam-refill/draft {para_count?, findings?, rejected?}`：
  读「前」（上章结尾原文）与「后」（断点后正文＋章末落点），起草 3 版互斥的开头重写
  方案（直承/过渡/重排）。SSE 事件：phase(assemble/model) → chunk(chars 计数) →
  done{options} ｜ error{error}。
- draft 不落库（关弹窗即弃）；应用＝前端按段号替换后走既有 PUT prose 链（作者确认制，
  版本快照即找回，不建 ghost）。
- 门控与计费：ai-generate ＋ PRO／本书模型双门控；operation=`seam_refill_draft(_fail)`。
- 输出校验链（W3）：echo 凭证归一化子串对拍（超 20 字仅告警不重试，W1）→ 逐版判负
  （边界标记/契约字样；与前/后文归一化公共子串 ≥15 字；与已否决 120 字预览公共子串
  ≥30 字，W2）→ 末尾与后文首句半句重叠剪尾。不符带错误信息重试一次（失败原因＋上一轮
  各版前 120 字回注【已否决方案】），再失败 error 事件；存活版 1-3 版照常 done。
- 模板 `seam_refill.prompt`（<<>> 顺序 replace，禁 str.format——契约含字面花括号）。
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import ai_feature, require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from prompts import load_layers
from settings.render import style_section
from workflow.engine import _validate_ref, load_chapter
from write.chapter_writer import (
    _story_state_block,
    build_chapter_context,
    strip_code_fences,
)

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/seam-refill",
    tags=["seam-refill"],
)

logger = logging.getLogger("uvicorn.error")

MAX_FINDINGS = 8
STRATEGIES = [("direct", "直承"), ("transition", "过渡"), ("reframe", "重排")]

# 输出校验链阈值（W3/W1/W2，提示词终审 2026-10 定稿口径）：
PREVIEW_CHARS = 120  # 已否决方案注入模板与判负对拍共用前缀长度（W2：模型只见过前 120 字）
ECHO_MAX_CHARS = 20  # W1：echo 超 20 字仅 logger.warning 不重试（模型保真优先，硬卡烧假重试）
SEAM_CLIP_MIN = 6  # 版末与后文首句归一化重叠 ≥6 字才剪尾（半句重叠；更短视为巧合）
REPEAT_MIN_SEAM = 15  # 版文与前/后文归一化公共子串 ≥15 字判负（污染）
REPEAT_MIN_REJECTED = 30  # 版文与已否决预览公共子串 ≥30 字判负（对拍范围＝注入预览，W2）
POLLUTION_MARKERS = ("```", "<<", ">>", "##", "输出契约")  # 边界标记行/代码围栏/契约字样


class RejectedVersion(BaseModel):
    approach: str = Field(default="", max_length=20)
    text: str = Field(default="", max_length=4000)


class SeamDraftBody(BaseModel):
    para_count: int = Field(default=3, ge=1, le=6)
    findings: list[dict] = Field(default_factory=list)
    rejected: list[RejectedVersion] = Field(default_factory=list)


def _paras(text: str) -> list[str]:
    return [p for p in (text or "").split("\n") if p.strip()]


def _parse_options(raw: str) -> list[dict] | None:
    """宽松解析三版 JSON（strip_code_fences＋花括号截取口径，同 _parse_findings）。

    校验：恰 3 版、approach ∈ {直承,过渡,重排} 且互不重复、text 非空。
    """
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:  # noqa: BLE001
        return None
    versions = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(versions, list) or len(versions) != len(STRATEGIES):
        return None
    labels = dict(STRATEGIES)
    axis_keys = {label: key for key, label in STRATEGIES}  # 模板契约＝中文轴名（直承/过渡/重排）
    seen: set[str] = set()
    options: list[dict] = []
    for v in versions:
        if not isinstance(v, dict):
            return None
        approach = str(v.get("approach", "")).strip()
        text = str(v.get("text", "")).strip()
        note = str(v.get("note", "")).strip()[:60]
        key = axis_keys.get(approach) or (approach if approach in labels else None)
        if not key or not text or key in seen:
            return None
        seen.add(key)
        options.append({"key": key, "label": labels[key], "how": note, "text": text})
    return options


def _norm(s: str) -> str:
    """folded 归一化：去全部空白＋全角引号统一直引号（同前端 PolishWizard 折叠口径）。"""
    return (
        "".join(str(s or "").split())
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _longest_common_substring_len(a: str, b: str) -> int:
    """最长公共子串长度（二分＋k-gram 集合，切片散列走 C 级，免去纯 Python DP）。"""
    if not a or not b:
        return 0
    lo, hi, best = 1, min(len(a), len(b)), 0
    while lo <= hi:
        mid = (lo + hi) // 2
        grams = {a[i : i + mid] for i in range(len(a) - mid + 1)}
        if any(b[j : j + mid] in grams for j in range(len(b) - mid + 1)):
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


_SENT_END = "。！？!?"


def _first_sentence(norm_text: str) -> str:
    """归一化文本的首句（含句末标点；无句末标点则全文）。"""
    for i, ch in enumerate(norm_text):
        if ch in _SENT_END:
            return norm_text[: i + 1]
    return norm_text


def _tail_prefix_overlap(norm_tail: str, head: str) -> int:
    """norm_tail 末尾与 head 开头的最大重叠长度（半句重叠检测）。"""
    for k in range(min(len(norm_tail), len(head)), 0, -1):
        if norm_tail.endswith(head[:k]):
            return k
    return 0


def _cut_norm_suffix(raw: str, k: int) -> str:
    """按归一化计数从 raw 尾部剪掉 k 个非空白字符（引号归一 1:1，剪口可落回原文）。"""
    if k <= 0:
        return raw
    seen = 0
    for i in range(len(raw) - 1, -1, -1):
        if not raw[i].isspace():
            seen += 1
            if seen == k:
                return raw[:i]
    return ""


def _validate_options(
    raw_options: list[dict], before: str, after: str, rejected_previews: list[str]
) -> tuple[list[dict], list[str]]:
    """逐版内容校验（W3）：返回（存活版, 丢弃原因）；空列表＝全灭。

    - 归一化后含边界标记行/代码围栏/契约字样 → 判负
    - 末尾与后文首句归一化重叠 ≥6 字 → 剪尾（剪后为空判负；剪口落回原文）
    - 与前/后文归一化公共子串 ≥15 字 → 判负
    - 与已否决预览（注入模板的同一段 120 字前缀，W2）公共子串 ≥30 字 → 判负
    """
    kept: list[dict] = []
    warnings: list[str] = []
    before_n, after_n = _norm(before), _norm(after)
    after_first = _first_sentence(after_n) if after_n else ""
    preview_norms = [p for p in (_norm(x) for x in rejected_previews) if p]
    for opt in raw_options:
        label = str(opt.get("label") or opt.get("key") or "?")
        text = str(opt.get("text", ""))
        norm = _norm(text)
        if any(m in norm for m in POLLUTION_MARKERS):
            warnings.append(f"{label}：含边界标记或契约字样")
            continue
        if after_first:
            overlap = _tail_prefix_overlap(norm, after_first)
            if overlap >= SEAM_CLIP_MIN:
                clipped = _cut_norm_suffix(text, overlap).strip()
                if not _norm(clipped):
                    warnings.append(f"{label}：剪尾后为空")
                    continue
                opt = {**opt, "text": clipped}
                norm = _norm(clipped)
                warnings.append(f"{label}：末尾与后文首句重叠，已剪尾保留")
        if before_n and _longest_common_substring_len(norm, before_n) >= REPEAT_MIN_SEAM:
            warnings.append(f"{label}：与前文重复过长")
            continue
        if after_n and _longest_common_substring_len(norm, after_n) >= REPEAT_MIN_SEAM:
            warnings.append(f"{label}：与后文重复过长")
            continue
        if any(
            _longest_common_substring_len(norm, pv) >= REPEAT_MIN_REJECTED
            for pv in preview_norms
        ):
            warnings.append(f"{label}：与已否决方案重复过长")
            continue
        kept.append(opt)
    return kept, warnings


def _parse_echos(raw: str) -> dict[str, str]:
    """从方案 JSON 提取 echo 凭证（缺失记空串；花括号截取口径同 _parse_options）。"""
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        data = json.loads(raw[start : end + 1])
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "before_echo": str(data.get("before_echo") or ""),
        "after_echo": str(data.get("after_echo") or ""),
    }


def _check_echo(echos: dict[str, str], before: str, after: str) -> tuple[bool, str]:
    """echo 凭证对拍（W3＋W1）：归一化后须为 before/after 的子串；超 20 字仅告警不重试。

    后文为空（断点即章末，无后续段）时 after_echo 无从对拍，跳过该侧子串检查。
    """
    for field, source in (("before_echo", before), ("after_echo", after)):
        norm = _norm(echos.get(field, ""))
        if not norm:
            return False, f"缺少{field}凭证"
        if len(norm) > ECHO_MAX_CHARS:
            logger.warning(
                "event=seam_refill_echo_overlong field=%s len=%d", field, len(norm)
            )
        src = _norm(source)
        if src and norm not in src:
            side = "前" if field == "before_echo" else "后"
            return False, f"{field}与{side}文原文对不上"
    return True, ""


def _after_text(prose: str, para_count: int) -> str:
    """断点后既有正文（≤2000 字）——模板 <<after>> 与判负对拍共用同一取材。"""
    paras = _paras(prose)
    para_count = min(para_count, len(paras))
    return "\n".join(paras[para_count:])[:2000]


def _rejected_feedback(base: str, opts: list[dict], reason: str) -> str:
    """重试素材：失败原因＋上一轮各版前 120 字，追加进【已否决方案】槽。"""
    lines = [base, f"【上一轮方案已作废——原因：{reason}；新版不得复用其讲法或连续文字】"]
    lines += [
        f"- {o.get('label', '')}：{str(o.get('text', ''))[:PREVIEW_CHARS]}" for o in opts
    ]
    return "\n".join(lines)


def _build_slots(ctx, prose: str, para_count: int, findings: list[dict], rejected: list) -> dict:
    """六槽组装：before/after/finding/rejected/story_state/style（模板 <<>> 一一对应）。"""
    paras = _paras(prose)
    para_count = min(para_count, len(paras))
    old_opening = "\n".join(paras[:para_count])
    after = _after_text(prose, para_count)

    lines = [
        f"- {f.get('title', '')}：{f.get('detail', '')}"
        for f in findings
        if isinstance(f, dict) and (f.get("title") or f.get("detail"))
    ]
    finding = "（无——按三类断裂自查开场衔接）"
    if lines:
        finding = "\n".join(lines)
    finding += f"\n【待替换的开场原文（病文，禁止效仿其讲法）】\n{old_opening}"

    rej_lines = [
        f"- {r.approach}：{r.text[:PREVIEW_CHARS]}" for r in rejected if r.text.strip()
    ]
    story = _story_state_block(ctx.story_state) or "（暂无故事状态）"

    return {
        "before": ctx.previous_tail or "（无）",
        "after": (after or "（本章没有后续段落）") + (
            f"\n\n【本章章末落点（硬边界，不得矛盾）】\n{ctx.ladder_exit}" if ctx.ladder_exit else ""
        ),
        "finding": finding,
        "rejected": "\n".join(rej_lines) if rej_lines else "（无）",
        "story_state": story,
        "style": style_section(ctx.style_setting) or "（未配置，以前后文自身文风为准）",
    }


@router.post("/draft")
@ai_feature("ai-generate")
async def draft(
    project_id: str,
    chapter_ref: str,
    body: SeamDraftBody | None = None,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """重写方案三选一（SSE）：draft 不落库，应用走前端替换＋既有 PUT prose 链。"""
    body = body or SeamDraftBody()
    if not 1 <= body.para_count <= 6:
        raise HTTPException(400, "para_count 取值 1-6")
    findings = [f for f in (body.findings or []) if isinstance(f, dict)][:MAX_FINDINGS]
    rejected = (body.rejected or [])[:3]

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    _validate_ref(chapter_ref)
    chapter = await load_chapter(project.root_path, chapter_ref) or {}
    prose = str(chapter.get("prose") or "")
    if not prose.strip():
        raise HTTPException(409, "本章还没有正文，没有可修复的开场")
    ctx = await build_chapter_context(
        project.root_path, chapter_ref, project.name, novel_id=project.id
    )
    if not (ctx.previous_tail or "").strip():
        raise HTTPException(409, "上一章没有可衔接的结尾（首章或上章未写），无需修复开场")

    client = await get_ai_client_for_novel(project.id)
    resolved_model = effective_model(project)
    slots = _build_slots(ctx, prose, body.para_count, findings, rejected)

    return StreamingResponse(
        _gen(
            project,
            ctx,
            chapter_ref,
            resolved_model,
            client,
            slots,
            db,
            user,
            before=ctx.previous_tail or "",
            after=_after_text(prose, body.para_count),
            previews=[r.text[:PREVIEW_CHARS] for r in rejected if r.text.strip()],
        ),
        media_type="text/event-stream",
    )


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _gen(
    project,
    ctx,
    chapter_ref: str,
    resolved_model: str,
    client,
    slots: dict,
    db,
    user,
    before: str,
    after: str,
    previews: list[str],
):
    from api_configs.usage import record_usage

    async def _fail(msg: str) -> None:
        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="seam_refill_draft_fail",
            model=resolved_model, force=True,
        )
        logger.warning("event=seam_refill_draft_error err=%s", msg[:200])
        yield _sse({"type": "error", "error": msg})

    try:
        yield _sse({"type": "phase", "phase": "assemble"})
        _sys_t, _usr_t = load_layers("seam_refill")
        system = _sys_t
        user_msg = _render(_usr_t, slots)
        yield _sse({"type": "phase", "phase": "model"})

        usage = {"tokens_in": 0, "tokens_out": 0}
        chars = 0
        kept: list[dict] = []
        for attempt in (1, 2):
            round_in = round_out = 0
            buf: list[str] = []
            async for ev in client.chat_stream(
                model=resolved_model,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
                max_tokens=8192,
                operation="seam_refill_draft",
            ):
                if ev.error:
                    raise RuntimeError(ev.error)
                if ev.text:
                    buf.append(ev.text)
                    chars += len(ev.text)
                    yield _sse({"type": "chunk", "chars": chars})
                if ev.tokens_in:
                    round_in = ev.tokens_in
                if ev.tokens:
                    round_out = ev.tokens
            usage["tokens_in"] += round_in
            usage["tokens_out"] += round_out

            raw = strip_code_fences("".join(buf))
            parsed = _parse_options(raw)
            if parsed is None:
                raise ValueError("方案解析失败（三版结构不完整），请重试")
            echo_ok, echo_err = _check_echo(_parse_echos(raw), before, after)
            survivors, warns = _validate_options(parsed, before, after, previews)
            for w in warns:
                logger.warning("event=seam_refill_option_rejected detail=%s", w)
            if echo_ok and survivors:
                kept = survivors
                break
            if attempt == 2:
                raise ValueError(f"重抽仍未通过校验（{echo_err or '三版均判负'}）")
            # 至多一次重试：失败原因＋上一轮各版前 120 字回注【已否决方案】（W2 同口径对拍）
            reason = echo_err or "、".join(warns) or "三版均判负"
            previews = [*previews, *(o["text"][:PREVIEW_CHARS] for o in parsed)]
            slots = {**slots, "rejected": _rejected_feedback(slots["rejected"], parsed, reason)}
            user_msg = _render(_usr_t, slots)

        await record_usage(
            db, user_id=project.user_id, project_id=project.id,
            chapter_id=chapter_ref, operation="seam_refill_draft",
            model=resolved_model,
            tokens_in=usage["tokens_in"], tokens_out=usage["tokens_out"],
        )
        yield _sse({"type": "done", "options": kept})
    except Exception as e:  # noqa: BLE001
        async for piece in _fail(f"衔接方案生成失败，可重试：{e}"):
            yield piece


def _render(template: str, values: dict[str, str]) -> str:
    """顺序 replace（<<name>> 占位），禁 str.format——契约含字面花括号。"""
    out = template
    for key, val in values.items():
        out = out.replace(f"<<{key}>>", val)
    return out
