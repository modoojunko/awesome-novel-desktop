"""拆解管线 v2（c-deconstruct-book 2.x，2026-10-13 用户拍板架构）——逐章拆卡＋分维度分级语义归并。

- v1→v2：prescan 梗概与「段×维度 map」合并为**每章一次拆卡调用**（十维碎片＋梗概，章级断点）；
  「每维度一次 reduce 且 40k 截断」改为**分级归并**：卡片碎片按字数分批归并（L1，复用十维度
  模板＝卡片归并口径）→ 归并产物**树状收敛**（reduce 轮次循环直到单份）——任意长度零截断。
- 模板 12 份（提示词仓 awesome-novel-prompts）：`deconstruct-card`、`deconstruct-{dim}`×10
  （输入为逐章卡片碎片）、`deconstruct-reduce`（通用树合并）。load_layers 分层，str.format 注入。
- 证据章号不靠模型记忆：碎片由代码盖 `【第N章】` 前缀，模板明令「章号只来自材料标注」。
- 单元级重试＋失败策略单源 `deconstruct/policy`（c-deconstruct-resilience）：瞬时错误
  （超时/429/5xx/未知）3 次尝试指数退避；鉴权/参数/路由一次定生死；内容审核按单元隔离；
  截断（finish_reason=length / JSON 不完整）拆组重试，MUST NOT 原样重发。
- 韧性三件套：熔断（连续单元失败→provider_unavailable 收场让出队列）、看门狗
  （无进展/墙钟→stalled 收场，DB 取消轮询 2s 贯穿在途调用）、单元账 `deconstruct_units`
  （card/card_batch/l1/reduce 逐单元落库＝断点续拆＋调用账；合批逐章产物行 card_product
  非调用，调用账与监控流水排除）。
- 能力感知预算（c-deconstruct-resilience D5/D6）：DECONSTRUCT_CAPS（或 vendor 表）给出
  上下文/输出上限 → 归并输入上限放大、输出预算放宽、**单遍归并**（碎片+梗概+开销 ≤ 输入预算
  且预计输出 ≤ 输出预算时跳过 L1/reduce，一次调用出终稿）；未知能力保守默认不阻塞。
- LLM 调用并发度＝DECONSTRUCT_CONCURRENCY（默认 4，=1 与旧串行实现逐字等价）：拆卡章间／
  维度间／维度内 L1 批次／在场补写四处并发，共享信号量限流；reduce 收敛保持串行（树形依赖）。
  纯 I/O 并发用 asyncio，无需子进程。
- 断点续拆：cards.entries 已有章号跳过；dims 中 state=completed 的维度跳过；
  L1 按批输入指纹复用单元账产物，reduce 从轮间检查点继续。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time

import httpx
from sqlalchemy import select

from db import async_session
from deconstruct import capabilities as caps_mod
from deconstruct import policy
from deconstruct.graph import (  # noqa: PLC2701 — 域内复用形状防御（graph 无回环）
    _TIME_TAGS,
    _clean,
    _dicts,
)
from deconstruct.sanitize import sanitize_for_model
from deconstruct.textparse import CARD_TEXT_LIMIT
from models.deconstruct import DIMENSION_KEYS, DeconstructJob, DeconstructUnit
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
# 兼容保留（旧测试/外部引用读它）：重试次数单源 policy.RETRY_MAX_ATTEMPTS（3 发含首发）
SEGMENT_RETRIES = policy.RETRY_MAX_ATTEMPTS - 1
# 并发调用上限（DECONSTRUCT_CONCURRENCY，默认 4；=1 即原串行）——拆书是 I/O 密集
# （等模型返回），asyncio 并发即可成倍提速、无需子进程；上限同时压住 429 限流风险
CONCURRENCY = max(1, int(os.environ.get("DECONSTRUCT_CONCURRENCY", "4") or 4))

# 非模型调用的账行（调用账/监控流水同口径排除，单源）：reduce_state＝归并轮间检查点；
# card_product＝合批成功后的逐章产物行——真实调用（耗时/token）记在 card_batch 行上，
# 产物行只证明「该章有卡」。不排除的话，一批 16 章会在流水里落 16 条 0s/0.0k 行，
# 还会把真实调用行挤出最近窗口（2026-10-21 真机：整屏小任务全是 0）。
NON_CALL_STAGES = frozenset({"reduce_state", "card_product"})

# 每 operation 输出 token 预算。归并类（deconstruct_{dim} L1 归并＋deconstruct_{dim}_reduce
# 树收敛）的 operation 名是动态的、不进本表——落 _MERGE_DEFAULT_TOKENS＝8192（默认 4096
# 会把 JSON 拦腰截断，真机实证三回：10-09 世界归并、10-18 structure/foreshadow 三连败、
# 10-20 《13路末班车》l1×6＋reduce×6 截断致 4 维降级分段稿）；拆卡单章 6144 不变；
# presence 补写/place 抽取单卡小输出钉 4096（c-deconstruct-merge-budget，接续 #896）。
_OP_MAX_TOKENS = {
    "deconstruct_card": 6144,
    "deconstruct_characters": 8192,
    "deconstruct_world": 8192,
    "deconstruct_presence": 4096,
    "deconstruct_place": 4096,
}
_MERGE_DEFAULT_TOKENS = 8192

# structure 单列小批：结构拍点契约「每章一行」逐章还原、无 dedup 压缩，且归并输出
# 会比碎片更丰满（≈1.5-2 倍字数），而碎片总量小（258 章仅约 2.3 万字）会被输入装箱
# 整本塞进单批——单批 256 行输出任何预算都吃不下；8000 字/批仍顶预算（真机复验
# 4 批只活 1 批，10-18 四连败）。4000 字/批 ≈ 40 章，输出 ≈4-5.5k token，
# 落 8192 预算内有余量；其余维度归并有真去重（伏笔/主线按对象收敛），装箱不变。
CARD_BATCH_CHARS_OVERRIDES = {"structure": 4000}


def _op_budget(operation: str, max_tokens: int | None) -> int:
    """单发调用的输出 token 预算：显式 max_tokens（能力感知预算）优先；动态归并 op
    落 8192 默认；表内 op 按表。"""
    if max_tokens is not None:
        return max_tokens
    return _OP_MAX_TOKENS.get(operation, _MERGE_DEFAULT_TOKENS)


def _dim_in_cap(dim: str, merge_in_cap: int) -> int:
    """维度 L1 归并的输入装箱上限：structure 走单列小批 override，其余按能力预算。"""
    return min(CARD_BATCH_CHARS_OVERRIDES.get(dim, merge_in_cap), merge_in_cap)


def _graph_export_on() -> bool:
    """图谱导出总开关（默认开；关＝跳过阶段三装配与导出三件套——评审：开关＝具名交付物）。"""
    return os.environ.get("DECONSTRUCT_GRAPH_EXPORT", "1") != "0"

_CANCELLED = "cancelled"

# ── 韧性运行时（c-deconstruct-resilience）────────────────────────────────────
# 看门狗/墙钟/取消轮询参数：env 可调，测试把间隔与阈值调小
_WATCH_INTERVAL = max(0.2, float(os.environ.get("DECONSTRUCT_WATCH_INTERVAL", "2") or 2))
# 无进展阈值：拆卡/归并分别设——要大于「单元 3 发重试最坏总时长」，
# 误杀面由「成功单元会 touch」兜住（只惩罚持续无单元产出的挂死）
_STALL_CARD_SEC = max(30.0, float(os.environ.get("DECONSTRUCT_STALL_CARD_SEC", "420") or 420))
_STALL_MERGE_SEC = max(60.0, float(os.environ.get("DECONSTRUCT_STALL_MERGE_SEC", "1500") or 1500))
# 任务墙钟兜底：真实 258 章任务 ≈21 分钟，90 分钟覆盖 60 万字上限仍有富余
_WALL_CLOCK_SEC = max(300.0, float(os.environ.get("DECONSTRUCT_WALL_CLOCK_SEC", "5400") or 5400))
# 熔断阈值：连续 N 个单元瞬时失败穷尽 → provider_unavailable 收场
_BREAKER_THRESHOLD = max(3, CONCURRENCY)


class _Stopped(Exception):
    """看门狗/熔断/取消注入的停止信号——reason 决定任务终态归类。"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _now():
    """DateTime 列必须收 datetime 对象（SQLite 绑 str 即 StatementError，行为测试实锤）。"""
    from datetime import UTC, datetime

    return datetime.now(UTC).replace(tzinfo=None)


