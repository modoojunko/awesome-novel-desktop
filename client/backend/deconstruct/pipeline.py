"""拆解管线 v2（c-deconstruct-book 2.x，2026-10-13 用户拍板架构）——逐章拆卡＋分维度分级语义归并。

- v1→v2：prescan 梗概与「段×维度 map」合并为**每章一次拆卡调用**（十维碎片＋梗概，章级断点）；
  「每维度一次 reduce 且 40k 截断」改为**分级归并**：卡片碎片按字数分批归并（L1，复用十维度
  模板＝卡片归并口径）→ 归并产物**树状收敛**（reduce 轮次循环直到单份）——任意长度零截断。
- 模板 12 份（提示词仓 awesome-novel-prompts）：`deconstruct-card`、`deconstruct-{dim}`×10
  （输入为逐章卡片碎片）、`deconstruct-reduce`（通用树合并）。load_layers 分层，str.format 注入。
- 证据章号不靠模型记忆：碎片由代码盖 `【第N章】` 前缀，模板明令「章号只来自材料标注」。
- 单元级重试 2 次（429 限流退避 3s）、cancel 在章/批边界生效（每单元前重读任务 status 列）。
- LLM 调用并发度＝DECONSTRUCT_CONCURRENCY（默认 4，=1 与旧串行实现逐字等价）：拆卡章间／
  维度间／维度内 L1 批次／在场补写四处并发，共享信号量限流；reduce 收敛保持串行（树形依赖）。
  纯 I/O 并发用 asyncio，无需子进程。
- 断点续拆：cards.entries 已有章号跳过；dims 中 state=completed 的维度跳过。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from sqlalchemy import select

from db import async_session
from deconstruct.graph import (  # noqa: PLC2701 — 域内复用形状防御（graph 无回环）
    _TIME_TAGS,
    _clean,
    _dicts,
)
from deconstruct.sanitize import sanitize_for_model
from deconstruct.textparse import CARD_TEXT_LIMIT
from models.deconstruct import DIMENSION_KEYS, DeconstructJob
from prompts import PromptPackMissing, load_layers

# 单章喂料：超长章取头 4000＋尾 2000（评审 P2：转场/到达/位置句多落在章尾，纯截头会漏 presence 证据）；
# 合计上限单源 textparse.CARD_TEXT_LIMIT（结构判定文案同源引用，防文案与实际喂料漂移）
_CARD_HEAD, _CARD_TAIL = 4000, 2000
# L1 归并单批卡片碎片输入上限（字）
CARD_BATCH_CHARS = 30000
# 树收敛每轮合并输入上限（字）
MERGE_INPUT_CAP = 40000
# 梗概注入上限（全书骨架，卡片 summary 拼接）
_SYNOPSIS_CAP = 12000
SEGMENT_RETRIES = 2
# 并发调用上限（DECONSTRUCT_CONCURRENCY，默认 4；=1 即原串行）——拆书是 I/O 密集
# （等模型返回），asyncio 并发即可成倍提速、无需子进程；上限同时压住 429 限流风险
CONCURRENCY = max(1, int(os.environ.get("DECONSTRUCT_CONCURRENCY", "4") or 4))

# 每 operation 输出 token 预算。归并类（deconstruct_{dim} L1 归并＋deconstruct_{dim}_reduce
# 树收敛，动态名不进表、吃默认值）一律 8192——默认 4096 会把 JSON 拦腰截断（真机实证
# 两回：10-09 世界归并、10-18 structure/foreshadow 归并三连败，error_json「模型输出
# JSON 不完整」；归并输出按条目数线性走不随摘要压缩变小，GLM-5.3 思考还与正文共用
# 预算）；拆卡单章 6144 不变；presence 补写/place 抽取单卡小输出维持 4096。
_OP_MAX_TOKENS = {
    "deconstruct_card": 6144,
    "deconstruct_presence": 4096,
    "deconstruct_place": 4096,
}
_OP_MERGE_TOKENS = 8192


def _graph_export_on() -> bool:
    """图谱导出总开关（默认开；关＝跳过阶段三装配与导出三件套——评审：开关＝具名交付物）。"""
    return os.environ.get("DECONSTRUCT_GRAPH_EXPORT", "1") != "0"

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
    """单章喂料：≤6000 字原样；超长取头 4000＋尾 2000（中略显式标注，卡以此可见部分为据）。

    脱敏不在本函数做——所有模型调用统一在 _call_with_retry 咽喉处过
    _sanitize_vars（拆卡/补写/归并/reduce 一处全覆盖，单点不会漏）。
    """
    text = chapter.get("text", "") or ""
    if len(text) <= CARD_TEXT_LIMIT:
        return text
    return text[:_CARD_HEAD] + "\n……（中略——仅以首尾为据）……\n" + text[-_CARD_TAIL:]


_log = logging.getLogger("deconstruct.sanitize")


def _sanitize_vars(user_vars: dict) -> dict:
    """模型调用前统一脱敏：所有 str 值过中性替换（非 str 原样）。

    覆盖全部调用点的输入——章节原文（拆卡/补写）之外，还有**归并与 reduce
    的碎片/归并稿**：它们凝结了原文敏感内容（13路末班车实测 1301 死在
    mainplot_reduce，L1 与拆卡均过），单盖 _card_text 挡不住这一层。
    已脱敏文本再过一遍是幂等 no-op（替换输出不含任何词表原词，测试钉死）。
    """
    out: dict = {}
    for k, v in user_vars.items():
        if isinstance(v, str):
            clean, hits = sanitize_for_model(v)
            if hits:
                _log.info("SANITIZE %s: %s", k, "；".join(hits[:8]))
            out[k] = clean
        else:
            out[k] = v
    return out


def _merge_final(partials: list[str]) -> dict:
    """终稿归一：单份直取；多份（reduce 降级残留）＝同键列表拼接的保底合并。

    降级稿内容与收敛稿基本一致（L1 每批都见过全书梗概），只是段间可能有
    重复条目——保底可用优先，不为此再冒一次被拦的调用。
    """
    if not partials:
        return {}
    parsed = [_parse_json_response(p) for p in partials]
    if len(parsed) == 1:
        return parsed[0]
    merged: dict = {}
    for data in parsed:
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            if isinstance(v, list) and isinstance(merged.get(k), list):
                merged[k] = merged[k] + v
            elif isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            elif k not in merged:
                merged[k] = v
            # 其余标量冲突：保留首份（seen/seg 口径以第一段为准可读性最好）
    return merged


def _quote_corpus(chapters: list[dict]) -> str:
    """quote 回验语料：原稿全文＋替换稿（仅在有替换时附）——卡片引用可能来自任一稿。

    _card_text 先截选再替换，边界截断的敏感词短语会以半截原形留在喂料里，
    模型引用于是可能出自原稿或替换稿；两稿拼一起让 quote 回验（子串匹配）两认。
    """
    raw = "\n".join(ch.get("text", "") or "" for ch in chapters)
    clean = sanitize_for_model(raw)[0]
    return raw if clean == raw else f"{raw}\n{clean}"


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
    # ai_client 的 read=90 是按 4096 tokens 生成上限校准的（ai-client-timeout D1）；
    # 归并类提到 8192 后 90 秒写不完（真机实证：五批连排 180s 超时），长输出
    # 操作改传 read=600——收敛最坏等待仍由单元级重试次数兜住。
    budget = _OP_MAX_TOKENS.get(operation, _OP_MERGE_TOKENS)
    timeout = None
    if budget >= 8192:
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)
    raw = await client.chat(
        model=model,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=budget,
        json_mode=True,
        operation=operation,
        timeout=timeout,
    )
    return _parse_json_response(raw)


async def _run_units(units: list) -> list:
    """单元集执行：CONCURRENCY=1＝逐个 await（与旧串行逐字等价：调用序/取消时机不变）；
    否则 gather 收齐在途单元再抛首错（并发下取消/失败的越界≤上限个单元，断点保留已完成）。"""
    if CONCURRENCY == 1:
        out: list = []
        for c in units:
            out.append(await c)
        return out
    outcomes = await asyncio.gather(*units, return_exceptions=True)
    for oc in outcomes:
        if isinstance(oc, BaseException):
            raise oc
    return outcomes


async def _call_with_retry(client, model, system_tpl, user_vars, operation):
    """单元级调用：重试 2 次（重试属同一单元内的模型调用，不涉及内容截断）。

    user 变量在咽喉处统一脱敏（_sanitize_vars）：章节原文＋归并/reduce 碎片
    全覆盖，绕内容审核 1301。
    """
    system, user_tpl = system_tpl
    user_vars = _sanitize_vars(user_vars)
    last_err: Exception | None = None
    for _ in range(SEGMENT_RETRIES + 1):
        try:
            return await _chat_json(client, model, system, user_tpl.format(**user_vars), operation)
        except _Cancelled:
            raise
        except Exception as e:  # noqa: BLE001 — 单元级重试后放行（管线自兜底）
            last_err = e
            msg = str(e)
            # 429＝限流：并发下更易触发，退避 3s 再试（其余失败 0.2s 快速重试）
            await asyncio.sleep(3.0 if "429" in msg or "rate limit" in msg.lower() else 0.2)
    raise last_err if last_err else RuntimeError("模型调用失败")


def _synopses(cards: dict) -> str:
    """卡片 summary → 全书逐章梗概（注入 L1 归并调用）。"""
    return "\n".join(
        f"第{no}章 {card.get('summary', '')}"
        for no, card in sorted(cards.get("entries", {}).items(), key=lambda kv: int(kv[0] or 0))
    )


def _presence_gaps(card: dict) -> list[str]:
    """单卡在场缺口：characters 全名（非空）− presence.who（评审钉的代码侧强制）。"""
    chars = {_clean(c.get("name"))
             for c in _dicts(card.get("characters")) if _clean(c.get("name"))}
    whos = {_clean(p.get("who"))
            for p in _dicts(card.get("presence")) if _clean(p.get("who"))}
    return sorted(chars - whos)


async def _backfill_presence(task_id, task, chapters, cards, dims, state, client, model,
                             graph_on: bool, caps: bool, sem: asyncio.Semaphore) -> int:
    """阶段 3.0（10.1a 熔断预案落地）：在场缺口选择性补写（章间并发，sem 共享限流）。

    - 逐章检测 characters 全名 ⊆ presence.who；缺口非空才触发轻量调用（达标章零成本）；
    - 补写只收名单内 who（模型越权输出丢弃）、where 强制本章闭集（越权地名降空串→未知区）；
    - 逐章 try/except：单章失败计入计数并跳过——图谱病着也要出（评审 P1-1 三级降级）；
    - caps=false（老包 card 无 presence 契约）或开关关：整段跳过；
      包版本窗（card 有 presence 而 deconstruct_presence 模板缺）→ 静默跳过（评审 P2-1）。
    - 返回补写失败章数（调用方并入 meta.warnings）。
    """
    if not graph_on or not caps:
        return 0
    try:
        sys_b, usr_b = load_layers("deconstruct_presence")
    except Exception:  # noqa: BLE001 — 模板缺失＝包版本窗，静默跳过（评审 P2-1）
        return 0
    from deconstruct.graph import _clean, _dicts  # noqa: PLC2701 — 域内复用形状防御

    entries = cards.get("entries") if isinstance(cards.get("entries"), dict) else {}
    if not entries:
        return 0
    gap_work: list[tuple[dict, list[str]]] = []
    for ch in chapters:
        no = str(ch.get("no", 0))
        card = entries.get(no)
        if isinstance(card, dict) and "places" in card:  # 老契约卡（无 places）留空降级不重跑
            missing = _presence_gaps(card)
            if missing:
                gap_work.append((ch, missing))
    # 阶段进度账（graph_phase）：补写是多次轻量调用，之前全程暗跑——UI 在
    # 全维度 completed 后几分钟数字不动，用户以为卡死（真机实证）。
    phase = {"step": "presence", "done": 0, "total": len(gap_work)}
    state["graph_phase"] = phase
    await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
    failed = 0

    async def _bf_one(ch: dict, missing: list[str]) -> bool:  # → True＝该章补写失败（降级留痕）
        nonlocal failed
        no = str(ch.get("no", 0))
        card = entries[no]
        async with sem:
            await _check_cancel(task_id)
            state["activity"] = {"label": f"正在补写在场 第{no}章", "at": _now().isoformat()}
            phase["done"] += 1
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
            known_list = [_clean(pl.get("name")) for pl in _dicts(card.get("places")) if _clean(pl.get("name"))]
            known_set = set(known_list)
            known = "、".join(known_list) or "（本章无已知地点，where 一律空串）"
            try:
                data = await _call_with_retry(
                    client, model, (sys_b, usr_b),
                    {
                        "book_name": task.book_name,
                        "chapter_no": no,
                        "chapter_title": ch.get("title", ""),
                        "missing_names": "、".join(missing),
                        "places_known": known,
                        "chapter_text": _card_text(ch),
                    },
                    "deconstruct_presence",
                )
            except _Cancelled:
                raise
            except Exception as _e:  # noqa: BLE001 — 评审 P1-1：单章失败跳过继续，不拖垮整本图谱
                _log.warning("BF-FAIL %s: %r", no, _e)
                failed += 1
                return True
        existing_whos = {_clean(p.get("who")) for p in _dicts(card.get("presence"))}
        added = 0
        for p in _dicts(data.get("presence") if isinstance(data, dict) else None):
            who = _clean(p.get("who"))
            if who not in missing or who in existing_whos:
                continue
            where = _clean(p.get("where"))
            if where and where not in known_set:  # 评审 P2-2：where 强制本章闭集
                where = ""
            entry: dict = {"who": who, "where": where or ""}
            t_raw = str(p.get("t") or "")
            if t_raw in _TIME_TAGS:
                entry["t"] = t_raw
            card.setdefault("presence", []).append(entry)
            existing_whos.add(who)
            added += 1
        if added:
            entries[no] = card
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
        return False

    await _run_units([_bf_one(ch, missing) for ch, missing in gap_work])
    return failed


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
        _sem = asyncio.Semaphore(CONCURRENCY)  # 全管线共享限流：卡/L1/补写/reduce 统一在册

        # ── 阶段一：逐章拆卡（章级断点：entries 已有章号跳过；章间并发）──
        cards = state.get("cards", {"state": "queued", "done": 0, "entries": {}})
        if cards.get("state") != "completed":
            cards.setdefault("entries", {})
            cards["state"] = "running"
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
            sys_c, usr_c = load_layers("deconstruct_card")
            todo = [ch for ch in chapters if str(ch.get("no", 0)) not in cards["entries"]]

            async def _card_one(ch: dict) -> None:
                async with _sem:
                    await _check_cancel(task_id)
                    no = str(ch.get("no", 0))
                    state["activity"] = {"label": f"正在拆解 第{no}章", "at": _now().isoformat()}
                    data = await _call_with_retry(
                        client, model, (sys_c, usr_c),
                        {
                            "book_name": task.book_name,
                            "chapter_no": str(ch.get("no", 0)),
                            "chapter_title": ch.get("title", ""),
                            "chapter_text": _card_text(ch),
                        },
                        "deconstruct_card",
                    )
                cards["entries"][no] = data  # 事件循环单线程：await 间串行改写，无竞争
                cards["done"] = len(cards["entries"])
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))

            await _run_units([_card_one(ch) for ch in todo])
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
        incomplete = [
            dim for dim in DIMENSION_KEYS
            if dim in selected and not (dims.get(dim, {}).get("state") == "completed" and dim in products)
        ]

        async def _run_dim(dim: str) -> None:
            await _check_cancel(task_id)
            dstate = dims.get(dim, {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""})
            sys_m, usr_m = load_layers(f"deconstruct_{dim}")
            pairs = [
                (no, line)
                for no, card in sorted(cards["entries"].items(), key=lambda kv: int(kv[0] or 0))
                if (line := _card_frag(no, card, dim))
            ]
            batches = _pack_pairs(pairs, CARD_BATCH_CHARS)
            dstate.update({"state": "running", "seg_done": 0, "seg_total": len(batches), "error": "",
                           "started_at": _now().isoformat()})
            dims[dim] = dstate
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))

            async def _batch(batch: list[tuple[str, str]]) -> str:
                async with _sem:
                    await _check_cancel(task_id)
                    ch_from, ch_to = batch[0][0] if batch else "1", batch[-1][0] if batch else "1"
                    state["activity"] = {
                        "label": f"正在归并 {names[dim]}（已完成 {dstate['seg_done']}/{dstate['seg_total']} 批）",
                        "at": _now().isoformat(),
                    }
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
                dstate["seg_done"] += 1  # 并发完成计数（gather 保序，partials 与批序一致）
                dims[dim] = dstate
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
                return json.dumps(data, ensure_ascii=False)

            batch_out = await _run_units([_batch(b) for b in batches])
            partials: list[str] = batch_out

            # 树收敛：多批产物反复合并直到单份（无头尾截断＝任意长度零丢失；串行——树形依赖）
            reduce_degraded = ""
            if len(partials) > 1:
                sys_r, usr_r = load_layers("deconstruct_reduce")
                try:
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
                            state["activity"] = {"label": f"正在收敛 {names[dim]}", "at": _now().isoformat()}
                            async with _sem:
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
                except _Cancelled:
                    raise
                except Exception as e:  # noqa: BLE001 — 收敛被拦（13路实测：reduce 输入脱敏后仍 1301，
                    # 分类器读的是全书恐怖梗概的语义，词表救不了）不拖垮维度：保留分段归并稿
                    reduce_degraded = (
                        f"reduce 收敛被模型拒绝（{str(e)[:60]}），保留 {len(partials)} 段归并稿"
                    )
                    _log.warning("REDUCE-DEGRADE %s: %s", dim, reduce_degraded)
                if reduce_degraded:
                    dstate["degraded"] = reduce_degraded

            final = _merge_final(partials)
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

        await _run_units([_run_dim(dim) for dim in incomplete])

        # ── 阶段三：图谱装配（deconstruct-graph/6）——开关关则跳过；病着也要出：
        #    装配异常只记 graph_error 留痕（导出端报可读 400），md 出口永不拖累 ──
        if (_graph_export_on() and state.get("caps_graph", True)
                and cards.get("entries") and not state.get("graph")):
            await _check_cancel(task_id)
            try:
                from deconstruct.graph import assemble, place_merge_input

                # 阶段 3.0：presence 补写（10.9 熔断预案落地）——卡上 characters 全名 ⊄ 在场者时，
                # 轻量调用逐人定位（只补名单、where 抄本章闭集），合并回卡片；达标章零调用
                backfill_failed = await _backfill_presence(
                    task_id, task, chapters, cards, dims, state, client, model,
                    graph_on=_graph_export_on(), caps=state.get("caps_graph", True), sem=_sem,
                )
                frags = place_merge_input(cards["entries"])
                place_merge = None
                truncated = False
                if frags:
                    frag_text = "\n".join(frags)
                    if len(frag_text) > MERGE_INPUT_CAP:
                        frag_text = frag_text[:MERGE_INPUT_CAP]
                        truncated = True
                    state["graph_phase"] = {"step": "place_merge"}
                    state["activity"] = {"label": "正在归并全书中地点", "at": _now().isoformat()}
                    await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
                    sys_pl, usr_pl = load_layers("deconstruct_place")
                    place_merge = await _call_with_retry(
                        client, model, (sys_pl, usr_pl),
                        {"book_name": task.book_name, "genre_or_unknown": "unknown",
                         "full_synopsis": full_synopsis[:_SYNOPSIS_CAP],
                         "seg_range": f"第1-{task.chapter_count}章" if task.chapter_count else "全本",
                         "excerpts": frag_text},
                        "deconstruct_place",
                    )
                await _check_cancel(task_id)  # 归并调用是新段边界：取消在此生效（评审 P3）
                state["graph_phase"] = {"step": "assemble"}
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
                graph = assemble(
                    book_name=task.book_name,
                    chapter_count=task.chapter_count,
                    words=task.total_chars,
                    cards=cards["entries"],
                    products=products,
                    place_merge=place_merge,
                    source_text=_quote_corpus(chapters),
                )
                if backfill_failed:
                    graph["meta"]["warnings"].append({
                        "kind": "presence_backfill_failed", "count": backfill_failed,
                        "msg": f"{backfill_failed} 章在场补写调用失败（重试穷尽），该章在场账留空（未知区）",
                    })
                if truncated:
                    graph["meta"]["warnings"].append({
                        "kind": "place_merge_truncated", "count": 1,
                        "msg": "地点归并输入超上限被截断：未覆盖地点按卡片原名补户（fallback 已兜底）",
                    })
                state["graph"] = graph
                state.pop("graph_phase", None)  # 终态不残留：轮询端以 phase 缺席＝阶段三已结束
                state.pop("activity", None)
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
            except _Cancelled:
                raise
            except Exception as e:  # noqa: BLE001 — 图谱不拖累任务：错误留痕，导出端 400
                state["graph_error"] = str(e)[:300]
                state.pop("graph_phase", None)
                state.pop("activity", None)
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
    except _Cancelled:
        await _patch(task_id, finished_at=_now())
        return
    except PromptPackMissing as e:
        await _fail(task_id, error={"message": f"写作能力包缺少拆书模板：{e}", "kind": "prompts_missing"})
        return
    except Exception as e:  # noqa: BLE001 — 终态收敛：任务失败保留已完成维度
        err_str = str(e)
        if "contentFilter" in err_str or "1301" in err_str:
            await _fail(task_id, error={
                "message": "已对原文做敏感词中性替换，模型的内容安全审核仍拒绝了该书的题材。"
                           "请更换模型（如 DeepSeek）或拆解其他作品。",
                "kind": "content_filter",
            })
            return
        await _fail(task_id, error={"message": err_str[:500], "kind": "pipeline"})
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
