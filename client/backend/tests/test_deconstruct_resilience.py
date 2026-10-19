"""拆书韧性测试（c-deconstruct-resilience）：失败策略、熔断、看门狗、取消、单元账。

模型与模板全部打桩（不依赖 sibling 提示词仓，CI 可跑）。故障注入矩阵：
- 瞬时（RuntimeError/超时形态）→ 3 发退避后放行/熔断；
- 确定性（401/400/404/405、contentFilter、JSON 截断）→ 不重试，按策略处置；
- 截断 → 拆半自愈，MUST NOT 同尺寸原样重发；
- 取消/看门狗 → 在途调用竞速掐断，任务有界收场；
- 单元账 → L1 批级断点续拆不重跑，调用账可聚合。
"""

import asyncio
import json
import os
import tempfile
import time

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_der.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_der_")
os.environ["DECONSTRUCT_DISPATCHER_OFF"] = "1"
os.environ["DECONSTRUCT_CONCURRENCY"] = "1"  # 串行口径保调用序列钉确定性
os.environ["DECONSTRUCT_BACKOFF_SCALE"] = "0"

from db import Base, async_session, engine  # noqa: E402
from models.deconstruct import DeconstructJob, DeconstructUnit  # noqa: E402

_UID = "der-user"

_SRC = (
    "第1章 初见\n林晚在渡口救人。\n第2章 重逢\n阿蓟归来报恩。\n"
    "第3章 远行\n二人离乡入京。\n第4章 风波\n京城水 deeply 深。\n"
)


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module", autouse=True)
def _db():
    _run(_ensure_tables())
    yield


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _mk_job(task_id: str, *, selected: list[str], chapters: int = 4, status: str = "queued",
            dims_json: str = "{}") -> None:
    async def _go():
        async with async_session() as s:
            from deconstruct.service import next_queue_seq, source_path_of

            path = source_path_of(task_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("".join(
                    f"第{i + 1}章 标题{i + 1}\n内容{i + 1}。\n" for i in range(chapters)
                ) if chapters != 4 else _SRC)
            s.add(DeconstructJob(
                id=task_id, user_id=_UID, status=status,
                queue_seq=await next_queue_seq(s),
                book_name="测试书", source_path=path, encoding="utf-8",
                api_config_id="cfg-1", ai_model="m-1",
                chapter_count=chapters,
                selected_dims_json=json.dumps(selected),
                dims_json=dims_json,
            ))
            await s.commit()
    _run(_go())


def _load(task_id: str) -> DeconstructJob:
    async def _go():
        async with async_session() as s:
            return await s.get(DeconstructJob, task_id)
    return _run(_go())


def _units(task_id: str) -> list[DeconstructUnit]:
    async def _go():
        from sqlalchemy import select

        async with async_session() as s:
            rows = (await s.execute(
                select(DeconstructUnit).where(DeconstructUnit.task_id == task_id)
            )).scalars().all()
            return list(rows)
    return _run(_go())


class FakeClient:
    """按 operation 派发脚本化回复；记录调用序列与 max_tokens。"""

    def __init__(self, handlers=None, default=None):
        self.calls: list[str] = []
        self.counts: dict[str, int] = {}
        self.last_by_op: dict[str, str] = {}
        self.max_tokens_by_op: dict[str, int] = {}
        self.handlers = handlers or {}
        self.default = default or (lambda *a: "{}")

    async def chat(self, **kw):
        op = kw.get("operation", "")
        self.calls.append(op)
        self.last_by_op[op] = kw["messages"][0]["content"]
        self.max_tokens_by_op[op] = kw.get("max_tokens", 0)
        n = self.counts.get(op, 0)
        self.counts[op] = n + 1
        result = self.handlers.get(op, self.default)(kw, n)
        if asyncio.iscoroutine(result):
            result = await result
        return result


def _stub(monkeypatch, client):
    from deconstruct import pipeline, service

    monkeypatch.setattr(pipeline, "CONCURRENCY", 1)

    def load_layers(name):
        if name == "deconstruct_card":
            return "sys", "u {book_name}|{chapter_no}|{chapter_title}|{chapter_text}"
        if name == "deconstruct_presence":
            return "sys", "u {book_name}|{chapter_no}|{chapter_title}|{missing_names}|{places_known}|{chapter_text}"
        if name == "deconstruct_reduce":
            return "sys", "u {dim_name}|{partials}"
        return "sys", "u {book_name}|{genre_or_unknown}|{full_synopsis}|{seg_range}|{excerpts}"

    monkeypatch.setattr(pipeline, "load_layers", load_layers)

    async def fake_resolve(user_id, api_config_id, model, thinking="inherit"):
        return client, "m-1"

    monkeypatch.setattr(service, "resolve_client", fake_resolve)


def _card_handler(kw, n):
    content = kw["messages"][0]["content"]
    no = content.split("|")[1]
    return json.dumps({
        "summary": f"梗概{no}",
        "world": [{"name": f"地{no}", "note": "n"}],
        "characters": [{"name": f"人{no}", "role": "主角", "traits": "t", "alias": ""}],
        "intro": [], "genre": [], "relations": [], "mainplot": [],
        "structure": [], "style": [], "techniques": [], "foreshadow": [],
    })


def _seen_handler(op_name):
    def h(kw, n):
        import re

        content = kw["messages"][0]["content"]
        seen = sorted({int(m) for m in re.findall(r"【第(\d+)章】", content)})
        return json.dumps({"seen": seen or [0], "src": op_name})
    return h


def _reduce_merge(kw, n):
    import re

    content = kw["messages"][0]["content"]
    seen: set[int] = set()
    for m in re.finditer(r'\{"seen": \[([0-9, ]*)\]', content):
        seen |= {int(x) for x in m.group(1).split(",") if x.strip()}
    return json.dumps({"seen": sorted(seen), "src": "reduce"})


class _StatusError(Exception):
    def __init__(self, status: int, message: str):
        self.status_code = status
        super().__init__(message)


# ── 失败分类 ────────────────────────────────────────────────────────────────

def test_classify_matrix():
    from deconstruct import policy

    assert policy.classify(RuntimeError("boom")) == policy.KIND_UNKNOWN
    assert policy.classify(_StatusError(401, "unauthorized")) == policy.KIND_AUTH
    assert policy.classify(_StatusError(403, "forbidden")) == policy.KIND_AUTH
    assert policy.classify(_StatusError(400, "bad request")) == policy.KIND_CONFIG
    assert policy.classify(_StatusError(404, "nope")) == policy.KIND_ROUTE
    assert policy.classify(_StatusError(405, "nope")) == policy.KIND_ROUTE
    assert policy.classify(_StatusError(429, "rate limited")) == policy.KIND_RATE_LIMIT
    assert policy.classify(_StatusError(503, "down")) == policy.KIND_UPSTREAM
    assert policy.classify(_StatusError(400, "Error code: 400 - {'contentFilter': []}")) == policy.KIND_CONTENT_FILTER
    assert policy.classify(RuntimeError("code 1301 被拒")) == policy.KIND_CONTENT_FILTER
    assert policy.classify(ValueError("模型输出 JSON 不完整")) == policy.KIND_TRUNCATED
    assert policy.classify(ValueError("模型输出不是 JSON")) == policy.KIND_INVALID_OUTPUT
    # 瞬时面：unknown/invalid_output 也重试（存量口径），截断不重试
    for kind in (policy.KIND_UNKNOWN, policy.KIND_INVALID_OUTPUT,
                 policy.KIND_TIMEOUT, policy.KIND_RATE_LIMIT, policy.KIND_UPSTREAM):
        assert kind in policy.TRANSIENT_KINDS, kind
    for kind in (policy.KIND_TRUNCATED, policy.KIND_CONTENT_FILTER,
                 policy.KIND_AUTH, policy.KIND_CONFIG, policy.KIND_ROUTE):
        assert kind not in policy.TRANSIENT_KINDS, kind


def test_backoff_scale_env_zero_and_retry_after(monkeypatch):
    from deconstruct import policy

    monkeypatch.setenv("DECONSTRUCT_BACKOFF_SCALE", "0")
    assert policy.backoff_seconds(3) == 0.0
    monkeypatch.setenv("DECONSTRUCT_BACKOFF_SCALE", "1")
    monkeypatch.setattr(policy.random, "uniform", lambda a, b: b)
    assert 0 < policy.backoff_seconds(1) <= policy.BACKOFF_CAP
    assert policy.backoff_seconds(1, retry_after=7.5) == 7.5
    monkeypatch.setenv("DECONSTRUCT_BACKOFF_SCALE", "0")
    assert policy.backoff_seconds(1, retry_after=7.5) == 0.0


def test_call_with_retry_transient_3_attempts_and_fatal_single(monkeypatch):
    from deconstruct import pipeline, policy

    class Flaky:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kw):
            self.calls += 1
            raise RuntimeError("网络抖动")

    flaky = Flaky()
    try:
        _run(pipeline._call_with_retry(flaky, "m", ("s", "u"), {}, "op"))
        raise AssertionError("持续失败应当上抛 UnitError")
    except policy.UnitError as e:
        assert e.kind == policy.KIND_UNKNOWN
    assert flaky.calls == policy.RETRY_MAX_ATTEMPTS

    class Fatal:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kw):
            self.calls += 1
            raise _StatusError(401, "bad key")

    fatal = Fatal()
    try:
        _run(pipeline._call_with_retry(fatal, "m", ("s", "u"), {}, "op"))
        raise AssertionError("应当上抛 UnitError")
    except policy.UnitError as e:
        assert e.kind == policy.KIND_AUTH
    assert fatal.calls == 1  # 鉴权失败只发一次


