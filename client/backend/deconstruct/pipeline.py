"""拆解管线 v2（c-deconstruct-book 2.x，2026-10-13 用户拍板架构）——逐章拆卡＋分维度分级语义归并。

- v1→v2：prescan 梗概与「段×维度 map」合并为**每章一次拆卡调用**（十维碎片＋梗概，章级断点）；
  「每维度一次 reduce 且 40k 截断」改为**分级归并**：卡片碎片按字数分批归并（L1，复用十维度
  模板＝卡片归并口径）→ 归并产物**树状收敛**（reduce 轮次循环直到单份）——任意长度零截断。
- 模板 12 份（提示词仓 awesome-novel-prompts）：`deconstruct-card`、`deconstruct-{dim}`×10
  （输入为逐章卡片碎片）、`deconstruct-reduce`（通用树合并）。load_layers 分层，str.format 注入。
- 证据章号不靠模型记忆：碎片由代码盖 `【第N章】` 前缀，模板明令「章号只来自材料标注」。
- 单元级重试 2 次、cancel 在章/批边界生效（每单元前重读任务 status 列）。
- 断点续拆：cards.entries 已有章号跳过；dims 中 state=completed 的维度跳过。
"""

from __future__ import annotations

import asyncio
import json
import os

from sqlalchemy import select

from db import async_session
from models.deconstruct import DIMENSION_KEYS, DeconstructJob
from prompts import PromptPackMissing, load_layers

# 单章喂料：超长章取头 4000＋尾 2000（评审 P2：转场/到达/位置句多落在章尾，纯截头会漏 presence 证据）
_CARD_TEXT_LIMIT = 6000
_CARD_HEAD, _CARD_TAIL = 4000, 2000
# L1 归并单批卡片碎片输入上限（字）
CARD_BATCH_CHARS = 30000
# 树收敛每轮合并输入上限（字）
MERGE_INPUT_CAP = 40000
# 梗概注入上限（全书骨架，卡片 summary 拼接）
_SYNOPSIS_CAP = 12000
SEGMENT_RETRIES = 2

_CANCELLED = "cancelled"


def _now():
    """DateTime 列必须收 datetime 对象（SQLite 绑 str 即 StatementError，行为测试实锤）。"""
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(tzinfo=None)


def _pack_pairs(pairs: list[tuple[str, str]], budget: int) -> list[list[tuple[str, str]]]:
    """确定性装箱（章号, 碎片行）：单行不拆，超预算起新批，单行超预算独占一批。"""
    batches: list[list[tuple[str, str]]] = []
    cur: list[tuple[str, str]] = []
    cur_len = 0
    for no, line in pairs:
        add = len(line) + (1 if cur else 0)  # "\n"
        if cur and cur_len + add > budget:
            batches.append(cur)
            cur, cur_len = [], 0
            add = len(line)
        cur.append((no, line))
        cur_len += add
    if cur:
        batches.append(cur)
    return batches or [[]]


def _pack_units(units: list[str], budget: int, joiner: str = "\n\n") -> list[list[str]]:
    """确定性装箱（字符串单元）：用于树收敛轮次的 partials 分组。"""
    batches: list[list[str]] = []
    cur: list[str] = []
    cur_len = 0
    for u in units:
        add = len(u) + (len(joiner) if cur else 0)
        if cur and cur_len + add > budget:
            batches.append(cur)
            cur, cur_len = [], 0
            add = len(u)
        cur.append(u)
        cur_len += add
    if cur:
        batches.append(cur)
    return batches or [[]]


def _card_text(chapter: dict) -> str:
    """单章喂料：≤6000 字原样；超长取头 4000＋尾 2000（中略显式标注，卡以此可见部分为据）。"""
    text = chapter.get("text", "") or ""
    if len(text) <= _CARD_TEXT_LIMIT:
        return text
    return text[:_CARD_HEAD] + "\n……（中略——仅以首尾为据）……\n" + text[-_CARD_TAIL:]


def _card_frag(no: str, card: dict, dim: str) -> str:
    """单卡某维度 → 一行碎片（空维度不给行）。structure 契约为数组，dict 容错包装。"""
    items = card.get(dim)
    if isinstance(items, dict):
        items = [items]
    if not items:
        return ""
    return f"【第{no}章】{json.dumps(items, ensure_ascii=False)}"


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


def dim_names() -> dict[str, str]:
    from models.deconstruct import DIMENSIONS

    return {k: name for k, name, _ in DIMENSIONS}


class _Cancelled(Exception):
    pass


async def _check_cancel(task_id: str) -> None:
    if await _status_of(task_id) == _CANCELLED:
        raise _Cancelled()


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


async def _call_with_retry(client, model, system_tpl, user_vars, operation):
    """单元级调用：重试 2 次（重试属同一单元内的模型调用，不涉及内容截断）。"""
    system, user_tpl = system_tpl
    last_err: Exception | None = None
    for _ in range(SEGMENT_RETRIES + 1):
        try:
            return await _chat_json(client, model, system, user_tpl.format(**user_vars), operation)
        except _Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 — 单元级重试后放行（管线自兜底）
            last_err = e
            await asyncio.sleep(0.2)
    raise last_err if last_err else RuntimeError("模型调用失败")


def _synopses(cards: dict) -> str:
    """卡片 summary → 全书逐章梗概（注入 L1 归并调用）。"""
    return "\n".join(
        f"第{no}章 {card.get('summary', '')}"
        for no, card in sorted(cards.get("entries", {}).items(), key=lambda kv: int(kv[0] or 0))
    )


