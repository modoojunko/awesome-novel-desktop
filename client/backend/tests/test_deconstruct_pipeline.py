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

    def load_layers(name):
        if name == "deconstruct_card":
            return "sys", "u {book_name}|{chapter_no}|{chapter_title}|{chapter_text}"
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