def test_call_with_retry_truncated_no_identical_retry():
    """截断（JSON 不完整）＝预算型失败：一次定生死，不做同输入重试。"""
    from deconstruct import pipeline, policy

    class Trunc:
        def __init__(self):
            self.calls = 0

        async def chat(self, **kw):
            self.calls += 1
            return '{"a": 1'  # 永远截断

    t = Trunc()
    try:
        _run(pipeline._call_with_retry(t, "m", ("s", "u"), {}, "op"))
        raise AssertionError("应当上抛 UnitError")
    except policy.UnitError as e:
        assert e.kind == policy.KIND_TRUNCATED
    assert t.calls == 1


# ── 熔断 / 看门狗 / 取消 ────────────────────────────────────────────────────

def test_breaker_trips_provider_unavailable(monkeypatch):
    """并发下连续单元穷尽 → 熔断：stopper 置位、全部单元以 _Stopped 收场、任务
    provider_unavailable、不再有新调用。串行模式首个穷尽单元直接失败任务
    （存量语义），熔断的增益在并发扇出场景。"""
    from deconstruct import pipeline

    client = FakeClient({"deconstruct_card": lambda kw, n: (_ for _ in ()).throw(RuntimeError("挂"))})

    def load_layers(name):
        if name == "deconstruct_card":
            return "sys", "u {book_name}|{chapter_no}|{chapter_title}|{chapter_text}"
        return "sys", "u {book_name}|{genre_or_unknown}|{full_synopsis}|{seg_range}|{excerpts}"

    from deconstruct import pipeline as pl
    from deconstruct import service as svc

    monkeypatch.setattr(pl, "CONCURRENCY", 4)
    monkeypatch.setattr(pl, "load_layers", load_layers)

    async def fake_resolve(user_id, api_config_id, model, thinking="inherit"):
        return client, "m-1"

    monkeypatch.setattr(svc, "resolve_client", fake_resolve)
    _mk_job("der-break", selected=["world"], chapters=4)

    _run(pipeline.run_task("der-break"))
    t = _load("der-break")
    assert t.status == "failed"
    err = json.loads(t.error_json)
    assert err["kind"] == "provider_unavailable"
    # 4 并发单元 × 每单元最多 3 发；熔断后其余单元不再发起（有界）
    assert 3 <= client.counts["deconstruct_card"] <= 12


