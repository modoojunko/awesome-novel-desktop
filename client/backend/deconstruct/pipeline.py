"""拆解管线（c-deconstruct-book 2.x）——prescan＋维度 map-reduce，模型输出 JSON、代码渲染 md。

- 模板 12 份（提示词仓 awesome-novel-prompts）：`deconstruct-prescan`、`deconstruct-{dim}`×10、
  `deconstruct-reduce`（通用合并）。分层加载（load_layers），占位符 str.format 注入。
- 证据章号不靠模型记忆：摘录由代码盖 `【第N章】` 前缀注入，模板明令「章号只来自材料标注」。
- 段窗：自建启发式 `_estimate_tokens`（中文 ≈1.6 字/token 保守值），按 ESTIMATE_TOKEN_BUDGET 切章。
- 段级重试 2 次（内存计数＋dims_json.error 留痕），维度失败即停任务；cancel 在段边界生效
  （每段前重读任务 status 列）。
- 断点续拆：dims_json 中 state=completed 的维度跳过；resume 只跑勾选且未完成的维度。
"""

from __future__ import annotations

import asyncio
import json
import os

from sqlalchemy import select

from db import async_session
from models.deconstruct import DIMENSION_KEYS, DeconstructJob
from prompts import PromptPackMissing, load_layers

# 段窗预算（token 估算值）：单次调用素材上限。中文 1.6 字/token 保守 → ~14k 字/段。
ESTIMATE_TOKEN_BUDGET = 9000
CHARS_PER_TOKEN = 1.6
SEGMENT_RETRIES = 2
# 每章摘录上限（首尾拼接），控制 map 输入规模
_EXCERPT_HEAD, _EXCERPT_TAIL = 900, 300

_CANCELLED = "cancelled"


class TaskCancelled(Exception):
    """段边界捕获的取消信号（worker 捕获后落 cancelled 终态）。"""


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text or "") / CHARS_PER_TOKEN))


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _segments(chapters: list[dict]) -> list[list[dict]]:
    """按估算 token 预算把章列表切成确定性的段（贪心装箱，章不跨段）。"""
    segs: list[list[dict]] = []
    cur: list[dict] = []
    cur_est = 0
    for ch in chapters:
        est = _estimate_tokens(ch.get("text", ""))
        if cur and cur_est + est > ESTIMATE_TOKEN_BUDGET:
            segs.append(cur)
            cur, cur_est = [], 0
        cur.append(ch)
        cur_est += est
    if cur:
        segs.append(cur)
    return segs or [[]]


def _excerpt(ch: dict) -> str:
    text = ch.get("text", "")
    head, tail = text[:_EXCERPT_HEAD], text[-_EXCERPT_TAIL:] if len(text) > _EXCERPT_HEAD + _EXCERPT_TAIL else ""
    body = head + ("……" + tail if tail else "")
    return f"【第{ch.get('no', 1)}章 · {ch.get('title', '')}】\n{body}"


