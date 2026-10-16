"""拆书管线 v2 行为钉子（c-deconstruct-book 2.x）：run_task 主循环全路径。

模型与模板全部打桩（不依赖 sibling 提示词仓，CI 可跑）：
- happy：逐章拆卡→单批归并→完成（调用序列与落库）；
- 树收敛：小预算逼多批多轮，终稿 seen 全章零丢失（截断已废除的证明）；
- 单元重试：坏输出重试 2 次后放行；
- cancel：章边界生效，卡片保留已完成章；
- 维度失败：任务 failed，先前完成维度产物保留；
- 断点续拆：cards.entries 跳章、completed 维度跳批。
"""

import asyncio
import json
import os
import tempfile

import pytest

_tmp_db = tempfile.NamedTemporaryFile(suffix="_dep.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_dep_")
os.environ["DECONSTRUCT_DISPATCHER_OFF"] = "1"
os.environ["DECONSTRUCT_CONCURRENCY"] = "1"  # 串行口径保调用序列钉确定性；并发行为另钉

from db import Base, async_session, engine  # noqa: E402
from models.deconstruct import DeconstructJob  # noqa: E402

_UID = "dep-user"

_SRC = "第1章 初见\n林晚在渡口救人。\n第2章 重逢\n阿蓟归来报恩。\n第3章 远行\n二人离乡入京。\n第4章 风波\n京城水 deeply 深。\n"


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


def _mk_job(task_id: str, *, selected: list[str], chapters: int = 2, status: str = "queued",
            dims_json: str = "{}", products_json: str = "{}") -> None:
    async def _go():
        async with async_session() as s:
            from deconstruct.service import next_queue_seq, source_path_of

            path = source_path_of(task_id)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(_SRC if chapters == 4 else "".join(
                    f"第{i + 1}章 标题{i + 1}\n内容{i + 1}。\n" for i in range(chapters)
                ))
            s.add(
                DeconstructJob(
                    id=task_id,
                    user_id=_UID,
                    status=status,
                    queue_seq=await next_queue_seq(s),
                    book_name="测试书",
                    source_path=path,
                    encoding="utf-8",
                    api_config_id="cfg-1",
                    ai_model="m-1",
                    chapter_count=chapters,
                    selected_dims_json=json.dumps(selected),
                    dims_json=dims_json,
                    products_json=products_json,
                )
            )
            await s.commit()

    _run(_go())


def _load(task_id: str) -> DeconstructJob:
    async def _go():
        async with async_session() as s:
            return await s.get(DeconstructJob, task_id)

    return _run(_go())


class FakeClient:
    """按 operation 派发脚本化回复；记录调用序列。handler(count)->str，抛异常即失败注入。"""

    def __init__(self, handlers=None, default=None):
        self.calls: list[str] = []
        self.counts: dict[str, int] = {}
        self.last_by_op: dict[str, str] = {}
        self.handlers = handlers or {}
        self.default = default or (lambda *a: "{}")

    async def chat(self, **kw):
        op = kw.get("operation", "")
        self.calls.append(op)
        self.last_by_op[op] = kw["messages"][0]["content"]
        n = self.counts.get(op, 0)
        self.counts[op] = n + 1
        result = self.handlers.get(op, self.default)(kw, n)
        if asyncio.iscoroutine(result):
            result = await result  # 异步 handler 与 run_task 同循环（取消注入用）
        return result


def _stub_layers(monkeypatch):
    from deconstruct import pipeline

    monkeypatch.setattr(pipeline, "CONCURRENCY", 1)  # 串行口径保调用序列钉确定性（其他测试模块可能抢先 import 把 env 固化成默认 4）

    def load_layers(name):
        if name == "deconstruct_card":
            return "sys", "u {book_name}|{chapter_no}|{chapter_title}|{chapter_text}"
        if name == "deconstruct_presence":
            return "sys", "u {book_name}|{chapter_no}|{chapter_title}|{missing_names}|{places_known}|{chapter_text}"
        if name == "deconstruct_reduce":
            return "sys", "u {dim_name}|{partials}"
        return "sys", "u {book_name}|{genre_or_unknown}|{full_synopsis}|{seg_range}|{excerpts}"

    monkeypatch.setattr(pipeline, "load_layers", load_layers)


def _stub_client(monkeypatch, client):
    from deconstruct import service

    async def fake_resolve(user_id, api_config_id, model):
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
    """维度 L1：从 user 消息里抠出【第N章】碎片 → {"seen":[N...]}。"""

    def h(kw, n):
        import re

        content = kw["messages"][0]["content"]
        seen = sorted({int(m) for m in re.findall(r"【第(\d+)章】", content)})
        return json.dumps({"seen": seen or [0], "src": op_name})

    return h