def test_watchdog_stall_fails_task_and_frees_queue(monkeypatch):
    from deconstruct import pipeline

    _mk_job("der-stall", selected=["world"], chapters=2)
    client = FakeClient({"deconstruct_card": _card_handler})

    async def hang(kw, n):
        if n == 0 and kw["operation"] == "deconstruct_card":
            await asyncio.sleep(30)  # 模型挂起不回
        return _card_handler(kw, n)

    client.handlers["deconstruct_card"] = hang
    _stub(monkeypatch, client)
    monkeypatch.setattr(pipeline, "_WATCH_INTERVAL", 0.05)
    monkeypatch.setattr(pipeline, "_STALL_CARD_SEC", 0.3)

    started = time.monotonic()
    _run(pipeline.run_task("der-stall"))
    wall = time.monotonic() - started
    t = _load("der-stall")
    assert t.status == "failed"
    assert json.loads(t.error_json)["kind"] == "stalled"
    assert wall < 10, f"看门狗未在有限时间内收场（{wall:.1f}s）"


def test_cancel_races_in_flight_call(monkeypatch):
    """取消贯穿在途调用：DB 置 cancelled 后轮询置停、竞速掐断挂起请求。"""
    from deconstruct import pipeline

    _mk_job("der-cancel", selected=["world"], chapters=2)
    client = FakeClient({"deconstruct_card": _card_handler})

    async def slow_first(kw, n):
        if n == 0 and kw["operation"] == "deconstruct_card":
            async def _flip():
                async with async_session() as s:
                    t = await s.get(DeconstructJob, "der-cancel")
                    t.status = "cancelled"
                    await s.commit()
            await _flip()
            await asyncio.sleep(30)  # 挂起：取消必须掐断它而不是等它
        return _card_handler(kw, n)

    client.handlers["deconstruct_card"] = slow_first
    _stub(monkeypatch, client)
    monkeypatch.setattr(pipeline, "_WATCH_INTERVAL", 0.05)

    started = time.monotonic()
    _run(pipeline.run_task("der-cancel"))
    wall = time.monotonic() - started
    t = _load("der-cancel")
    assert t.status == "cancelled"
    assert wall < 10, f"取消未在有限时间内生效（{wall:.1f}s）"
    assert client.counts["deconstruct_card"] == 1  # 取消后不再发起新调用


# ── 单元隔离与截断自愈 ──────────────────────────────────────────────────────

def test_content_filter_chapter_isolated_task_completes(monkeypatch):
    """单章内容审核：隔离＋告警＋单元账 failed，其余章照常、任务完成。"""
    from deconstruct import pipeline, policy

    _stub(monkeypatch, None)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world")})

    def cf_on_ch2(kw, n):
        no = kw["messages"][0]["content"].split("|")[1]
        if no == "2":
            raise RuntimeError("Error code: 400 - {'contentFilter': [{'level': 1}]}")
        return _card_handler(kw, n)

    client.handlers["deconstruct_card"] = cf_on_ch2
    _stub(monkeypatch, client)
    _mk_job("der-cf", selected=["world"], chapters=4)

    _run(pipeline.run_task("der-cf"))
    t = _load("der-cf")
    assert t.status == "completed", t.error_json
    state = json.loads(t.dims_json)
    entries = set(state["cards"]["entries"])
    assert entries == {"1", "3", "4"}  # 第 2 章被隔离
    assert any("第2章" in w for w in state.get("warnings", []))
    failed_units = [u for u in _units("der-cf") if u.stage == "card" and u.status == "failed"]
    assert len(failed_units) == 1 and failed_units[0].error_kind == policy.KIND_CONTENT_FILTER
    # 世界归并只见 3 章碎片
    prods = json.loads(t.products_json)
    assert prods["world"]["data"]["seen"] == [1, 3, 4]