class _Stopper:
    """任务级停止器：取消（DB 轮询）与异常中止（看门狗/熔断）共用一个事件。

    reason：cancelled=用户取消（状态列已由端点落库）；stalled=无进展；wall=墙钟；
    provider_unavailable=熔断。last_progress 是看门狗的进展锚（monotonic）。
    """

    def __init__(self) -> None:
        self.event = asyncio.Event()
        self.reason = ""
        self.last_progress = time.monotonic()
        self.phase = "card"  # card | merge——无进展阈值随阶段切换

    def stop(self, reason: str) -> None:
        if not self.event.is_set():
            self.reason = reason
            self.event.set()

    def touch(self) -> None:
        self.last_progress = time.monotonic()


class _Breaker:
    """连续瞬时失败熔断：单元重试穷尽才计数，成功即清零；单个 429 不触发。"""

    def __init__(self, threshold: int, stopper: _Stopper) -> None:
        self.threshold = threshold
        self._stopper = stopper
        self.consecutive = 0

    def record_success(self) -> None:
        self.consecutive = 0

    def record_failure(self, kind: str) -> None:
        if kind not in policy.TRANSIENT_KINDS:
            return
        self.consecutive += 1
        if self.consecutive >= self.threshold:
            self._stopper.stop("provider_unavailable")