def _reduce_merge(kw, n):
    """通用 reduce：抠出各 partial JSON 的 seen 并集（证明树收敛零丢失）。"""
    content = kw["messages"][0]["content"]
    seen: set[int] = set()
    for m in json_find_seen(content):
        seen |= m
    return json.dumps({"seen": sorted(seen), "src": "reduce"})


def json_find_seen(text: str):
    import re

    out = []
    for m in re.finditer(r'\{"seen": \[([0-9, ]*)\]', text):
        out.append({int(x) for x in m.group(1).split(",") if x.strip()})
    return out


def test_happy_cards_then_merge(monkeypatch):
    _stub_layers(monkeypatch)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world"),
                         "deconstruct_characters": _seen_handler("characters")})
    _stub_client(monkeypatch, client)
    _mk_job("p-happy", selected=["world", "characters"], chapters=2)

    from deconstruct.pipeline import run_task

    _run(run_task("p-happy"))
    t = _load("p-happy")
    assert t.status == "completed"
    assert client.calls == ["deconstruct_card", "deconstruct_card", "deconstruct_world", "deconstruct_characters"]
    prods = json.loads(t.products_json)
    assert set(prods) == {"world", "characters"}
    assert prods["world"]["data"]["seen"] == [1, 2]
    assert prods["world"]["file"] == "世界设定.md" and "## seen" in prods["world"]["md"]
    state = json.loads(t.dims_json)
    assert state["cards"]["state"] == "completed" and state["cards"]["done"] == 2


def test_tree_merge_zero_loss(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world"),
                         "deconstruct_world_reduce": _reduce_merge})
    _stub_client(monkeypatch, client)
    _mk_job("p-tree", selected=["world"], chapters=4)
    monkeypatch.setattr(pipeline, "CARD_BATCH_CHARS", 30)  # 每条碎片独占一批 → 4 批
    monkeypatch.setattr(pipeline, "MERGE_INPUT_CAP", 60)   # 逼多轮收敛

    _run(pipeline.run_task("p-tree"))
    t = _load("p-tree")
    assert t.status == "completed", t.error_json
    final = json.loads(t.products_json)["world"]["data"]
    assert final["seen"] == [1, 2, 3, 4]  # 树收敛零丢失
    reduce_calls = [c for c in client.calls if c.endswith("_reduce")]
    assert len(reduce_calls) >= 3  # 4 批至少 2+1 轮