def test_l1_truncation_bisects_not_retries(monkeypatch):
    """L1 截断：拆半重试，4 章批不再以同尺寸重发；终稿零丢失。"""
    from deconstruct import pipeline

    _stub(monkeypatch, None)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world_reduce": _reduce_merge})

    def world_maybe_truncated(kw, n):
        import re

        n_ch = len(re.findall(r"【第(\d+)章】", kw["messages"][0]["content"]))
        if n_ch > 2:
            raise ValueError("模型输出 JSON 不完整")
        return _seen_handler("world")(kw, n)

    client.handlers["deconstruct_world"] = world_maybe_truncated
    _stub(monkeypatch, client)
    _mk_job("der-bisect", selected=["world"], chapters=4)  # 默认 30000：4 章一批

    _run(pipeline.run_task("der-bisect"))
    t = _load("der-bisect")
    assert t.status == "completed", t.error_json
    prods = json.loads(t.products_json)
    assert prods["world"]["data"]["seen"] == [1, 2, 3, 4]
    # 4 章批 1 发（截断）＋ 2 章批 2 发＋ reduce 1 发＝4；4 章批不得重发第二次
    assert client.counts["deconstruct_world"] == 3
    assert client.counts["deconstruct_world_reduce"] == 1


# ── 能力预算（1M 上下文解锁）────────────────────────────────────────────────

def test_caps_env_unlocks_merge_budget(monkeypatch):
    """DECONSTRUCT_CAPS 显式覆盖：归并输出预算放大（单遍归并的预算前提）。"""
    from deconstruct import pipeline

    monkeypatch.setenv("DECONSTRUCT_CAPS", json.dumps(
        {"context_window": 1000000, "max_output_tokens": 65536}))
    _stub(monkeypatch, None)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world")})
    _stub(monkeypatch, client)
    _mk_job("der-caps", selected=["world"], chapters=2)

    _run(pipeline.run_task("der-caps"))
    t = _load("der-caps")
    assert t.status == "completed", t.error_json
    assert client.max_tokens_by_op["deconstruct_world"] == 16384  # min(65536*0.75, 16384)
    state = json.loads(t.dims_json)
    assert state["caps_note"]["context_window"] == 1000000
    assert state["caps_note"]["source"] == "env"


def test_caps_conservative_default_unchanged(monkeypatch,):
    """未知模型＝保守口径：归并输出仍 8192（行为零漂移）。"""
    from deconstruct import pipeline

    monkeypatch.delenv("DECONSTRUCT_CAPS", raising=False)
    _stub(monkeypatch, None)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world")})
    _stub(monkeypatch, client)
    _mk_job("der-caps2", selected=["world"], chapters=2)

    _run(pipeline.run_task("der-caps2"))
    assert _load("der-caps2").status == "completed"
    assert client.max_tokens_by_op["deconstruct_world"] == 8192


def test_token_estimate_and_oversize():
    from deconstruct import capabilities as caps_mod
    from deconstruct import policy

    assert caps_mod.estimate_tokens("") == 0
    cjk = caps_mod.estimate_tokens("一二三四五")
    ascii_t = caps_mod.estimate_tokens("abcde")
    assert cjk > ascii_t  # CJK 记 1/字、ASCII 记 0.3/字
    assert caps_mod.caps_for(vendor="", model="m-1").source == "conservative"
    known = caps_mod.caps_for(vendor="glm", model="glm-5.3-flash")
    assert known.source == "known" and known.context_window >= 131072

    class _E(Exception):
        status_code = 400

    assert caps_mod.oversize_reject(_E("maximum context length exceeded"))
    assert not caps_mod.oversize_reject(_StatusError(401, "bad key"))
    # oversize 的 400 在管线里被归为 truncated（拆半自愈），不是 config
    e = _StatusError(400, "This model's maximum context length is 8192 tokens")
    assert policy.classify(e) == policy.KIND_CONFIG  # 原生分类


# ── 单元账：断点续拆＋调用账 ────────────────────────────────────────────────