def _parse_json_response(raw: str) -> dict:
    """模型 JSON 容错解析：剥 ```json 围栏，取首个 {...} 平衡块。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    if start < 0:
        raise ValueError("模型输出不是 JSON")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("模型输出 JSON 不完整")


def _fmt_warning(value) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def dim_names() -> dict[str, str]:
    from models.deconstruct import DIMENSIONS

    return {k: name for k, name, _ in DIMENSIONS}


async def _chat_json(client, model: str, system: str, user: str, operation: str) -> dict:
    raw = await client.chat(
        model=model,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=4096,
        json_mode=True,
        operation=operation,
    )
    return _parse_json_response(raw)


def _render_md(dim: str, data: dict, book_name: str, covered: str) -> str:
    """JSON → Markdown（代码渲染：模型不直出 md）。产物仅静态呈现，应用内不预览不编辑。"""
    lines = [f"# {dim}｜{book_name}", "", f"> 覆盖范围：{covered} · 由拆书任务生成，证据章号见各条目", ""]
    if not isinstance(data, dict):
        data = {"result": data}
    for key, value in data.items():
        lines.append(f"## {key}")
        lines.append("")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    head = str(item.get("name") or item.get("title") or item.get("desc") or "").strip()
                    body = "；".join(
                        f"{k}：{v}" for k, v in item.items() if k not in ("name", "title") and v
                    )
                    lines.append(f"- {('**' + head + '**　') if head else ''}{body}")
                else:
                    lines.append(f"- {item}")
        else:
            lines.append(str(value))
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("三铁律：硬事实回指章节号；结论标可信度（high/mid/low）；原文没写的标「原文未明确」。")
    lines.append("")
    return "\n".join(lines)


async def _load_task(task_id: str) -> DeconstructJob | None:
    async with async_session() as session:
        return await session.get(DeconstructJob, task_id)


async def _patch(task_id: str, **mutate) -> None:
    async with async_session() as session:
        task = await session.get(DeconstructJob, task_id)
        if task is None:
            return
        for k, v in mutate.items():
            setattr(task, k, v)
        await session.commit()


async def _status_of(task_id: str) -> str:
    async with async_session() as session:
        task = await session.get(DeconstructJob, task_id)
        return task.status if task else _CANCELLED


def _selected(task: DeconstructJob) -> list[str]:
    try:
        picked = json.loads(task.selected_dims_json or "[]")
    except ValueError:
        picked = []
    valid = [k for k in DIMENSION_KEYS if k in picked]
    return valid or list(DIMENSION_KEYS)


class _Cancelled(Exception):
    pass


async def _check_cancel(task_id: str) -> None:
    if await _status_of(task_id) == _CANCELLED:
        raise _Cancelled()


async def _call_with_retry(client, model, system_tpl, user_vars, operation):
    """段级调用：重试 2 次（重试属同一段内的模型调用，不涉及内容截断）。"""
    system, user_tpl = system_tpl
    last_err: Exception | None = None
    for _ in range(SEGMENT_RETRIES + 1):
        try:
            return await _chat_json(client, model, system, user_tpl.format(**user_vars), operation)
        except _Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 — 段级重试后放行（管线自兜底）
            last_err = e
            await asyncio.sleep(0.2)
    raise last_err if last_err else RuntimeError("模型调用失败")


async def run_task(task_id: str) -> None:
    """执行一个拆书任务（dispatcher 串行调用；亦为断点续拆入口）。"""
    task = await _load_task(task_id)
    if task is None:
        return
    client, model = (None, "")
    try:
        from deconstruct.service import resolve_client

        client, model = await resolve_client(task.user_id, task.api_config_id, task.ai_model)
    except ValueError as e:
        await _fail(task_id, error={"message": str(e), "kind": "model"})
        return

    chapters = await _load_chapters(task)
    state = await _read_dims(task_id)
    selected = _selected(task)
    dims = state.get("dims", {})

    try:
        # ── 阶段一：prescan（逐章梗概；断点：已完成章跳过）──
        prescan = state.get("prescan", {"state": "queued", "chapters_done": 0, "entries": {}})
        if prescan.get("state") != "completed":
            prescan.setdefault("entries", {})
            prescan["state"] = "running"
            await _patch(task_id, dims_json=json.dumps({"prescan": prescan, "dims": dims}, ensure_ascii=False))
            sys_p, usr_p = load_layers("deconstruct_prescan")
            for ch in chapters:
                await _check_cancel(task_id)
                no = str(ch.get("no", 0))
                if no in prescan["entries"]:
                    continue
                data = await _call_with_retry(
                    client, model, (sys_p, usr_p),
                    {"chapter_no": no, "chapter_title": ch.get("title", ""), "chapter_text": ch["text"][:6000]},
                    "deconstruct_prescan",
                )
                prescan["entries"][no] = data.get("summary", "")
                prescan["chapters_done"] = len(prescan["entries"])
                await _patch(task_id, dims_json=json.dumps({"prescan": prescan, "dims": dims}, ensure_ascii=False))
            prescan["state"] = "completed"
            await _patch(task_id, dims_json=json.dumps({"prescan": prescan, "dims": dims}, ensure_ascii=False))

        full_synopsis = "\n".join(
            f"第{no}章 {summary}" for no, summary in sorted(prescan.get("entries", {}).items(), key=lambda kv: int(kv[0] or 0))
        )

        # ── 阶段二：十维度 map-reduce（勾选集；completed 跳过＝断点续拆）──
        products: dict[str, str] = {}
        try:
            products = json.loads((await _load_task(task_id)).products_json or "{}")
        except (ValueError, AttributeError):
            pass
        for dim in DIMENSION_KEYS:
            if dim not in selected:
                continue
            await _check_cancel(task_id)
            dstate = dims.get(dim, {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""})
            if dstate.get("state") == "completed" and dim in products:
                continue
            sys_m, usr_m = load_layers(f"deconstruct_{dim}")
            segs = _segments(chapters)
            dstate.update({"state": "running", "seg_total": len(segs), "seg_done": 0, "error": ""})
            dims[dim] = dstate
            await _patch(task_id, dims_json=json.dumps({"prescan": prescan, "dims": dims}, ensure_ascii=False))

            partials: list[str] = []
            for i, seg in enumerate(segs):
                await _check_cancel(task_id)
                ch_from, ch_to = seg[0].get("no", 1), seg[-1].get("no", 1)
                excerpts = "\n\n".join(_excerpt(c) for c in seg)
                data = await _call_with_retry(
                    client, model, (sys_m, usr_m),
                    {"book_name": task.book_name, "genre_or_unknown": "unknown",
                     "full_synopsis": full_synopsis[:12000], "seg_range": f"第{ch_from}-{ch_to}章",
                     "excerpts": excerpts[:20000]},
                    f"deconstruct_{dim}",
                )
                partials.append(f"【覆盖第{ch_from}-{ch_to}章】\n" + json.dumps(data, ensure_ascii=False))
                dstate["seg_done"] = i + 1
                dims[dim] = dstate
                await _patch(task_id, dims_json=json.dumps({"prescan": prescan, "dims": dims}, ensure_ascii=False))

            await _check_cancel(task_id)
            if len(partials) == 1:
                final = _parse_json_response(partials[0].partition("】\n")[2]) if "】" in partials[0] else json.loads(partials[0])
            else:
                sys_r, usr_r = load_layers("deconstruct_reduce")
                final = await _call_with_retry(
                    client, model, (sys_r, usr_r),
                    {"dim_name": dim, "partials": "\n\n".join(partials)[:40000]},
                    f"deconstruct_{dim}_reduce",
                )
            covered = f"第1-{task.chapter_count}章" if task.chapter_count else "全本"
            products[dim] = {
                "file": _dim_filename(dim),
                "data": final,
                "md": _render_md(dim_names()[dim], final, task.book_name, covered),
            }
            dstate["state"] = "completed"
            dims[dim] = dstate
            await _patch(
                task_id,
                dims_json=json.dumps({"prescan": prescan, "dims": dims}, ensure_ascii=False),
                products_json=json.dumps(products, ensure_ascii=False),
            )
    except _Cancelled:
        await _patch(task_id, finished_at=_now_iso())
        return
    except PromptPackMissing as e:
        await _fail(task_id, error={"message": f"写作能力包缺少拆书模板：{e}", "kind": "prompts_missing"})
        return
    except Exception as e:  # noqa: BLE001 — 终态收敛：任务失败保留已完成维度
        await _fail(task_id, error={"message": str(e)[:500], "kind": "pipeline"})
        return

    await _patch(task_id, status="completed", finished_at=_now_iso())


async def _fail(task_id: str, error: dict) -> None:
    await _patch(
        task_id,
        status="failed",
        error_json=json.dumps(error, ensure_ascii=False),
        finished_at=_now_iso(),
    )


def _dim_filename(dim: str) -> str:
    from models.deconstruct import DIMENSIONS

    return next(filename for k, _, filename in DIMENSIONS if k == dim)


async def _load_chapters(task: DeconstructJob) -> list[dict]:
    """从 staging 源文件重建章节（解析确定性：同一文件同一结果）。缺源抛 FileNotFoundError。"""
    from deconstruct.textparse import decode_text, parse_novel

    if not task.source_path or not os.path.exists(task.source_path):
        raise FileNotFoundError(task.source_path)
    with open(task.source_path, "rb") as f:
        raw = f.read()
    text, _ = decode_text(raw)
    return parse_novel(text)["chapters"]


async def _read_dims(task_id: str) -> dict:
    async with async_session() as session:
        task = await session.get(DeconstructJob, task_id)
        try:
            return json.loads(task.dims_json or "{}") if task else {}
        except ValueError:
            return {}


async def list_queued_ids() -> list[str]:
    async with async_session() as session:
        rows = (
            await session.scalars(
                select(DeconstructJob.id)
                .where(DeconstructJob.status == "queued")
                .order_by(DeconstructJob.queue_seq, DeconstructJob.created_at)
            )
        ).all()
        return list(rows)


async def startup_sweep() -> None:
    """启动恢复（照 dossier sweep 先例）：running 且无线程→failed(interrupted)；
    queued 缺源→need_reupload；有源 queued 保持位次（dispatcher 会接手）。"""
    async with async_session() as session:
        rows = (
            await session.scalars(
                select(DeconstructJob).where(DeconstructJob.status.in_(["running", "queued"]))
            )
        ).all()
        changed = False
        for r in rows:
            if r.status == "running":
                r.status = "failed"
                r.error_json = json.dumps(
                    {"message": "应用退出导致中断，可从断点续拆", "kind": "interrupted"},
                    ensure_ascii=False,
                )
                changed = True
            elif r.status == "queued" and (not r.source_path or not os.path.exists(r.source_path)):
                r.status = "need_reupload"
                changed = True
        if changed:
            await session.commit()