async def run_task(task_id: str) -> None:
    """执行一个拆书任务（dispatcher 串行调用；亦为断点续拆入口）。"""
    task = await _load_task(task_id)
    if task is None:
        return
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
        # ── 阶段一：逐章拆卡（章级断点：entries 已有章号跳过）──
        cards = state.get("cards", {"state": "queued", "done": 0, "entries": {}})
        if cards.get("state") != "completed":
            cards.setdefault("entries", {})
            cards["state"] = "running"
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
            sys_c, usr_c = load_layers("deconstruct_card")
            for ch in chapters:
                await _check_cancel(task_id)
                no = str(ch.get("no", 0))
                if no in cards["entries"]:
                    continue
                data = await _call_with_retry(
                    client, model, (sys_c, usr_c),
                    {
                        "book_name": task.book_name,
                        "chapter_no": no,
                        "chapter_title": ch.get("title", ""),
                        "chapter_text": _card_text(ch),
                    },
                    "deconstruct_card",
                )
                cards["entries"][no] = data
                cards["done"] = len(cards["entries"])
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
            cards["state"] = "completed"
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))

        full_synopsis = _synopses(cards)

        # ── 阶段二：分维度分级归并（勾选集；completed 跳过＝断点续拆）──
        products: dict[str, dict] = {}
        try:
            products = json.loads((await _load_task(task_id)).products_json or "{}")
        except (ValueError, AttributeError):
            pass
        names = dim_names()
        for dim in DIMENSION_KEYS:
            if dim not in selected:
                continue
            await _check_cancel(task_id)
            dstate = dims.get(dim, {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""})
            if dstate.get("state") == "completed" and dim in products:
                continue
            sys_m, usr_m = load_layers(f"deconstruct_{dim}")
            pairs = [
                (no, line)
                for no, card in sorted(cards["entries"].items(), key=lambda kv: int(kv[0] or 0))
                if (line := _card_frag(no, card, dim))
            ]
            batches = _pack_pairs(pairs, CARD_BATCH_CHARS)
            dstate.update({"state": "running", "seg_done": 0, "seg_total": len(batches), "error": ""})
            dims[dim] = dstate
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))

            partials: list[str] = []
            for i, batch in enumerate(batches):
                await _check_cancel(task_id)
                ch_from, ch_to = batch[0][0] if batch else "1", batch[-1][0] if batch else "1"
                data = await _call_with_retry(
                    client, model, (sys_m, usr_m),
                    {
                        "book_name": task.book_name, "genre_or_unknown": "unknown",
                        "full_synopsis": full_synopsis[:_SYNOPSIS_CAP],
                        "seg_range": f"第{ch_from}-{ch_to}章",
                        "excerpts": "\n".join(line for _, line in batch),
                    },
                    f"deconstruct_{dim}",
                )
                partials.append(json.dumps(data, ensure_ascii=False))
                dstate["seg_done"] = i + 1
                dims[dim] = dstate
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))

            # 树收敛：多批产物反复合并直到单份（无头尾截断＝任意长度零丢失）
            if len(partials) > 1:
                sys_r, usr_r = load_layers("deconstruct_reduce")
                while len(partials) > 1:
                    await _check_cancel(task_id)
                    groups = _pack_units(partials, MERGE_INPUT_CAP)
                    if len(groups) >= len(partials):
                        # 每份都超单组预算：两两配对保底收敛
                        groups = [partials[i : i + 2] for i in range(0, len(partials), 2)]
                    nxt: list[str] = []
                    dstate["seg_total"] += len(groups)
                    for group in groups:
                        if len(group) == 1:
                            nxt.append(group[0])
                            continue
                        await _check_cancel(task_id)
                        merged = await _call_with_retry(
                            client, model, (sys_r, usr_r),
                            {"dim_name": names[dim], "partials": "\n\n".join(group)},
                            f"deconstruct_{dim}_reduce",
                        )
                        nxt.append(json.dumps(merged, ensure_ascii=False))
                        dstate["seg_done"] += 1
                        dims[dim] = dstate
                        await _patch(
                            task_id, dims_json=_state_json(state, cards=cards, dims=dims)
                        )
                    partials = nxt

            final = _parse_json_response(partials[0]) if partials else {}
            covered = f"第1-{task.chapter_count}章" if task.chapter_count else "全本"
            products[dim] = {
                "file": _dim_filename(dim),
                "data": final,
                "md": _render_md(names[dim], final, task.book_name, covered),
            }
            dstate["state"] = "completed"
            dims[dim] = dstate
            await _patch(
                task_id,
                dims_json=_state_json(state, cards=cards, dims=dims),
                products_json=json.dumps(products, ensure_ascii=False),
            )
    except _Cancelled:
        await _patch(task_id, finished_at=_now())
        return
    except PromptPackMissing as e:
        await _fail(task_id, error={"message": f"写作能力包缺少拆书模板：{e}", "kind": "prompts_missing"})
        return
    except Exception as e:  # noqa: BLE001 — 终态收敛：任务失败保留已完成维度
        await _fail(task_id, error={"message": str(e)[:500], "kind": "pipeline"})
        return

    await _patch(task_id, status="completed", finished_at=_now())


async def _fail(task_id: str, error: dict) -> None:
    await _patch(
        task_id,
        status="failed",
        error_json=json.dumps(error, ensure_ascii=False),
        finished_at=_now(),
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


def _state_json(state: dict, *, cards: dict, dims: dict) -> str:
    """dims_json 全量落库：**保留未知顶键**——评审 P0：阶段三 graph 归一化缓存（及未来新段）
    不得被卡片/维度边界的 patch 抹掉；管线为 dims_json 唯一写者。"""
    out = dict(state)
    out["cards"] = cards
    out["dims"] = dims
    return json.dumps(out, ensure_ascii=False)


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