def test_l1_unit_resume_skips_done_batches(monkeypatch):
    """L1 批级断点：批 2 截断失败 → 任务失败；续拆只补批 2/3/4＋reduce，批 1 复用。"""
    from deconstruct import pipeline

    _stub(monkeypatch, None)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world_reduce": _reduce_merge})
    monkeypatch.setattr(pipeline, "CARD_BATCH_CHARS", 30)  # 每碎片独占一批 → 4 批

    def world_truncate_batch2(kw, n):
        import re

        chs = re.findall(r"【第(\d+)章】", kw["messages"][0]["content"])
        if chs == ["2"] and n == 1:  # 批 2 首发（n=1）截断：一次定生死不重试；续拆走 n=2 正常
            raise ValueError("模型输出 JSON 不完整")
        return _seen_handler("world")(kw, n)

    client.handlers["deconstruct_world"] = world_truncate_batch2
    _stub(monkeypatch, client)
    _mk_job("der-resume", selected=["world"], chapters=4)

    _run(pipeline.run_task("der-resume"))
    t = _load("der-resume")
    assert t.status == "failed"
    assert json.loads(t.error_json)["kind"] == "truncated"
    first_run_world = client.counts["deconstruct_world"]
    assert first_run_world == 2  # 批 1 成功＋批 2 截断（1 发，不重试）

    # 续拆：批 1 从单元账复用（不重复调用）
    _run(pipeline.run_task("der-resume"))
    t2 = _load("der-resume")
    assert t2.status == "completed", t2.error_json
    second_run_world = client.counts["deconstruct_world"] - first_run_world
    assert second_run_world == 3  # 只补批 2/3/4
    prods = json.loads(t2.products_json)
    assert prods["world"]["data"]["seen"] == [1, 2, 3, 4]
    l1_done = [u for u in _units("der-resume") if u.stage == "l1" and u.status == "done"]
    assert len(l1_done) == 4
    assert any(u.stage == "reduce_state" for u in _units("der-resume"))
    # 检查点非调用（评审 P3）：调用账不得出现 reduce_state 幽灵桶
    from deconstruct import service as dec_service

    stats = _run(dec_service.task_stats("der-resume"))
    assert "reduce_state" not in stats
    assert stats["reduce"]["calls"] >= 1 and stats["l1"]["calls"] == 4


def test_task_stats_aggregation(monkeypatch):
    """调用账聚合：按阶段计 calls/attempts/tokens，失败行归 by_kind。"""
    from deconstruct import pipeline, service

    _stub(monkeypatch, None)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world")})
    _stub(monkeypatch, client)
    _mk_job("der-stats", selected=["world"], chapters=2)

    _run(pipeline.run_task("der-stats"))
    stats = _run(service.task_stats("der-stats"))
    assert stats["card"]["calls"] == 2 and stats["card"]["failures"] == 0
    assert stats["l1"]["calls"] == 1 and stats["l1"]["attempts"] >= 1
    # usage 桩不回 token（FakeClient 忽略 usage dict）→ 0 但字段在
    assert "tokens_in" in stats["card"]


def test_resume_with_model_change_updates_history(monkeypatch):
    """换模型续拆：resolve 校验→更新任务→model_history 追加。"""
    from deconstruct import service

    _mk_job("der-mc", selected=["world"], chapters=1, status="failed")
    history_json = json.dumps([{
        "api_config_id": "cfg-1", "ai_model": "m-1",
        "at": "2026-10-17T00:00:00",
    }], ensure_ascii=False)

    async def _seed():
        async with async_session() as s:
            t = await s.get(DeconstructJob, "der-mc")
            t.model_history_json = history_json
            await s.commit()
    _run(_seed())

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from deconstruct.router import router

    app = FastAPI()
    app.include_router(router)
    called_with: dict = {}

    async def fake_resolve(user_id, api_config_id, model, thinking="inherit"):
        called_with.update(config=api_config_id, model=model)
        return object(), model

    monkeypatch.setattr(service, "resolve_client", fake_resolve)
    monkeypatch.setattr("deconstruct.dispatcher.start_dispatcher", lambda: None)

    # 鉴权覆盖：router 依赖 get_current_user —— 复用 test_deconstruct_api 的做法太重，
    # 这里直接 dependency_overrides
    from auth_local.middleware import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"id": _UID}
    from db import get_db

    async def _override_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    try:
        with TestClient(app) as tc:
            r = tc.post("/api/deconstruct/tasks/der-mc/resume",
                        json={"api_config_id": "cfg-9", "ai_model": "m-9"})
            assert r.status_code == 200, r.text
            assert called_with == {"config": "cfg-9", "model": "m-9"}
            t = _load("der-mc")
            assert t.api_config_id == "cfg-9" and t.ai_model == "m-9"
            history = json.loads(t.model_history_json)
            assert len(history) == 2 and history[-1]["ai_model"] == "m-9"
    finally:
        # 收尾还原终态：resume 把任务置回 queued，若留着不管，同进程后续的
        # dispatcher 集成测试会先接单这个泄漏任务（实测踩坑：串行 worker 被占死）
        async def _restore():
            async with async_session() as s:
                row = await s.get(DeconstructJob, "der-mc")
                if row is not None and row.status == "queued":
                    row.status = "failed"
                    await s.commit()
        _run(_restore())


# ── 时间口径 ────────────────────────────────────────────────────────────────

def test_activity_age_utc_consistent(monkeypatch):
    """UTC+8 挂钟下 activity.age_seconds 仍是真实 20 秒（时区偏移根治钉）。"""
    import time as time_mod
    from datetime import UTC, datetime, timedelta

    from deconstruct import service

    monkeypatch.setenv("TZ", "Asia/Shanghai")
    if hasattr(time_mod, "tzset"):
        time_mod.tzset()
    try:
        now_utc = datetime.now(UTC).replace(tzinfo=None)
        task = DeconstructJob(id="der-tz", user_id=_UID, status="running")
        task.dims_json = json.dumps({
            "activity": {"label": "正在拆解 第1章",
                         "at": (now_utc - timedelta(seconds=20)).isoformat(timespec="seconds")},
        })
        a = service._activity(task)
        assert a is not None
        assert 10 <= a["age_seconds"] <= 120
    finally:
        monkeypatch.delenv("TZ")
        if hasattr(time_mod, "tzset"):
            time_mod.tzset()