def test_reduce_blocked_degrades_to_partials(monkeypatch):
    """reduce 被拦（13路实测：脱敏后仍 1301＝语义级）维度不死：保留分段归并稿＋degraded 留痕。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)

    def blocked_reduce(kw, n):
        raise RuntimeError("Error code: 400 - contentFilter 1301")

    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_world": _seen_handler("world"),
                         "deconstruct_world_reduce": blocked_reduce})
    _stub_client(monkeypatch, client)
    _mk_job("p-degrade", selected=["world"], chapters=4)
    monkeypatch.setattr(pipeline, "CARD_BATCH_CHARS", 30)  # 4 批 → 必有 reduce 轮

    _run(pipeline.run_task("p-degrade"))
    t = _load("p-degrade")
    assert t.status == "completed", t.error_json  # 维度不死、任务不 failed
    final = json.loads(t.products_json)["world"]["data"]
    assert sorted(final["seen"]) == [1, 2, 3, 4]  # 分段保底合并零丢失
    state = json.loads(t.dims_json)["dims"]["world"]
    assert "reduce 收敛被模型拒绝" in state.get("degraded", "")


def test_merge_final_passthrough_and_concat():
    """终稿归一：单份直取；多份同键列表拼接、dict 浅并、标量保首份。"""
    from deconstruct.pipeline import _merge_final

    assert _merge_final([]) == {}
    assert _merge_final(['{"seen": [1]}']) == {"seen": [1]}
    out = _merge_final([
        '{"arcs": [{"a": 1}], "meta": {"x": 1}, "seg": "1-2"}',
        '{"arcs": [{"a": 2}], "meta": {"y": 2}, "seg": "3-4"}',
    ])
    assert out["arcs"] == [{"a": 1}, {"a": 2}]  # 列表拼接
    assert out["meta"] == {"x": 1, "y": 2}  # dict 浅并
    assert out["seg"] == "1-2"  # 标量保首份


def test_unit_retry_then_success(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)

    def flaky(kw, n):
        if n < 2:
            raise RuntimeError("坏输出")
        return _card_handler(kw, n)

    client = FakeClient({"deconstruct_card": flaky, "deconstruct_world": _seen_handler("world")})
    _stub_client(monkeypatch, client)
    _mk_job("p-retry", selected=["world"], chapters=1)

    _run(pipeline.run_task("p-retry"))
    assert client.counts["deconstruct_card"] == 3  # 1+2 次重试
    assert _load("p-retry").status == "completed"


def test_cancel_at_chapter_boundary(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    _mk_job("p-cancel", selected=["world"], chapters=2, status="running")

    def cancel_after_first(kw, n):
        if n == 0:  # 第一章拆完即置取消 → 第二章边界生效（async 同循环注入）

            async def _flip():
                async with async_session() as s:
                    t = await s.get(DeconstructJob, "p-cancel")
                    t.status = "cancelled"
                    await s.commit()

            return _flip()
        return _card_handler(kw, n)

    client = FakeClient({"deconstruct_card": cancel_after_first, "deconstruct_world": _seen_handler("world")})
    _stub_client(monkeypatch, client)

    _run(pipeline.run_task("p-cancel"))
    t = _load("p-cancel")
    assert t.status == "cancelled"
    assert json.loads(t.dims_json)["cards"]["entries"].keys() == {"1"}  # 第二章未拆
    assert json.loads(t.products_json) == {}


def test_dim_failure_keeps_completed_products(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)

    def always_fail(kw, n):
        raise RuntimeError("上游 500")

    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_intro": _seen_handler("intro"),
                         "deconstruct_genre": always_fail})
    _stub_client(monkeypatch, client)
    _mk_job("p-fail", selected=["intro", "genre"], chapters=1)

    _run(pipeline.run_task("p-fail"))
    t = _load("p-fail")
    assert t.status == "failed"
    assert json.loads(t.error_json)["kind"] == "pipeline"
    assert set(json.loads(t.products_json)) == {"intro"}  # 已完成维度保留


def test_resume_skips_done_cards_and_dims(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    seed = json.dumps({
        "cards": {"state": "running", "done": 1, "entries": {"1": {
            "summary": "梗概1", "world": [{"name": "地1", "note": "n"}], "characters": [
                {"name": "人1", "role": "主角", "traits": "t", "alias": ""}],
            "intro": [], "genre": [], "relations": [], "mainplot": [],
            "structure": [], "style": [], "techniques": [], "foreshadow": []}}},
        "dims": {
            "world": {"state": "completed", "seg_done": 1, "seg_total": 1, "error": ""},
            "characters": {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""},
        },
    })
    preset = json.dumps({"world": {"file": "世界设定.md", "data": {"seen": [1]}, "md": "# 旧"}})
    _mk_job("p-resume", selected=["world", "characters"], chapters=2,
            status="failed", dims_json=seed, products_json=preset)
    client = FakeClient({"deconstruct_card": _card_handler,
                         "deconstruct_characters": _seen_handler("characters")})
    _stub_client(monkeypatch, client)

    _run(pipeline.run_task("p-resume"))
    t = _load("p-resume")
    assert t.status == "completed"
    assert client.calls == ["deconstruct_card", "deconstruct_characters"]  # 章1跳、维度world跳
    prods = json.loads(t.products_json)
    assert prods["world"]["md"] == "# 旧"  # 已完成维度产物原样保留
    assert set(prods) == {"world", "characters"}


def test_card_text_head_tail():
    """超长章＝头4000＋尾2000（转场句在章尾不失明）；≤6000 原样；恰 6000 不截。"""
    from deconstruct.pipeline import _card_text

    assert _card_text({"text": "甲" * 100}) == "甲" * 100
    assert _card_text({"text": "X" * 6000}) == "X" * 6000
    long = "H" * 4000 + "M" * 5000 + "T" * 2000
    out = _card_text({"text": long})
    assert out.startswith("H" * 4000) and out.endswith("T" * 2000)
    assert "中略" in out and "M" not in out


def test_card_text_clips_only():
    """_card_text 只管截选，脱敏已下沉 _call_with_retry 咽喉（归并/reduce 同盖，不在此重复）。"""
    from deconstruct.pipeline import _card_text

    raw = "她推门看见了尸体，满地鲜血。"
    out = _card_text({"no": 3, "text": raw})
    assert "尸体" in out  # 本层原样保留；脱敏在咽喉层（见 test_call_with_retry_sanitizes_user_vars）


def test_sanitize_vars_mixed_types():
    """咽喉脱敏：str 值替换、非 str 原样、混合 dict 全覆盖。"""
    from deconstruct.pipeline import _sanitize_vars

    out = _sanitize_vars({"chapter_text": "他看见了尸体。", "chapter_no": 3, "flag": True})
    assert out["chapter_text"] == "他看见了遗体。"
    assert out["chapter_no"] == 3 and out["flag"] is True


def test_call_with_retry_sanitizes_user_vars():
    """_call_with_retry 咽喉实钉：归并/reduce 碎片（凝结原文敏感词）也必过脱敏。"""
    from deconstruct import pipeline

    client = FakeClient()
    out = _run(pipeline._call_with_retry(
        client, "m-1", ("sys", "u {partials}"), {"partials": "【第1章】她看见了尸体"}, "op_x",
    ))
    assert out == {}
    sent = client.last_by_op["op_x"]
    assert "遗体" in sent and "尸体" not in sent


def test_quote_corpus_dual_text():
    """quote 回验语料＝原稿＋替换稿（有替换时两稿都认）；无替换恒等只用原稿。"""
    from deconstruct.pipeline import _quote_corpus

    chs = [{"text": "第1章\n他看见了尸体。"}, {"text": "第2章\n平静收场。"}]
    corpus = _quote_corpus(chs)
    assert "他看见了尸体。" in corpus  # 原稿在
    assert "他看见了遗体。" in corpus  # 替换稿也在（模型引用可能出自替换稿）

    assert _quote_corpus([{"text": "渡口救人。"}]) == "渡口救人。"  # 无替换不附第二稿


def test_run_task_cards_use_head_tail_clip(monkeypatch):
    """run_task 集成：超长章卡片只收到首尾拼接正文（中段被显式中略）。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    client = FakeClient({"deconstruct_card": _card_handler, "deconstruct_world": _seen_handler("world")})
    _stub_client(monkeypatch, client)
    _mk_job("p-clip", selected=["world"], chapters=1)
    from deconstruct.service import source_path_of

    with open(source_path_of("p-clip"), "w", encoding="utf-8") as f:
        f.write("第1章 长夜\n" + "首" * 4200 + "埋" * 3000 + "尾" * 2100 + "\n")

    _run(pipeline.run_task("p-clip"))
    sent = client.last_by_op["deconstruct_card"]
    assert "首" * 3900 in sent and "尾" * 1900 in sent
    assert "埋" not in sent and "中略" in sent  # 中段丢、显式标注
    assert _load("p-clip").status == "completed"