class _Watchdog:
    """任务看门狗：取消轮询（贯穿在途调用）＋无进展判定＋墙钟兜底。

    与 run_task 同事件循环跑后台 task；stop() 取消轮询本身。
    DB 取消轮询是取消端点（写状态列）与在途 HTTP 之间的桥：2s 内把用户取消
    变成 stopper 事件，调用层 race 立刻掐断请求——「取消 10 秒内生效」的实现点。
    """

    def __init__(self, task_id: str, stopper: _Stopper) -> None:
        self._task_id = task_id
        self._stopper = stopper
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.ensure_future(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 — 收尾不二次爆炸
                _log.debug("watchdog stop swallow", exc_info=True)
            self._task = None

    async def _loop(self) -> None:
        started = time.monotonic()
        while True:
            await asyncio.sleep(_WATCH_INTERVAL)
            if self._stopper.event.is_set():
                return
            try:
                status = await _status_of(self._task_id)
            except Exception:  # noqa: BLE001 — DB 抖动下一轮再查
                _log.debug("watchdog status poll failed", exc_info=True)
                continue
            if status == _CANCELLED:
                self._stopper.stop("cancelled")
                return
            idle = time.monotonic() - self._stopper.last_progress
            stall = _STALL_MERGE_SEC if self._stopper.phase == "merge" else _STALL_CARD_SEC
            if idle > stall:
                self._stopper.stop("stalled")
                return
            if time.monotonic() - started > _WALL_CLOCK_SEC:
                self._stopper.stop("wall")
                return


def _input_hash(*parts: str) -> str:
    sha = hashlib.sha256()
    for p in parts:
        sha.update(p.encode("utf-8", "ignore"))
        sha.update(b"\x00")
    return sha.hexdigest()[:40]


async def _unit_upsert(task_id: str, stage: str, dim: str, unit_key: str, **fields) -> None:
    """单元账落库（断点复用＋调用账事实源）：成功产物/失败归因/计数一次写齐。"""
    allowed = {"status", "attempts", "error_kind", "error_msg", "duration_ms",
               "tokens_in", "tokens_out", "output_json", "input_hash"}
    async with async_session() as session:
        row = (
            await session.execute(
                select(DeconstructUnit).where(
                    DeconstructUnit.task_id == task_id,
                    DeconstructUnit.stage == stage,
                    DeconstructUnit.dim == dim,
                    DeconstructUnit.unit_key == unit_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = DeconstructUnit(task_id=task_id, stage=stage, dim=dim, unit_key=unit_key)
            session.add(row)
        for k, v in fields.items():
            if k in allowed:
                setattr(row, k, v)
        await session.commit()


async def _unit_running(task_id: str, stage: str, dim: str, unit_key: str) -> None:
    """调度落账（c-deconstruct-monitor）：单元派发即写 running 行——监控「在途」与
    「最近」明细当场可见（boss 2026-10-19：具体的调度任务要在明细里刷新出来）；
    完成时 _unit_upsert 按唯一键覆盖同行为终态。取消/熔断/看门狗中断的余波
    （running 残留）由任务终局 _sweep_running 统一收敛。"""
    await _unit_upsert(task_id, stage, dim, unit_key, status="running")


async def _sweep_running(task_id: str) -> None:
    """任务终局清扫：残留 running 行（停止余波）一律置 failed(cancelled)，
    防止在途账永久虚高。每次 run_task 的 finally 调用（成功路径无残留，幂等）。"""
    async with async_session() as session:
        rows = (
            await session.scalars(
                select(DeconstructUnit).where(
                    DeconstructUnit.task_id == task_id,
                    DeconstructUnit.status == "running",
                )
            )
        ).all()
        for r in rows:
            r.status = "failed"
            r.error_kind = "cancelled"
        await session.commit()


async def _units_done(task_id: str, stage: str, dim: str) -> dict[str, str]:
    """已完成单元映射（unit_key → output_json）——续拆只补未完成单元的读取口。"""
    async with async_session() as session:
        rows = (
            await session.scalars(
                select(DeconstructUnit).where(
                    DeconstructUnit.task_id == task_id,
                    DeconstructUnit.stage == stage,
                    DeconstructUnit.dim == dim,
                    DeconstructUnit.status == "done",
                )
            )
        ).all()
        return {r.unit_key: r.output_json for r in rows}


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


async def _genre_vocab_names() -> str:
    """题材库词表（每行一个展示名）——genre 维度 L1 注入 {genre_vocab}，让题材
    从词表逐字选词（对齐书架题材胶囊），词表外模型自行降 low。查询失败给空串
    （模板分支回退自由词，不阻塞拆书）。"""
    try:
        from sqlalchemy import select

        from db import async_session
        from models.genre import Genre

        async with async_session() as db:
            names = (
                await db.scalars(select(Genre.name).order_by(Genre.name))
            ).all()
        return "\n".join(str(n).strip() for n in names if str(n).strip())
    except Exception:  # noqa: BLE001 — 词表拿不到不挡拆书
        return ""


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


async def _chat_json(client, model: str, system: str, user: str, operation: str) -> dict:
    """单发 JSON 调用并解析（保留旧直调形状：超时钉测试断言 600s/read 口径）。"""
    raw = await _chat_raw(client, model, system, user, operation)
    return _parse_json_response(raw)


# 产物 JSON 键 → 作家中文标签（渲染层单源；未登记的键回退原键展示）
_MD_LABELS: dict[str, str] = {
    "intro": "简介", "confidence": "可信度", "genre": "题材", "tags": "题材标签",
    "promise": "题材承诺", "no_power": "舞台类型", "stage": "地理与舞台",
    "power": "力量体系", "cost": "代价", "history": "大事记", "factions": "势力",
    "constraints": "禁忌铁律", "extra": "其他设定", "key": "名", "value": "内容",
    "characters": "人物卡", "name": "名", "aliases": "别名", "role": "定位",
    "persona": "人物速写", "gender": "性别", "age": "年龄", "race": "种族",
    "faction": "势力·身份", "look": "外貌", "speech": "语言特征",
    "background": "背景", "plot": "关键行动", "evidence_ch": "证据章节",
    "edges": "关系边", "from": "一方", "to": "另一方", "rel_type": "关系类型",
    "stance": "立场", "note": "说明", "quote": "原文佐证", "raw": "原文措辞",
    "members": "成员", "arcs": "剧情弧", "fullstory": "主线全景",
    "summary": "梗概",
    "ending": "结局", "scene": "结尾场景", "hero": "主角结局", "tone": "收束基调",
    "ch_start": "起", "ch_end": "止", "volumes": "分卷", "title": "题",
    "conflict": "冲突", "chapters": "章", "ch_range": "章范围",
    "rules": "写作规则", "craft": "表现手法", "examples": "原文短例",
    "example": "例", "how": "怎么用", "taboo": "避免的写法",
    "hooks": "伏笔", "type": "类型", "priority": "重要度", "desc": "内容",
    "plant_ch": "埋设章", "payoff_ch": "回收章", "status": "状态",
    "result": "结果",
}
_CONF_CN = {"high": "高", "mid": "中", "low": "低"}
_MD_FOOTNOTE = (
    "说明：条目里标注的章号是原文出处；可信度（高/中/低）表示该条结论有多少原文"
    "依据——高＝有直接依据，中＝含推断，低＝证据较弱或原文说法有分歧。"
)


def _md_cell(key: str, value) -> str:
    """单个字段 → 「中文标签：值」；confidence 值翻成高/中/低；空值不给。"""
    text = str(value or "").strip()
    if not text:
        return ""
    if key == "confidence":
        text = _CONF_CN.get(text, text)
    label = _MD_LABELS.get(key, key)
    return f"{label}：{text}"


def _render_md(dim: str, data: dict, book_name: str, covered: str) -> str:
    """JSON → Markdown（代码渲染：模型不直出 md）。产物仅静态呈现，应用内不预览不编辑。

    渲染对齐作家视角：键名翻中文标签、可信度翻高/中/低；顶部单值 confidence 并入
    抬头行不单独成节（2026-10-20 拍板：拆书产物按设定字段契约归纳、呈现说人话）。
    """
    if not isinstance(data, dict):
        data = {"result": data}
    conf_top = _CONF_CN.get(str(data.get("confidence", "")).strip(), "")
    conf_note = f" · 可信度：{conf_top}" if conf_top else ""
    lines = [
        f"# {dim}｜{book_name}",
        "",
        f"> 覆盖范围：{covered} · 由拆书任务生成{conf_note}",
        "",
    ]
    for key, value in data.items():
        if key == "confidence":
            continue  # 单值可信度已在抬头行
        # 无正文不出节：空列表/空对象/空标量只给标题的空节对作家是噪音（评审 P3）
        if not value or (isinstance(value, (dict, list, str)) and not str(value).strip()):
            continue
        lines.append(f"## {_MD_LABELS.get(key, key)}")
        lines.append("")
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    head_key = next((k for k in ("name", "title", "desc") if str(item.get(k, "")).strip()), "")
                    head = str(item.get(head_key, "")).strip() if head_key else ""
                    body = "；".join(
                        cell for cell in (
                            _md_cell(k, v) for k, v in item.items()
                            if k not in ("name", "title") and v
                        ) if cell
                    )
                    lines.append(f"- {('**' + head + '**　') if head else ''}{body}")
                else:
                    lines.append(f"- {item}")
        elif isinstance(value, dict):
            # 对象值（如 mainplot.ending 三格）：逐字段展开成中文标签行，
            # 不给 Python dict repr（评审 P1：作家看到 {'scene': …} 原文）
            for k, v in value.items():
                cell = _md_cell(k, v)
                if cell:
                    lines.append(f"- {cell}")
        else:
            # 标量节正文＝裸值（标签已在节标题；再带前缀会「标题×2」）
            lines.append(str(value or "").strip())
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(_MD_FOOTNOTE)
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


async def _chat_raw(client, model: str, system: str, user: str, operation: str, *,
                    max_tokens: int | None = None, usage: dict | None = None,
                    meta: dict | None = None, stopper: _Stopper | None = None) -> str:
    """单发 JSON 调用：取消竞速（stopper 置位即掐断在途请求）＋输出预算/超时按 op 计算。

    ai_client 的 read=90 是按 4096 tokens 生成上限校准的（ai-client-timeout D1）；
    归并类提到 8192 后 90 秒写不完（真机实证：五批连排 180s 超时），长输出
    操作改传 read=600——收敛最坏等待仍由单元级重试次数兜住。
    """
    budget = _op_budget(operation, max_tokens)
    timeout = None
    if budget >= 8192:
        timeout = httpx.Timeout(connect=10.0, read=600.0, write=30.0, pool=10.0)

    async def _do() -> str:
        return await client.chat(
            model=model,
            system=system,
            messages=[{"role": "user", "content": user}],
            max_tokens=budget,
            json_mode=True,
            operation=operation,
            timeout=timeout,
            usage=usage if usage is not None else {},
            meta=meta if meta is not None else {},
        )

    if stopper is None:
        return await _do()
    chat_task = asyncio.ensure_future(_do())
    stop_wait = asyncio.ensure_future(stopper.event.wait())
    try:
        await asyncio.wait({chat_task, stop_wait}, return_when=asyncio.FIRST_COMPLETED)
        if chat_task.done() and not chat_task.cancelled():
            return chat_task.result()
        if chat_task.done():
            chat_task.result()  # 透传任务内异常
        chat_task.cancel()
        raise _Stopped(stopper.reason or "cancelled")
    finally:
        stop_wait.cancel()
        if not chat_task.done():
            chat_task.cancel()


async def _call_with_retry(client, model, system_tpl, user_vars, operation, *,
                           max_tokens: int | None = None, stopper: _Stopper | None = None,
                           breaker: _Breaker | None = None, usage: dict | None = None,
                           meta: dict | None = None, info: dict | None = None,
                           jsonl: bool = False) -> str:
    """单元级调用：失败策略单源 deconstruct/policy（c-deconstruct-resilience D1）。

    - 瞬时（超时/429/5xx/未知）：RETRY_MAX_ATTEMPTS 次尝试，指数退避＋全抖动，
      429 优先 Retry-After；退避等待可被取消打断；
    - 确定性（鉴权/参数/路由/内容审核/截断/坏输出）：一次定生死，重试无意义
      （同输入同预算重发注定同败——真机实证：截断 reduce 三连败）；
    - provider 把「输入超上下文/输出超上限」以 400 表达时归为截断同族（拆组自愈）；
    - 熔断计数按**单元穷尽**（不是按发）：单个 429/单发失败不熔断；
    - jsonl=True：合批调用返回原始文本（JSONL 由 _parse_batch_cards 解析，
      单文档平衡块解析会截断多行输出）；
    - user 变量在咽喉处统一脱敏（_sanitize_vars）：章节原文＋归并/reduce 碎片全覆盖。
    """
    system, user_tpl = system_tpl
    user_vars = _sanitize_vars(user_vars)
    usage_d = usage if usage is not None else {}
    meta_d = meta if meta is not None else {}
    last_err: policy.UnitError | None = None
    for attempt in range(1, policy.RETRY_MAX_ATTEMPTS + 1):
        if stopper is not None and stopper.event.is_set():
            raise _Stopped(stopper.reason)
        try:
            raw = await _chat_raw(client, model, system, user_tpl.format(**user_vars),
                                  operation, max_tokens=max_tokens, usage=usage_d,
                                  meta=meta_d, stopper=stopper)
            if jsonl:
                parsed = raw  # 合批：原文返回（JSONL 解析在调用方）
            else:
                parsed = _parse_json_response(raw)  # 解析在重试循环内：截断参与分类
            if breaker is not None:
                breaker.record_success()
            if info is not None:
                info["attempts"] = attempt
            return parsed
        except _Stopped:
            raise
        except Exception as e:  # noqa: BLE001 — 分类后按策略放行
            kind = policy.classify(e)
            if kind == policy.KIND_CONFIG and caps_mod.oversize_reject(e):
                kind = policy.KIND_TRUNCATED  # 输入超上下文 → 拆半重试，不是配置错误
            last_err = policy.UnitError(kind, str(e), policy.retry_after_of(e))
            if not last_err.transient:
                raise last_err
            if attempt < policy.RETRY_MAX_ATTEMPTS:
                await policy.cancellable_sleep(
                    policy.backoff_seconds(attempt, last_err.retry_after),
                    stopper.event if stopper is not None else None,
                )
    if breaker is not None and last_err is not None:
        breaker.record_failure(last_err.kind)
    if stopper is not None and stopper.event.is_set():
        raise _Stopped(stopper.reason)
    raise last_err if last_err is not None else policy.UnitError(
        policy.KIND_UNKNOWN, "模型调用失败")


async def _run_units(units: list) -> list:
    """单元集执行：CONCURRENCY=1＝逐个 await（与旧串行逐字等价：调用序/取消时机不变）；
    否则 gather 收齐在途单元再抛首错（并发下取消/失败的越界≤上限个单元，断点保留已完成）。
    _Stopped（取消/熔断/看门狗）优先于其他异常上抛——停止后其余单元的失败只是停止的余波。"""
    if CONCURRENCY == 1:
        out: list = []
        unit_iter = iter(units)
        for c in unit_iter:
            try:
                out.append(await c)
            except BaseException:
                for rest in unit_iter:  # 停止后剩余协程显式关闭（消 never-awaited 噪音）
                    if asyncio.iscoroutine(rest):
                        rest.close()
                raise
        return out
    outcomes = await asyncio.gather(*units, return_exceptions=True)
    stopped = next((oc for oc in outcomes if isinstance(oc, _Stopped)), None)
    if stopped is not None:
        raise stopped
    for oc in outcomes:
        if isinstance(oc, BaseException):
            raise oc
    return outcomes


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
                             graph_on: bool, caps: bool, sem: asyncio.Semaphore,
                             stopper: _Stopper | None = None,
                             breaker: _Breaker | None = None) -> int:
    """阶段 3.0（10.1a 熔断预案落地）：在场缺口选择性补写（章间并发，sem 共享限流）。

    - 逐章检测 characters 全名 ⊆ presence.who；缺口非空才触发轻量调用（达标章零成本）；
    - 补写只收名单内 who（模型越权输出丢弃）、where 强制本章闭集（越权地名降空串→未知区）；
    - 逐章 try/except：单章失败计入计数并跳过——图谱病着也要出（评审 P1-1 三级降级）；
      单元账记 failed 行（error_kind 归因），stopper 置位（取消/熔断）则立刻上抛；
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
            if stopper is not None and stopper.event.is_set():
                raise _Stopped(stopper.reason)
            state["activity"] = {"label": f"正在补写在场 第{no}章", "at": _now().isoformat()}
            phase["done"] += 1
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
            known_list = [_clean(pl.get("name")) for pl in _dicts(card.get("places")) if _clean(pl.get("name"))]
            known_set = set(known_list)
            known = "、".join(known_list) or "（本章无已知地点，where 一律空串）"
            started = time.monotonic()
            usage: dict = {}
            info: dict = {}
            ukey = _input_hash("presence", no, *sorted(missing))
            await _unit_running(task_id, "presence", "", ukey)
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
                    stopper=stopper, breaker=breaker, usage=usage, info=info,
                )
            except _Cancelled:
                raise
            except _Stopped:
                raise
            except Exception as _e:  # noqa: BLE001 — 评审 P1-1：单章失败跳过继续，不拖垮整本图谱
                _log.warning("BF-FAIL %s: %r", no, _e)
                failed += 1
                kind = _e.kind if isinstance(_e, policy.UnitError) else policy.KIND_UNKNOWN
                await _unit_upsert(task_id, "presence", "", ukey, status="failed",
                                   attempts=int(info.get("attempts", 1)), error_kind=kind,
                                   error_msg=str(_e)[:300], duration_ms=int((time.monotonic() - started) * 1000))
                return True
            if stopper is not None:
                stopper.touch()
            await _unit_upsert(task_id, "presence", "", ukey, status="done",
                               attempts=int(info.get("attempts", 1)),
                               duration_ms=int((time.monotonic() - started) * 1000),
                               tokens_in=int(usage.get("tokens_in", 0) or 0),
                               tokens_out=int(usage.get("tokens_out", 0) or 0))
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


def _merge_budgets(caps) -> tuple[int, int]:
    """归并输入字符上限＋输出 token 预算。

    能力保守（未知模型）＝现行口径（CARD_BATCH_CHARS / 8192），行为零漂移；
    env 显式覆盖（DECONSTRUCT_CAPS）或 vendor 已知表才放大——1M 上下文由此解锁
    「单遍归并」（全部碎片一批喂入），输出超预算仍由拆半自愈兜底。
    """
    if caps.source in ("env", "known"):
        in_cap = max(CARD_BATCH_CHARS, caps_mod.input_budget_chars(caps))
        out_tokens = caps_mod.merge_max_tokens(caps)
    else:
        in_cap = CARD_BATCH_CHARS
        out_tokens = _OP_MAX_TOKENS.get("deconstruct_world", 8192)
    return in_cap, out_tokens


_CARD_OUT_TOKEN_ESTIMATE = 1500  # 单章卡片输出估算（真机 258 章均值 2.35KB ≈ 1.5k tokens）


def _card_batch_size(caps) -> int:
    """拆卡合批大小（c-deconstruct-resilience D6）：调用数的大头杠杆（258 章 → 数十次）。

    DECONSTRUCT_CARD_BATCH：off=强制逐章；数字=钉死每批章数（1–30）；
    auto/未设＝能力显式（DECONSTRUCT_CAPS 或 vendor 已知表）才按输出预算合批
    ——未知能力保守逐章，行为零漂移。批内输出超预算由「整批退回逐章」兜底。
    """
    raw = os.environ.get("DECONSTRUCT_CARD_BATCH", "auto").strip().lower()
    if raw == "off":
        return 1
    if raw.isdigit():
        return max(1, min(30, int(raw)))
    if caps.source not in ("env", "known"):
        return 1
    # 预算同源＋同余量（c-deconstruct-merge-budget）：card_batch 调用传的正是
    # merge_out_tokens，批大小按「预算×0.75」折算——与 usable_output 的安全余量系数
    # 一致（评审 P2：直接除预算只剩 4% 余量，高方差批必截退回白烧整轮）。
    # vendor 数据放大（如 deepseek 393K）后批不再超出实传预算。
    return max(1, min(30, int(caps_mod.merge_max_tokens(caps) * 0.75) // _CARD_OUT_TOKEN_ESTIMATE))


def _parse_batch_cards(raw: str, allowed: set[str]) -> dict[str, dict] | None:
    """合批输出解析：JSONL（一行一张卡，no 首字段）优先；回退 {"cards":[…]} 包裹形。

    全不可解析 → None（整批退回逐章）；行级缺章只回缺章集合（调用方逐章补）；
    越权章号/重复行丢弃——章号只认代码章标，禁止模型自编。
    """
    text = (raw or "").strip()
    if not text:
        return None
    parsed: list[dict] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except ValueError:
            parsed = []
            break
        if isinstance(obj, dict):
            parsed.append(obj)
    if parsed and all("no" not in obj for obj in parsed):
        # 单行包裹形 {"cards":[…]}：每行都能 json.loads 但没有 no 字段——解包取 cards
        items = next((obj.get("cards") for obj in parsed if isinstance(obj.get("cards"), list)), None)
        parsed = [x for x in (items or []) if isinstance(x, dict)]
    if not parsed:  # JSONL 不成立 → 整文平衡块回退
        try:
            data = _parse_json_response(text)
        except ValueError:
            return None
        items = data.get("cards") if isinstance(data, dict) else None
        parsed = [x for x in items if isinstance(x, dict)] if isinstance(items, list) else []
    out: dict[str, dict] = {}
    for obj in parsed:
        no = str(obj.get("no", "")).strip()
        if no not in allowed or no in out:
            continue
        card = {k: v for k, v in obj.items() if k != "no"}
        out[no] = card
    return out or None


def _task_kind(unit_kind: str) -> str:
    """单元错误类别 → 任务 error.kind（未知沿用 pipeline 口径，兼容既有前端）。"""
    return {
        policy.KIND_UNKNOWN: "pipeline",
        policy.KIND_TIMEOUT: "timeout",
        policy.KIND_RATE_LIMIT: "rate_limit",
        policy.KIND_UPSTREAM: "provider_unavailable",
        policy.KIND_AUTH: "auth",
        policy.KIND_CONFIG: "config",
        policy.KIND_ROUTE: "route",
        policy.KIND_CONTENT_FILTER: "content_filter",
        policy.KIND_INVALID_OUTPUT: "invalid_output",
        policy.KIND_TRUNCATED: "truncated",
    }.get(unit_kind, "pipeline")


async def run_task(task_id: str) -> None:
    """执行一个拆书任务（dispatcher 串行调用；亦为断点续拆入口）。"""
    task = await _load_task(task_id)
    if task is None:
        return
    try:
        from deconstruct.service import resolve_client

        client, model = await resolve_client(
            task.user_id, task.api_config_id, task.ai_model,
            thinking=getattr(task, "thinking_mode", "off") or "off",
        )
    except ValueError as e:
        await _fail(task_id, error={"message": str(e), "kind": "model"})
        return

    chapters = await _load_chapters(task)
    state = await _read_dims(task_id)
    selected = _selected(task)
    dims = state.get("dims", {})

    stopper = _Stopper()
    breaker = _Breaker(_BREAKER_THRESHOLD, stopper)
    watch = _Watchdog(task_id, stopper)
    watch.start()
    # 任务级告警账（进 dims_json 顶键，_state_json 保留未知顶键）：单元隔离的
    # 章级/批级失败都留痕，详情页可见——不再「全绿但实际缺章/降级」
    warnings: list[str] = state.setdefault("warnings", [])
    cf_chapters: list[str] = []

    try:
        _sem = asyncio.Semaphore(CONCURRENCY)  # 全管线共享限流：卡/L1/补写/reduce 统一在册
        vendor = getattr(client, "_vendor", "") or ""
        caps = caps_mod.caps_for(vendor=vendor, model=model)
        state["caps_note"] = {  # 能力口径入任务账：能力未知可见，预算来源可审计
            "context_window": caps.context_window,
            "max_output_tokens": caps.max_output_tokens,
            "source": caps.source,
        }
        merge_in_cap, merge_out_tokens = _merge_budgets(caps)

        # ── 阶段一：逐章拆卡（章级断点：entries 已有章号跳过；章间并发）──
        cards = state.get("cards", {"state": "queued", "done": 0, "entries": {}})
        if cards.get("state") != "completed":
            cards.setdefault("entries", {})
            cards["state"] = "running"
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
            sys_c, usr_c = load_layers("deconstruct_card")
            todo = [ch for ch in chapters if str(ch.get("no", 0)) not in cards["entries"]]

            batch_size = _card_batch_size(caps)
            batch_tpl = None
            if batch_size > 1 and len(todo) > 1:
                try:
                    batch_tpl = load_layers("deconstruct_card_batch")
                except Exception:  # noqa: BLE001 — 老包无合批模板＝包版本窗：逐章（回退口径）
                    batch_tpl = None
                    batch_size = 1

            async def _card_one(ch: dict) -> None:
                async with _sem:
                    await _check_cancel(task_id)
                    if stopper.event.is_set():
                        raise _Stopped(stopper.reason)
                    no = str(ch.get("no", 0))
                    state["activity"] = {"label": f"正在拆解 第{no}章", "at": _now().isoformat()}
                    await _unit_running(task_id, "card", "", no)
                    started = time.monotonic()
                    usage: dict = {}
                    info: dict = {}
                    ch_hash = _input_hash(str(ch.get("text", ""))[:4000])
                    card_vars = {
                        "book_name": task.book_name,
                        "chapter_no": no,
                        "chapter_title": ch.get("title", ""),
                        "chapter_text": _card_text(ch),
                    }
                    try:
                        try:
                            data = await _call_with_retry(
                                client, model, (sys_c, usr_c), card_vars,
                                "deconstruct_card",
                                stopper=stopper, breaker=breaker, usage=usage, info=info,
                            )
                        except policy.UnitError as e:
                            if e.kind != policy.KIND_TRUNCATED:
                                raise
                            # 截断：提输出预算再试一次（拆组对单章不适用——章是最小单元）
                            usage, info = {}, {}
                            data = await _call_with_retry(
                                client, model, (sys_c, usr_c), card_vars,
                                "deconstruct_card", max_tokens=8192,
                                stopper=stopper, breaker=breaker, usage=usage, info=info,
                            )
                    except _Cancelled:
                        raise
                    except _Stopped:
                        raise
                    except policy.UnitError as e:
                        if e.kind in (policy.KIND_CONTENT_FILTER, policy.KIND_INVALID_OUTPUT,
                                      policy.KIND_TRUNCATED):
                            # 单元隔离：该章不产出、任务继续；单元账记 failed，续拆只补该章
                            cf_chapters.append(no)
                            await _unit_upsert(task_id, "card", "", no, status="failed",
                                               attempts=int(info.get("attempts", 1)),
                                               error_kind=e.kind, error_msg=e.message[:300],
                                               duration_ms=int((time.monotonic() - started) * 1000),
                                               input_hash=ch_hash)
                            return
                        raise
                    stopper.touch()
                    cards["entries"][no] = data  # 事件循环单线程：await 间串行改写，无竞争
                    cards["done"] = len(cards["entries"])
                    await _unit_upsert(task_id, "card", "", no, status="done",
                                       attempts=int(info.get("attempts", 1)),
                                       duration_ms=int((time.monotonic() - started) * 1000),
                                       tokens_in=int(usage.get("tokens_in", 0) or 0),
                                       tokens_out=int(usage.get("tokens_out", 0) or 0),
                                       output_json=json.dumps(data, ensure_ascii=False),
                                       input_hash=ch_hash)
                    await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))

            async def _card_batch_one(batch: list[dict]) -> None:
                """合批拆卡：一次调用出多张卡（JSONL 一行一张，章标由代码盖在材料上）。

                任何单元级失败/解析不齐 → 坏行或缺章**退回逐章**（单章失败沿用既有
                隔离口径）——合批只降调用数，永不放大单章损失面。
                失败账：批次尝试比照其他阶段落 failed 行（评审 P3——退回成功也不
                该抹掉这次失败尝试的 kind/attempts/duration）。
                成功账：真实调用（耗时/token/重试）只记 card_batch 行；逐章产物另记
                card_product（非调用行，进不了调用账与监控流水）。
                """
                nos = [str(ch.get("no", 0)) for ch in batch]
                chapters_block = "\n\n".join(
                    f"【第{ch.get('no', 0)}章】{ch.get('title', '')}\n{_card_text(ch)}"
                    for ch in batch
                )
                bkey = _input_hash(chapters_block[:2000])
                # 流水 label 具体到调度对象（c-deconstruct-monitor 拍板）：章号区间附在
                # 输入指纹后当单元键——input_hash 仍只存指纹本身。
                ukey = f"{bkey}:{nos[0]}-{nos[-1]}"
                started = time.monotonic()
                usage: dict = {}
                info: dict = {}
                try:
                    async with _sem:
                        await _check_cancel(task_id)
                        if stopper.event.is_set():
                            raise _Stopped(stopper.reason)
                        state["activity"] = {
                            "label": f"正在拆解 第{nos[0]}-{nos[-1]}章（合批 {len(batch)} 章）",
                            "at": _now().isoformat(),
                        }
                        await _unit_running(task_id, "card_batch", "", ukey)
                        raw = await _call_with_retry(
                            client, model, batch_tpl,
                            {"book_name": task.book_name, "chapters_block": chapters_block},
                            "deconstruct_card_batch",
                            max_tokens=merge_out_tokens, stopper=stopper, breaker=breaker,
                            usage=usage, info=info, jsonl=True,
                        )
                except _Cancelled:
                    raise
                except _Stopped:
                    raise
                except policy.UnitError as e:
                    await _unit_upsert(task_id, "card_batch", "", ukey, status="failed",
                                       attempts=int(info.get("attempts", 1)),
                                       error_kind=e.kind, error_msg=e.message[:300],
                                       duration_ms=int((time.monotonic() - started) * 1000),
                                       input_hash=bkey)
                    if e.kind in (policy.KIND_AUTH, policy.KIND_CONFIG, policy.KIND_ROUTE):
                        raise  # 确定性致命：退回逐章注定同败（评审 P2），立即终局
                    await _run_units([_card_one(ch) for ch in batch])  # 瞬时/审核/截断：退回逐章
                    return
                except Exception as e:  # noqa: BLE001 — 合批失败整批退回逐章（降级不放大损失面）
                    await _unit_upsert(task_id, "card_batch", "", ukey, status="failed",
                                       attempts=int(info.get("attempts", 1)),
                                       error_kind=policy.KIND_UNKNOWN, error_msg=str(e)[:300],
                                       duration_ms=int((time.monotonic() - started) * 1000),
                                       input_hash=bkey)
                    await _run_units([_card_one(ch) for ch in batch])
                    return
                parsed = _parse_batch_cards(raw, set(nos))
                if parsed is None:
                    # 解析不齐/坏行＝无效输出：记失败账后退回逐章（耗时按实测，不写 0）
                    await _unit_upsert(task_id, "card_batch", "", ukey, status="failed",
                                       attempts=int(info.get("attempts", 1)),
                                       error_kind=policy.KIND_INVALID_OUTPUT,
                                       error_msg="合批输出无法解析",
                                       duration_ms=int((time.monotonic() - started) * 1000),
                                       input_hash=bkey)
                    await _run_units([_card_one(ch) for ch in batch])
                    return
                stopper.touch()
                await _unit_upsert(task_id, "card_batch", "", ukey,
                                   status="done", attempts=int(info.get("attempts", 1)),
                                   duration_ms=int((time.monotonic() - started) * 1000),
                                   tokens_in=int(usage.get("tokens_in", 0) or 0),
                                   tokens_out=int(usage.get("tokens_out", 0) or 0))
                missing: list[dict] = []
                for ch in batch:
                    no = str(ch.get("no", 0))
                    data = parsed.get(no)
                    if data is None:
                        missing.append(ch)
                        continue
                    cards["entries"][no] = data
                    cards["done"] = len(cards["entries"])
                    # 产物行（非模型调用）：耗时/token 全在 card_batch 行上，这里只证明
                    # 「该章有卡」——调用账与流水按 NON_CALL_STAGES 排除，防空值行刷屏。
                    await _unit_upsert(task_id, "card_product", "", no, status="done",
                                       attempts=int(info.get("attempts", 1)),
                                       output_json=json.dumps(data, ensure_ascii=False),
                                       input_hash=_input_hash(str(ch.get("text", ""))[:4000]))
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
                if missing:  # 行级缺章：逐章补（批内其余章已落账）
                    await _run_units([_card_one(ch) for ch in missing])

            if batch_tpl is not None and batch_size > 1 and len(todo) > 1:
                batches = [todo[i : i + batch_size] for i in range(0, len(todo), batch_size)]
                await _run_units([_card_batch_one(b) for b in batches])
            else:
                await _run_units([_card_one(ch) for ch in todo])
            cards["state"] = "completed"
            if cf_chapters:
                warnings.append(
                    f"{len(cf_chapters)} 章拆卡被模型拒绝或输出损坏已跳过（续拆可补）："
                    f"第{'、'.join(cf_chapters[:20])}章"
                )
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))

        stopper.phase = "merge"
        full_synopsis = _synopses(cards)
        # 题材库词表（genre 维度注入 {genre_vocab}；其他维度模板无此占位符不受影响）
        genre_vocab = await _genre_vocab_names()

        # ── 阶段二：分维度归并（勾选集；completed 跳过＝断点续拆）──
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
            if stopper.event.is_set():
                raise _Stopped(stopper.reason)
            dstate = dims.get(dim, {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""})
            sys_m, usr_m = load_layers(f"deconstruct_{dim}")
            pairs = [
                (no, line)
                for no, card in sorted(cards["entries"].items(), key=lambda kv: int(kv[0] or 0))
                if (line := _card_frag(no, card, dim))
            ]
            batches = _pack_pairs(pairs, _dim_in_cap(dim, merge_in_cap))
            dstate.update({"state": "running", "seg_done": 0, "seg_total": len(batches), "error": "",
                           "started_at": _now().isoformat()})
            dims[dim] = dstate
            await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))

            done_l1 = await _units_done(task_id, "l1", dim)

            async def _merge_batch(batch: list[tuple[str, str]]) -> list[str]:
                """单批归并 → [partial JSON]。

                截断/超长拆半**递归**（信号量外递归——信号量不可重入，递归内再进
                会死锁，pytest-timeout 实锤）；内容审核隔离为空列表（维度降级注记）；
                断点：同输入批次的已完成产物直接复用。
                """
                bkey = _input_hash("l1", dim, sys_m, "\n".join(line for _, line in batch))
                if bkey in done_l1:
                    dstate["seg_done"] += 1
                    return [done_l1[bkey]]
                started = time.monotonic()
                usage: dict = {}
                info: dict = {}
                try:
                    async with _sem:
                        await _check_cancel(task_id)
                        if stopper.event.is_set():
                            raise _Stopped(stopper.reason)
                        # 空维度（该维碎片全空）＝_pack_pairs 的 [[]] 占位批：存量口径照样
                        # 调用一次（模板自返空产物），seg 账同样走一遍
                        ch_from = batch[0][0] if batch else "1"
                        ch_to = batch[-1][0] if batch else "1"
                        state["activity"] = {
                            "label": f"正在归并 {names[dim]}（已完成 {dstate['seg_done']}/{dstate['seg_total']} 批）",
                            "at": _now().isoformat(),
                        }
                        await _unit_running(task_id, "l1", dim, bkey)
                        data = await _call_with_retry(
                            client, model, (sys_m, usr_m),
                            {
                                "book_name": task.book_name, "genre_or_unknown": "unknown",
                                "genre_vocab": genre_vocab,
                                "full_synopsis": full_synopsis[:_SYNOPSIS_CAP],
                                "seg_range": f"第{ch_from}-{ch_to}章",
                                "excerpts": "\n".join(line for _, line in batch),
                            },
                            f"deconstruct_{dim}",
                            max_tokens=merge_out_tokens, stopper=stopper, breaker=breaker,
                            usage=usage, info=info,
                        )
                except policy.UnitError as e:
                    await _unit_upsert(task_id, "l1", dim, bkey, status="failed",
                                       attempts=int(info.get("attempts", 1)),
                                       error_kind=e.kind, error_msg=e.message[:300],
                                       duration_ms=int((time.monotonic() - started) * 1000),
                                       input_hash=bkey)
                    if e.kind == policy.KIND_TRUNCATED and len(batch) > 1:
                        # 输出超预算/输入超上下文：拆半重试（MUST NOT 同尺寸原样重发）
                        mid = len(batch) // 2
                        left = await _merge_batch(batch[:mid])
                        right = await _merge_batch(batch[mid:])
                        return [*left, *right]
                    if e.kind == policy.KIND_CONTENT_FILTER:
                        return []  # 内容审核：隔离该批，维度降级注记，其余批继续
                    raise
                stopper.touch()
                out = json.dumps(data, ensure_ascii=False)
                await _unit_upsert(task_id, "l1", dim, bkey, status="done",
                                   attempts=int(info.get("attempts", 1)),
                                   duration_ms=int((time.monotonic() - started) * 1000),
                                   tokens_in=int(usage.get("tokens_in", 0) or 0),
                                   tokens_out=int(usage.get("tokens_out", 0) or 0),
                                   output_json=out, input_hash=bkey)
                dstate["seg_done"] += 1
                dims[dim] = dstate
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
                return [out]

            batch_out = await _run_units([_merge_batch(b) for b in batches])
            partials: list[str] = []
            for outs in batch_out:
                partials.extend(outs)
            skipped = sum(1 for outs in batch_out if not outs)
            reduce_degraded = (
                f"{skipped}/{len(batches)} 批内容被模型安全审核拒绝，该范围未纳入" if skipped else ""
            )

            # 树收敛：多批产物反复合并直到单份（无头尾截断＝任意长度零丢失；串行——树形依赖）
            if len(partials) > 1:
                sys_r, usr_r = load_layers("deconstruct_reduce")
                saved = (await _units_done(task_id, "reduce_state", dim)).get("partials")
                if saved:  # 断点：从轮间检查点继续（轮内重做有界）
                    try:
                        partials = json.loads(saved)
                    except ValueError:
                        pass

                async def _merge_group(group: list[str]) -> str:
                    """reduce 组合并（含截断拆半递归；信号量外递归防重入死锁）。"""
                    if len(group) == 1:
                        return group[0]
                    started = time.monotonic()
                    usage: dict = {}
                    info: dict = {}
                    gkey = _input_hash("reduce", dim, sys_r, *(_input_hash(g) for g in group))
                    try:
                        async with _sem:
                            await _check_cancel(task_id)
                            if stopper.event.is_set():
                                raise _Stopped(stopper.reason)
                            state["activity"] = {"label": f"正在收敛 {names[dim]}", "at": _now().isoformat()}
                            await _unit_running(task_id, "reduce", dim, gkey)
                            merged = await _call_with_retry(
                                client, model, (sys_r, usr_r),
                                {"dim_name": names[dim], "dim_key": dim,
                                 "partials": "\n\n".join(group)},
                                f"deconstruct_{dim}_reduce",
                                max_tokens=merge_out_tokens, stopper=stopper, breaker=breaker,
                                usage=usage, info=info,
                            )
                    except policy.UnitError as e:
                        await _unit_upsert(task_id, "reduce", dim, gkey, status="failed",
                                           attempts=int(info.get("attempts", 1)),
                                           error_kind=e.kind, error_msg=e.message[:300],
                                           duration_ms=int((time.monotonic() - started) * 1000))
                        if e.kind == policy.KIND_TRUNCATED and len(group) > 2:
                            mid = len(group) // 2
                            left = await _merge_group(group[:mid])
                            right = await _merge_group(group[mid:])
                            return await _merge_group([left, right])
                        raise
                    stopper.touch()
                    out = json.dumps(merged, ensure_ascii=False)
                    await _unit_upsert(task_id, "reduce", dim, gkey, status="done",
                                       attempts=int(info.get("attempts", 1)),
                                       duration_ms=int((time.monotonic() - started) * 1000),
                                       tokens_in=int(usage.get("tokens_in", 0) or 0),
                                       tokens_out=int(usage.get("tokens_out", 0) or 0),
                                       output_json=out)
                    dstate["seg_done"] += 1
                    dims[dim] = dstate
                    await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
                    return out

                try:
                    while len(partials) > 1:
                        await _check_cancel(task_id)
                        if stopper.event.is_set():
                            raise _Stopped(stopper.reason)
                        groups = _pack_units(partials, max(MERGE_INPUT_CAP, merge_in_cap))
                        if len(groups) >= len(partials):
                            # 每份都超单组预算：两两配对保底收敛
                            groups = [partials[i : i + 2] for i in range(0, len(partials), 2)]
                        nxt: list[str] = []
                        dstate["seg_total"] += len(groups)
                        for group in groups:
                            nxt.append(await _merge_group(group))
                        partials = nxt
                        # 轮间检查点：续拆从本轮产物继续，不整维重跑
                        await _unit_upsert(task_id, "reduce_state", dim, "partials",
                                           status="done", output_json=json.dumps(partials, ensure_ascii=False))
                except _Cancelled:
                    raise
                except _Stopped:
                    raise
                except policy.UnitError as e:  # noqa: BLE001 — 收敛被拦（13路实测：reduce 输入脱敏后仍 1301）
                    reduce_degraded = (
                        f"reduce 收敛被模型拒绝（{policy.KIND_LABELS.get(e.kind, e.kind)}：{str(e)[:60]}），"
                        f"保留 {len(partials)} 段归并稿"
                    )
                    _log.warning("REDUCE-DEGRADE %s: %s", dim, reduce_degraded)
                except Exception as e:  # noqa: BLE001 — 非模型异常同降级（图谱病着也要出）
                    reduce_degraded = f"reduce 收敛失败（{str(e)[:60]}），保留 {len(partials)} 段归并稿"
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
            if stopper.event.is_set():
                raise _Stopped(stopper.reason)
            try:
                from deconstruct.graph import assemble, place_merge_input

                # 阶段 3.0：presence 补写——卡上 characters 全名 ⊄ 在场者时，
                # 轻量调用逐人定位（只补名单、where 抄本章闭集），合并回卡片；达标章零调用
                backfill_failed = await _backfill_presence(
                    task_id, task, chapters, cards, dims, state, client, model,
                    graph_on=_graph_export_on(), caps=state.get("caps_graph", True), sem=_sem,
                    stopper=stopper, breaker=breaker,
                )
                frags = place_merge_input(cards["entries"])
                place_merge = None
                truncated = False
                place_cached = (await _units_done(task_id, "place", "")).get("book")
                if frags:
                    frag_text = "\n".join(frags)
                    if len(frag_text) > merge_in_cap:
                        frag_text = frag_text[:merge_in_cap]
                        truncated = True
                    state["graph_phase"] = {"step": "place_merge"}
                    state["activity"] = {"label": "正在归并全书中地点", "at": _now().isoformat()}
                    await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
                    if place_cached:  # 断点：全书地点归并只做一次
                        place_merge = json.loads(place_cached)
                    else:
                        sys_pl, usr_pl = load_layers("deconstruct_place")
                        started = time.monotonic()
                        usage: dict = {}
                        info: dict = {}
                        await _unit_running(task_id, "place", "", "book")
                        place_merge = await _call_with_retry(
                            client, model, (sys_pl, usr_pl),
                            {"book_name": task.book_name, "genre_or_unknown": "unknown",
                             "full_synopsis": full_synopsis[:_SYNOPSIS_CAP],
                             "seg_range": f"第1-{task.chapter_count}章" if task.chapter_count else "全本",
                             "excerpts": frag_text},
                            "deconstruct_place",
                            max_tokens=merge_out_tokens, stopper=stopper, breaker=breaker,
                            usage=usage, info=info,
                        )
                        stopper.touch()
                        await _unit_upsert(task_id, "place", "", "book", status="done",
                                           attempts=int(info.get("attempts", 1)),
                                           duration_ms=int((time.monotonic() - started) * 1000),
                                           tokens_in=int(usage.get("tokens_in", 0) or 0),
                                           tokens_out=int(usage.get("tokens_out", 0) or 0),
                                           output_json=json.dumps(place_merge, ensure_ascii=False))
                await _check_cancel(task_id)  # 归并调用是新段边界：取消在此生效（评审 P3）
                if stopper.event.is_set():
                    raise _Stopped(stopper.reason)
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
            except _Stopped:
                raise
            except Exception as e:  # noqa: BLE001 — 图谱不拖累任务：错误留痕，导出端 400
                state["graph_error"] = str(e)[:300]
                state.pop("graph_phase", None)
                state.pop("activity", None)
                await _patch(task_id, dims_json=_state_json(state, cards=cards, dims=dims))
    except (_Cancelled, _Stopped) as s:
        reason = getattr(s, "reason", "") or "cancelled"
        if reason == "cancelled":
            await _patch(task_id, finished_at=_now())
            return
        if reason in ("stalled", "wall"):
            await _fail(task_id, error={
                "message": ("模型长时间无响应，任务已自动暂停，可从断点续拆"
                            if reason == "stalled" else
                            "任务超出时长上限，已自动暂停，可从断点续拆"),
                "kind": "stalled",
            })
            return
        await _fail(task_id, error={
            "message": "模型服务连续失败，任务已自动暂停，可稍后续拆或更换模型",
            "kind": "provider_unavailable",
        })
        return
    except policy.UnitError as e:
        await _fail(task_id, error={
            "message": f"{policy.KIND_LABELS.get(e.kind, '模型调用失败')}：{str(e.message)[:200]}",
            "kind": _task_kind(e.kind),
        })
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
    finally:
        await _sweep_running(task_id)  # 调度落账收尾（c-deconstruct-monitor）：running 残留置 failed，幂等
        await watch.stop()

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