# ── 开书产物契约（设定页内容要求）───────────────────────────────────────────

def _apply_task(products: dict):
    from types import SimpleNamespace

    return SimpleNamespace(products_json=json.dumps(products, ensure_ascii=False))


def test_apply_cards_persona_fallback_from_background():
    """persona 全空（真机 13路 258 章实测 10/10 张）→ 背景/关键行动合成一句话速写。"""
    from deconstruct.apply import _cards

    task = _apply_task({"characters": {"data": {"characters": [
        {"name": "李耀", "role": "主角", "persona": "", "background": "末班车售票员，随身带着一张老路线图。",
         "plot": "在第3章发现班次异常。", "evidence_ch": "第1章"},
        {"name": "老吴", "role": "配角", "persona": "原文未明确", "background": "原文未明确",
         "plot": "替主角挡了一刀。", "evidence_ch": "第2章"},
    ]}}})
    cards = _cards(task)
    assert cards[0]["persona"], "背景非空时 persona 必须兜底合成"
    assert "售票员" in cards[0]["persona"]
    assert cards[1]["persona"], "背景缺失时从 plot 兜底"
    assert "挡了一刀" in cards[1]["persona"]


def test_apply_cards_role_normalize_compound():
    """复合 role（「核心反派」「反派→求助者」「主角（前期）」）→ 白名单五档，不错标配角。"""
    from deconstruct.apply import _cards

    task = _apply_task({"characters": {"data": {"characters": [
        {"name": "甲", "role": "核心反派", "background": "b"},
        {"name": "乙", "role": "反派→求助者", "background": "b"},
        {"name": "丙", "role": "主角（前期）", "background": "b"},
        {"name": "丁", "role": "神秘存在", "background": "b"},  # 全无关键词 → 兜底配角
    ]}}})
    roles = {c["name"]: c["role"] for c in _cards(task)}
    assert roles["甲"] == "反派"
    assert roles["乙"] == "反派"
    assert roles["丙"] == "主角"
    assert roles["丁"] == "配角"


# ── 拆卡合批（P1b：JSONL 一行一张卡；坏批回退逐章）──────────────────────────

def test_parse_batch_cards_jsonl_wrapped_and_garbage():
    from deconstruct.pipeline import _parse_batch_cards

    jsonl = '{"no": 1, "summary": "a"}\n{"no": 2, "summary": "b"}'
    out = _parse_batch_cards(jsonl, {"1", "2"})
    assert set(out) == {"1", "2"} and out["1"]["summary"] == "a" and "no" not in out["1"]
    wrapped = '{"cards": [{"no": 1, "summary": "a"}, {"no": 2, "summary": "b"}]}'
    assert set(_parse_batch_cards(wrapped, {"1", "2"})) == {"1", "2"}
    # 越权章号丢弃、行级缺章只回已有集合（调用方逐章补缺）
    assert set(_parse_batch_cards('{"no": 1, "summary": "a"}\n{"no": 9, "x": 1}', {"1", "2"})) == {"1"}
    assert _parse_batch_cards("这不是 JSON", {"1"}) is None
    assert _parse_batch_cards("", {"1"}) is None


def _stub_with_batch(monkeypatch, client):
    from deconstruct import pipeline, service

    monkeypatch.setattr(pipeline, "CONCURRENCY", 1)

    def load_layers(name):
        if name == "deconstruct_card":
            return "sys", "u {book_name}|{chapter_no}|{chapter_title}|{chapter_text}"
        if name == "deconstruct_card_batch":
            return "sys", "u {book_name}|{chapters_block}"
        if name == "deconstruct_reduce":
            return "sys", "u {dim_name}|{partials}"
        return "sys", "u {book_name}|{genre_or_unknown}|{full_synopsis}|{seg_range}|{excerpts}"

    monkeypatch.setattr(pipeline, "load_layers", load_layers)

    async def fake_resolve(user_id, api_config_id, model, thinking="inherit"):
        return client, "m-1"

    monkeypatch.setattr(service, "resolve_client", fake_resolve)