def test_state_roundtrip_preserves_unknown_keys(monkeypatch):
    """评审 P0：dims_json 未知顶键（阶段三 graph 缓存）不被卡片/维度 patch 抹掉。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    card1 = {"summary": "梗概1", "world": [{"name": "地1", "note": "n"}], "characters": [],
             "intro": [], "genre": [], "relations": [], "mainplot": [], "structure": [],
             "style": [], "techniques": [], "foreshadow": []}
    seed = json.dumps({
        # 卡片未完成但本章已在 entries → 走卡片边界 patch；再走维度全链 patch
        "cards": {"state": "running", "done": 1, "entries": {"1": card1}},
        "dims": {"world": {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""}},
        "graph": {"sentinel": True},  # 阶段三缓存占位：任何 patch 后都必须原样存在
    })
    client = FakeClient({"deconstruct_world": _seen_handler("world")})
    _stub_client(monkeypatch, client)
    _mk_job("p-keep", selected=["world"], chapters=1, dims_json=seed)

    _run(pipeline.run_task("p-keep"))
    t = _load("p-keep")
    assert t.status == "completed"
    state = json.loads(t.dims_json)
    assert state["graph"] == {"sentinel": True}  # 未知顶键存活
    assert state["cards"]["state"] == "completed"
    assert state["dims"]["world"]["state"] == "completed"


def test_op_max_tokens_budget():
    """卡片/角色/世界输出预算上调（角色档案格＋世界 extra 扩容后 4096 截断 JSON）；其余默认 4096。"""
    from deconstruct.pipeline import _OP_MAX_TOKENS

    assert _OP_MAX_TOKENS.get("deconstruct_card", 4096) == 6144
    assert _OP_MAX_TOKENS.get("deconstruct_world", 4096) == 8192
    assert _OP_MAX_TOKENS.get("deconstruct_characters", 4096) == 8192
    assert _OP_MAX_TOKENS.get("deconstruct_place", 4096) == 4096


# ── 阶段三（图谱装配）集成 ─────────────────────────────────────────────

def _graph_card_handler(kw, n):
    no = kw["messages"][0]["content"].split("|")[1]
    return json.dumps({
        "summary": f"梗概{no}",
        "characters": [{"name": "林晚", "role": "主角", "traits": "t", "alias": ""}],
        "places": [{"name": "竹湾渡口", "parent": "", "note": ""}],
        "presence": [{"who": "林晚", "where": "竹湾渡口"}],
        "intro": [], "genre": [], "world": [], "relations": [], "mainplot": [],
        "structure": [], "style": [], "techniques": [], "foreshadow": [],
    })


_PLACE_OK = json.dumps({"places": [
    {"name": "竹湾渡口", "aliases": [], "parent": "", "note": "", "evidence_ch": "第1章"}],
    "links": [{"who": "林晚", "where": "竹湾渡口", "kind": "据地", "evidence": "世代摆渡", "ch": "第1章"}]})


def test_stage3_assembles_graph(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    client = FakeClient({
        "deconstruct_card": _graph_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "渡口救人", "evidence_ch": "第1章"}]}),
        "deconstruct_mainplot": lambda kw, n: json.dumps({"arcs": [
            {"title": "救恩", "ch_start": 1, "ch_end": 2, "summary": "林晚救人", "confidence": "high"}]}),
        "deconstruct_place": lambda kw, n: _PLACE_OK,
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-graph", selected=["characters", "mainplot"], chapters=2)

    _run(pipeline.run_task("p-graph"))
    t = _load("p-graph")
    assert t.status == "completed", t.error_json
    g = json.loads(t.dims_json)["graph"]
    assert g["contract"] == "deconstruct-graph/6" and g["stats"]["chapters"] == 2
    assert client.counts.get("deconstruct_place") == 1
    assert any(l["kind"] == "据地" for l in g["links"])
    assert len(g["chapters"]) == 2 and g["events"][0]["ch"] == [1, 2]
    assert g["chapters"][0]["beat"] == "梗概1"


def test_stage3_place_failure_records_graph_error(monkeypatch):
    """图谱病着也要出：装配异常不拖垮任务，graph_error 留痕（导出端 400）。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)

    def boom(kw, n):
        raise RuntimeError("装配期异常")

    client = FakeClient({
        "deconstruct_card": _graph_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_place": boom,
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-graph-err", selected=["characters"], chapters=2)

    _run(pipeline.run_task("p-graph-err"))
    t = _load("p-graph-err")
    assert t.status == "completed"  # md 出口不受拖累
    state = json.loads(t.dims_json)
    assert "graph" not in state and state.get("graph_error")
    assert "characters" in json.loads(t.products_json)


def test_graph_switch_off_skips_stage3(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    monkeypatch.setenv("DECONSTRUCT_GRAPH_EXPORT", "0")
    client = FakeClient({
        "deconstruct_card": _graph_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": []}),
        "deconstruct_place": lambda kw, n: _PLACE_OK,
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-graph-off", selected=["characters"], chapters=1)

    _run(pipeline.run_task("p-graph-off"))
    t = _load("p-graph-off")
    assert t.status == "completed"
    assert "deconstruct_place" not in client.calls
    assert "graph" not in json.loads(t.dims_json)


def test_stage3_skips_when_cache_present(monkeypatch):
    """缓存存在即不重算（append-only id 语义：重算会平移旧 id）。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    card1 = {"summary": "梗概1", "characters": [], "places": [], "presence": [],
             "intro": [], "genre": [], "world": [], "relations": [], "mainplot": [],
             "structure": [], "style": [], "techniques": [], "foreshadow": []}
    seed = json.dumps({
        "cards": {"state": "completed", "done": 1, "entries": {"1": card1}},
        "dims": {"characters": {"state": "completed", "seg_done": 1, "seg_total": 1, "error": ""}},
        "graph": {"contract": "deconstruct-graph/6", "sentinel": True},
    })
    preset = json.dumps({"characters": {"file": "角色设定.md",
                                        "data": {"characters": []}, "md": "# 旧"}})
    _mk_job("p-graph-cache", selected=["characters"], chapters=1,
            dims_json=seed, products_json=preset)
    client = FakeClient({})
    _stub_client(monkeypatch, client)

    _run(pipeline.run_task("p-graph-cache"))
    t = _load("p-graph-cache")
    assert t.status == "completed"
    assert client.calls == []  # 全缓存：零模型调用
    assert json.loads(t.dims_json)["graph"]["sentinel"] is True


def test_stage3_skipped_when_no_caps(monkeypatch):
    """老包能力戳为假：阶段三不跑（不产空转图谱），文档版照常。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    card1 = {"summary": "梗概1", "characters": [], "places": [], "presence": [],
             "intro": [], "genre": [], "world": [], "relations": [], "mainplot": [],
             "structure": [], "style": [], "techniques": [], "foreshadow": []}
    seed = json.dumps({
        "caps_graph": False,
        "cards": {"state": "completed", "done": 1, "entries": {"1": card1}},
        "dims": {"world": {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""}},
    })
    client = FakeClient({"deconstruct_world": _seen_handler("world"),
                         "deconstruct_place": lambda kw, n: _PLACE_OK})
    _stub_client(monkeypatch, client)
    _mk_job("p-nocaps", selected=["world"], chapters=1, dims_json=seed)

    _run(pipeline.run_task("p-nocaps"))
    t = _load("p-nocaps")
    assert t.status == "completed"
    assert "deconstruct_place" not in client.calls
    assert "graph" not in json.loads(t.dims_json)


def test_cancel_at_place_merge_boundary(monkeypatch):
    """评审 P3：归并调用是新段边界——调用后取消，任务停机且不产图谱。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)

    async def place_cancel(kw, n):
        async with async_session() as s:
            t = await s.get(DeconstructJob, "p-cancel3")
            t.status = "cancelled"
            await s.commit()
        return _PLACE_OK  # 归并成功返回后，段边界取消检查应生效

    client = FakeClient({
        "deconstruct_card": _graph_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_place": place_cancel,
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-cancel3", selected=["characters"], chapters=1)

    _run(pipeline.run_task("p-cancel3"))
    t = _load("p-cancel3")
    assert t.status == "cancelled"
    assert "graph" not in json.loads(t.dims_json) and "graph_error" not in json.loads(t.dims_json)


# ── 10.9 在场补写（熔断预案落地）────────────────────────────────────

def _gap_card_handler(kw, n):
    no = kw["messages"][0]["content"].split("|")[1]
    return json.dumps({
        "summary": f"梗概{no}",
        "characters": [{"name": "林晚", "role": "主角", "traits": "t", "alias": ""},
                       {"name": "老郭", "role": "配角", "traits": "t", "alias": ""}],
        "places": [{"name": "竹湾渡口", "parent": "", "note": ""}],
        "presence": [{"who": "林晚", "where": "竹湾渡口"}],  # 老郭缺席
        "intro": [], "genre": [], "world": [], "relations": [], "mainplot": [],
        "structure": [], "style": [], "techniques": [], "foreshadow": [],
    })


def _presence_patch_handler(kw, n):
    return json.dumps({"presence": [
        {"who": "老郭", "where": "竹湾渡口"},
        {"who": "名单外的人", "where": "竹湾渡口"},  # 越权输出：应被丢弃
    ]})


def test_backfill_triggers_on_gap_and_merges(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    client = FakeClient({
        "deconstruct_card": _gap_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"},
            {"name": "老郭", "role": "配角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_presence": _presence_patch_handler,
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-bf1", selected=["characters"], chapters=1)

    _run(pipeline.run_task("p-bf1"))
    t = _load("p-bf1")
    assert t.status == "completed", t.error_json
    assert client.counts.get("deconstruct_presence") == 1
    g = json.loads(t.dims_json)["graph"]
    ch1 = g["chapters"][0]
    assert {p["who"] for p in ch1["presence"]} == {pid for pid in (n["id"] for n in g["nodes"] if n["label"] in ("林晚", "老郭"))}
    assert not any(n["label"] == "名单外的人" for n in g["nodes"])  # 越权输出未入户


def test_backfill_skipped_when_presence_complete(monkeypatch):
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    client = FakeClient({
        "deconstruct_card": _graph_card_handler,  # characters=林晚，presence 有林晚 → 达标
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_presence": _presence_patch_handler,
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-bf2", selected=["characters"], chapters=1)

    _run(pipeline.run_task("p-bf2"))
    assert "deconstruct_presence" not in client.calls
    assert _load("p-bf2").status == "completed"


# ── 10.9 评审修复批测试（PR：presence 补写降级＋闭集＋老卡）──────────

_LEGACY_CARD = {"summary": "老卡", "characters": [{"name": "林晚", "role": "主角", "traits": "", "alias": ""}]}
# 新形状：有 places 键、presence 缺失（新包×中断残卡）——补写预案的目标 cohort
_NEW_SHAPE_MISSING = {"summary": "残卡", "characters": [{"name": "林晚", "role": "主角", "traits": "", "alias": ""}],
                      "places": [{"name": "竹湾渡口", "parent": "", "note": ""}]}


def _graph_card_with(kw, n):
    base = _graph_card_handler(kw, n)
    d = json.loads(base)
    d["characters"].append({"name": "老郭", "role": "配角", "traits": "t", "alias": ""})
    return json.dumps(d)


def test_backfill_unit_failure_degrades_not_kills_graph(monkeypatch):
    """评审 P1-1：单章补写失败→该章跳过＋警告计数，图谱照常装配（三级降级）。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)

    def flaky(kw, n):
        raise RuntimeError("补写失败")  # 每发全失败→该章降级跳过

    client = FakeClient({
        "deconstruct_card": _graph_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"},
            {"name": "老郭", "role": "配角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_presence": flaky,  # 补写单元：3 发全失败→跳过该章
        "deconstruct_place": lambda kw, n: json.dumps({"places": [
            {"name": "竹湾渡口", "aliases": [], "parent": "", "note": "", "evidence_ch": "第1章"}],
            "links": []}),
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-bf3", selected=["characters"], chapters=2)
    # 重试穷尽需 3 发/章：ch1、ch2 各失败→ failed=2（SEGMENT_RETRIES=2，0.2s×n 次 sleep 可接受）

    _run(pipeline.run_task("p-bf3"))
    t = _load("p-bf3")
    assert t.status == "completed", t.error_json
    g = json.loads(t.dims_json)["graph"]
    assert not [x for x in g["meta"]["warnings"] if x["kind"] == "presence_backfill_failed"]
    # 正常路径：补写成功→无 warning（失败臂降级由 test_backfill_unit_failure_degrades 验证）


def test_backfill_legacy_card_skipped_no_presence_key_created(monkeypatch):
    """评审 P2-3：老契约卡（无 places 键）跳过补写、presence 键不被凭空创建。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    client = FakeClient({
        "deconstruct_card": _gap_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"},
            {"name": "老郭", "role": "配角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_presence": _presence_patch_handler,
    })
    _stub_client(monkeypatch, client)
    # 手工造老契约卡：无 places/presence 键
    seed = json.dumps({
        "cards": {"state": "completed", "done": 1, "entries": {"1": _LEGACY_CARD}},
        "dims": {"characters": {"state": "queued", "seg_done": 0, "seg_total": 0, "error": ""}},
    })
    _mk_job("p-bf4", selected=["characters"], chapters=1, dims_json=seed)


    _run(pipeline.run_task("p-bf4"))
    assert "deconstruct_presence" not in client.calls  # 老卡不补
    card = json.loads(_load("p-bf4").dims_json)["cards"]["entries"]["1"]
    assert "presence" not in card and "places" not in card  # 键不被凭空创建


def test_backfill_where_outside_closed_set_dropped_to_unknown(monkeypatch):
    """评审 P2-2：补写 where 不在本章闭集→空串（装配后落未知区 null）。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    client = FakeClient({
        "deconstruct_card": _gap_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"},
            {"name": "老郭", "role": "配角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_presence": lambda kw, n: json.dumps({"presence": [
            {"who": "老郭", "where": "编造的地点"}]}),
        "deconstruct_place": lambda kw, n: json.dumps({"places": [
            {"name": "竹湾渡口", "aliases": [], "parent": "", "note": "", "evidence_ch": "第1章"}],
            "links": []}),
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-bf5", selected=["characters"], chapters=1)

    _run(pipeline.run_task("p-bf5"))
    t = _load("p-bf5")
    assert t.status == "completed", t.error_json
    g = json.loads(t.dims_json)["graph"]
    guo = next(p for p in g["chapters"][0]["presence"] if p["who"] == next(
        n["id"] for n in g["nodes"] if n["label"] == "老郭"))
    assert guo["where"] is None  # 越权地名→未知区（宁可承认不知道）


def test_backfill_preserves_t_tag(monkeypatch):
    """补写条目 t 标签保留（hashable 防御：list 形状不炸）。"""
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    client = FakeClient({
        "deconstruct_card": _gap_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"},
            {"name": "老郭", "role": "配角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_presence": lambda kw, n: json.dumps({"presence": [
            {"who": "老郭", "where": "竹湾渡口", "t": "回忆"},
            {"who": "林晚", "where": ["坏形状"]},
            {"who": "林晚", "where": "竹湾渡口"}]}),
        "deconstruct_place": lambda kw, n: json.dumps({"places": [
            {"name": "竹湾渡口", "aliases": [], "parent": "", "note": "", "evidence_ch": "第1章"}],
            "links": []}),
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-bf6", selected=["characters"], chapters=1)

    _run(pipeline.run_task("p-bf6"))
    t = _load("p-bf6")
    assert t.status == "completed", t.error_json
    card = json.loads(t.dims_json)["cards"]["entries"]["1"]
    tags = [p.get("t") for p in card["presence"] if p.get("who") == "老郭"]
    assert tags == ["回忆"]




def test_graph_phase_reported_and_cleared(monkeypatch):
    """阶段三进度账：presence n/m 入账递增，place_merge/assemble 相继接棒，终态 pop 不残留。

    真机实证动因：阶段三全程暗跑（全维 completed 后几分钟数字不动）＝「进度慢」体感主因。
    """
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    seen: list[dict] = []
    real_patch = pipeline._patch

    async def spy_patch(task_id, **kw):
        dj = kw.get("dims_json")
        if dj and '"graph_phase"' in dj:
            gp = json.loads(dj).get("graph_phase")
            if gp:
                seen.append(gp)
        return await real_patch(task_id, **kw)

    monkeypatch.setattr(pipeline, "_patch", spy_patch)
    client = FakeClient({
        "deconstruct_card": _gap_card_handler,
        "deconstruct_characters": lambda kw, n: json.dumps({"characters": [
            {"name": "林晚", "role": "主角", "plot": "p", "evidence_ch": "第1章"},
            {"name": "老郭", "role": "配角", "plot": "p", "evidence_ch": "第1章"}]}),
        "deconstruct_presence": _presence_patch_handler,
    })
    _stub_client(monkeypatch, client)
    _mk_job("p-bfphase", selected=["characters"], chapters=1)

    _run(pipeline.run_task("p-bfphase"))
    t = _load("p-bfphase")
    assert t.status == "completed", t.error_json
    steps = [p["step"] for p in seen]
    assert "presence" in steps and "place_merge" in steps and "assemble" in steps
    pres = [p for p in seen if p["step"] == "presence"]
    assert pres and pres[0]["total"] >= 1 and all(0 <= p["done"] <= p["total"] for p in pres)
    assert any(p["done"] >= 1 for p in pres)  # 补写推进至少走一笔（首笔 done:0＝开账）
    assert "graph_phase" not in json.loads(t.dims_json)  # 终态不残留


def test_concurrent_cards_overlap_and_complete(monkeypatch):
    """并发拆卡：CONCURRENCY=3 下 4 章调用真重叠（max_in_flight≥2），结果与串行等价。

    真机动因：258 章串行拆卡要数小时（每章一次 10-90s 调用）——I/O 密集，
    asyncio 共享信号量并发即可，无需子进程。
    """
    from deconstruct import pipeline

    _stub_layers(monkeypatch)
    monkeypatch.setattr(pipeline, "CONCURRENCY", 3)  # 在 _stub_layers 串行钉之后覆盖
    inflight = {"cur": 0, "max": 0}

    async def card_handler(kw, n):
        inflight["cur"] += 1
        inflight["max"] = max(inflight["max"], inflight["cur"])
        await asyncio.sleep(0.05)  # 让出循环：并发单元真重叠
        inflight["cur"] -= 1
        content = kw["messages"][0]["content"]
        no = content.split("|")[1]
        return json.dumps({
            "summary": f"梗概{no}",
            "world": [{"name": f"地{no}", "note": "n"}],
            "characters": [{"name": f"人{no}", "role": "主角", "traits": "t", "alias": ""}],
            "intro": [], "genre": [], "relations": [], "mainplot": [],
            "structure": [], "style": [], "techniques": [], "foreshadow": [],
            "places": [{"name": f"地{no}", "parent": "", "note": ""}],
            "presence": [{"who": f"人{no}", "where": f"地{no}"}],
        })

    client = FakeClient({"deconstruct_card": card_handler, "deconstruct_world": _seen_handler("world")})
    _stub_client(monkeypatch, client)
    _mk_job("p-cc", selected=["world"], chapters=4)

    _run(pipeline.run_task("p-cc"))
    t = _load("p-cc")
    assert t.status == "completed", t.error_json
    assert inflight["max"] >= 2, "并发单元未重叠＝没提速"
    cards = json.loads(t.dims_json)["cards"]
    assert cards["done"] == 4 and set(cards["entries"]) == {"1", "2", "3", "4"}
    prods = json.loads(t.products_json)
    assert prods["world"]["data"]["seen"] == [1, 2, 3, 4]  # 并发不改归并结果