def test_card_batching_jsonl_calls_and_ledger(monkeypatch):
    """合批路径：2 章/批 → 4 章只发 2 次合批调用；逐章零调用；单元账按章落 done。"""
    import re

    from deconstruct import pipeline

    monkeypatch.setenv("DECONSTRUCT_CARD_BATCH", "2")
    client = FakeClient({"deconstruct_world": _seen_handler("world")})

    def batch_cards2(kw, n):
        content = kw["messages"][0]["content"]
        nos = re.findall(r"【第(\d+)章】", content)
        lines = []
        for no in nos:
            card = json.loads(_card_handler({"messages": [{"content": f"x|{no}|t|x"}]}, 0))
            card["no"] = int(no)
            lines.append(json.dumps(card, ensure_ascii=False))
        return "\n".join(lines)

    client.handlers["deconstruct_card_batch"] = batch_cards2
    _stub_with_batch(monkeypatch, client)
    _mk_job("der-batch", selected=["world"], chapters=4)

    _run(pipeline.run_task("der-batch"))
    t = _load("der-batch")
    assert t.status == "completed", t.error_json
    assert client.counts["deconstruct_card_batch"] == 2
    assert "deconstruct_card" not in client.counts  # 逐章零调用
    cards = json.loads(t.dims_json)["cards"]
    assert set(cards["entries"]) == {"1", "2", "3", "4"}
    done_cards = [u for u in _units("der-batch") if u.stage == "card" and u.status == "done"]
    assert len(done_cards) == 4
    assert any(u.stage == "card_batch" for u in _units("der-batch"))


def test_card_batch_bad_output_falls_back_per_chapter(monkeypatch):
    """合批坏输出 → 整批退回逐章（既有隔离口径），任务仍完成。"""
    from deconstruct import pipeline

    monkeypatch.setenv("DECONSTRUCT_CARD_BATCH", "2")
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world"),
                         "deconstruct_card_batch": lambda kw, n: "完全不是 JSON 的输出"})
    _stub_with_batch(monkeypatch, client)
    _mk_job("der-batch-fb", selected=["world"], chapters=4)

    _run(pipeline.run_task("der-batch-fb"))
    t = _load("der-batch-fb")
    assert t.status == "completed", t.error_json
    assert client.counts["deconstruct_card_batch"] == 2
    assert client.counts["deconstruct_card"] == 4  # 两批全退回逐章
    assert set(json.loads(t.dims_json)["cards"]["entries"]) == {"1", "2", "3", "4"}
    # 失败账：退回成功也保留批次失败痕迹（评审 P3）
    fb_rows = [u for u in _units("der-batch-fb") if u.stage == "card_batch" and u.status == "failed"]
    assert len(fb_rows) == 2 and all(u.error_kind == "invalid_output" for u in fb_rows)


def test_card_batch_off_forces_per_chapter(monkeypatch):
    """off 旗标强制逐章（回滚口径）；模板缺失（老包）同样回退。"""
    from deconstruct import pipeline

    monkeypatch.setenv("DECONSTRUCT_CARD_BATCH", "off")
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world")})
    _stub(monkeypatch, client)  # 该桩不含 card_batch 模板
    _mk_job("der-batch-off", selected=["world"], chapters=2)

    _run(pipeline.run_task("der-batch-off"))
    t = _load("der-batch-off")
    assert t.status == "completed"
    assert client.counts["deconstruct_card"] == 2
    assert "deconstruct_card_batch" not in client.counts


def test_card_batch_fatal_error_no_chapter_fallback(monkeypatch):
    """合批遇确定性致命（401/400/404）：立即终局，不退回逐章再打注定失败的请求（评审 P2）。"""
    from deconstruct import pipeline

    monkeypatch.setenv("DECONSTRUCT_CARD_BATCH", "2")
    client = FakeClient({"deconstruct_card_batch": lambda kw, n: (_ for _ in ()).throw(
        _StatusError(401, "bad key"))})
    _stub_with_batch(monkeypatch, client)
    _mk_job("der-batch-fatal", selected=["world"], chapters=4)

    _run(pipeline.run_task("der-batch-fatal"))
    t = _load("der-batch-fatal")
    assert t.status == "failed"
    assert json.loads(t.error_json)["kind"] == "auth"
    assert client.counts["deconstruct_card_batch"] == 1
    assert "deconstruct_card" not in client.counts  # 逐章零调用（不放大无效请求）
    # 失败账：致命批也落 failed 行（评审 P3——账本不缺失败尝试）
    from deconstruct import policy as dec_policy

    fatal_rows = [u for u in _units("der-batch-fatal") if u.stage == "card_batch"]
    assert len(fatal_rows) == 1 and fatal_rows[0].status == "failed"
    assert fatal_rows[0].error_kind == dec_policy.KIND_AUTH


def test_merge_max_tokens_env_guard(monkeypatch):
    """DECONSTRUCT_MERGE_MAX_TOKENS 下限护栏：误配 0/小值回安全默认（评审 P3）。"""
    from deconstruct import capabilities as caps_mod

    caps = caps_mod.DEFAULT_CAPS
    monkeypatch.delenv("DECONSTRUCT_MERGE_MAX_TOKENS", raising=False)
    assert caps_mod.merge_max_tokens(caps) == 8192
    monkeypatch.setenv("DECONSTRUCT_MERGE_MAX_TOKENS", "0")
    assert caps_mod.merge_max_tokens(caps) == 8192
    monkeypatch.setenv("DECONSTRUCT_MERGE_MAX_TOKENS", "8")
    assert caps_mod.merge_max_tokens(caps) == 8192
    monkeypatch.setenv("DECONSTRUCT_MERGE_MAX_TOKENS", "16384")
    assert caps_mod.merge_max_tokens(caps) == 16384


def test_cancel_via_endpoint_stops_dispatcher_task(monkeypatch):
    """全链取消（用户报告「任务没有取消、没有停止」的集成级反证钉）：
    HTTP 取消端点 → dispatcher 线程 → 看门狗轮询 → 在途调用被扼断，
    取消在数秒内落地、后续章节不再发起。"""

    from deconstruct.dispatcher import start_dispatcher

    _mk_job("der-cancel-e2e", selected=["world"], chapters=2)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world")})

    async def slow_first(kw, n):
        if n == 0 and kw["operation"] == "deconstruct_card":
            await asyncio.sleep(30)  # 模拟模型挂起：取消必须扼断它而不是等它跑完
        return _card_handler(kw, n)

    client.handlers["deconstruct_card"] = slow_first
    _stub(monkeypatch, client)
    # 该模块 import 时置了 DISPATCHER_OFF=1；本测试要真 dispatcher 线程
    monkeypatch.setenv("DECONSTRUCT_DISPATCHER_OFF", "0")
    start_dispatcher()
    try:
        _run_cancel_e2e_body(client)
    finally:
        # 收线：不停的话常驻轮询会抢跑同进程后续测试造的 queued 任务
        from deconstruct import dispatcher as dec_dispatcher

        dec_dispatcher.stop_dispatcher()
        if dec_dispatcher._thread is not None:
            dec_dispatcher._thread.join(timeout=5)


def _run_cancel_e2e_body(client: FakeClient) -> None:
    import time as time_mod

    deadline = time_mod.monotonic() + 15
    while time_mod.monotonic() < deadline:
        t = _load("der-cancel-e2e")
        if t.status == "running" and client.counts["deconstruct_card"] >= 1:
            break
        time_mod.sleep(0.2)
    assert t.status == "running", f"dispatcher 未接单：{t.status}"

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_local.middleware import get_current_user
    from db import get_db
    from deconstruct.router import router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"id": _UID}

    async def _override_db():
        async with async_session() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app) as tc:
        r = tc.post("/api/deconstruct/tasks/der-cancel-e2e/cancel")
        assert r.status_code == 200, r.text

    started = time_mod.monotonic()
    while time_mod.monotonic() - started < 10:
        t = _load("der-cancel-e2e")
        if t.finished_at is not None:
            break
        time_mod.sleep(0.2)
    assert t.status == "cancelled"
    assert t.finished_at is not None, "取消后未在有限时间内收尾"
    assert time_mod.monotonic() - started < 10, "取消未在数秒内落地（在途调用未被扼断）"
    assert client.counts["deconstruct_card"] == 1, "取消后仍发起了新调用"


# ── 思考档位（D10：拆书默认关思考，用户可选 低/跟随配置）─────────────────────

def test_normalize_thinking_mode():
    from deconstruct.service import normalize_thinking_mode

    assert normalize_thinking_mode("low") == "low"
    assert normalize_thinking_mode("inherit") == "inherit"
    assert normalize_thinking_mode("off") == "off"
    assert normalize_thinking_mode("") == "off"
    assert normalize_thinking_mode("max") == "off"  # 白名单外一律默认关
    assert normalize_thinking_mode(None) == "off"


def test_client_from_config_thinking_override():
    """off/low 覆盖折算成构造参数；inherit（None）跟随 ApiConfig。"""
    from types import SimpleNamespace

    from ai_client import _client_from_config

    cfg = SimpleNamespace(base_url="", api_format="openai", vendor="",
                          thinking_enabled=True, thinking_effort="max")
    off = _client_from_config(cfg, "m", "k", max_retries=0,
                              thinking_enabled=False, thinking_effort="low")
    assert off._thinking_enabled is False and off._thinking_effort == "low"
    low = _client_from_config(cfg, "m", "k", max_retries=0,
                              thinking_enabled=True, thinking_effort="low")
    assert low._thinking_enabled is True and low._thinking_effort == "low"
    inherit = _client_from_config(cfg, "m", "k")
    assert inherit._thinking_enabled is True and inherit._thinking_effort == "max"


def test_run_task_passes_task_thinking_to_resolve(monkeypatch):
    from deconstruct import pipeline, service

    _mk_job("der-think", selected=["world"], chapters=1)

    async def _seed():
        async with async_session() as s:
            t = await s.get(DeconstructJob, "der-think")
            t.thinking_mode = "low"
            await s.commit()
    _run(_seed())

    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world")})
    captured: dict = {}

    def load_layers(name):
        if name == "deconstruct_card":
            return "sys", "u {book_name}|{chapter_no}|{chapter_title}|{chapter_text}"
        return "sys", "u {book_name}|{genre_or_unknown}|{full_synopsis}|{seg_range}|{excerpts}"

    monkeypatch.setattr(pipeline, "CONCURRENCY", 1)
    monkeypatch.setattr(pipeline, "load_layers", load_layers)

    async def fake_resolve(user_id, api_config_id, model, thinking="inherit"):
        captured["thinking"] = thinking
        return client, "m-1"

    monkeypatch.setattr(service, "resolve_client", fake_resolve)
    _run(pipeline.run_task("der-think"))
    assert captured["thinking"] == "low"
    assert _load("der-think").status == "completed"
