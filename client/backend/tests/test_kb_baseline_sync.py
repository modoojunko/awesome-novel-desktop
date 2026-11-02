"""基线包同步测试（c-kb-baseline 批A）：整层替换/幂等/保旧层/升级演练/双账号隔离。

同步器网络面全注入（_fetch_json/_fetch_bytes monkeypatch）——无真实 CDN 依赖；
签名用测试密钥对（打包期烘焙公钥的先例口径）。

断言口径：不只信 status，必须回读库内真实行（曾出过 db.execute 漏 await 导致
「同步成功但零行」照样绿的 P0——状态码断言抓不到该类缺陷）。
"""

import asyncio
import base64
import hashlib
import json
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import event
from sqlalchemy import select as sel

from db import async_session, engine
from kb.baseline import proxy_id
from manifest_crypto import sign_manifest
from models.app_meta import AppMeta
from models.kb import KbBaselineEntry, KbBaselineOverlay, KbBaselineTag

_ed_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_TEST_PRIV = base64.b64encode(bytes(range(32))).decode()
_TEST_KID = "test-k"
_TEST_PUBKEYS = {_TEST_KID: _ed_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}
_BASE = "http://127.0.0.1:1/knowledge/baseline"


def _run(coro):
    return asyncio.run(coro)


def _entry(src_key: str, title: str = "条目", *, instruction: str | None = None,
           genre: str = "玄幻", when: dict | None = None) -> dict:
    return {
        "src_key": src_key, "title": title, "concept": "手法", "genre": genre,
        "instruction": instruction or f"{title}：交手先守后攻，招式收在第三拍。",
        "payload": {"slot": "打斗-节奏", "scene": "打斗"},
        "when": when if when is not None else {"scene": "打斗"},
    }


def _signed_latest(version: int, manifest_sha: str, *, min_client: str | None = None) -> dict:
    body = {"version": version, "manifest_sha256": manifest_sha}
    if min_client:
        body["min_client_version"] = min_client
    return sign_manifest(body, _TEST_PRIV, _TEST_KID)


class _FakeCDN:
    def __init__(self):
        self.latest = None
        self.manifest_raw = b"{}"
        self.entries_raw = b"[]"

    async def get_json(self, client=None, url="", **kw):
        if url.endswith("latest.json"):
            return self.latest
        if url.endswith("manifest.json"):
            return json.loads(self.manifest_raw)
        return None

    async def get_bytes(self, client=None, url="", **kw):
        if url.endswith("entries.jsonl"):
            return self.entries_raw
        if url.endswith("manifest.json"):
            return self.manifest_raw
        return None


_CDN = _FakeCDN()


def _publish(
    version: int,
    entries: list[dict],
    *,
    fmt: int = 1,
    bad_hash: bool = False,
    count: int | None = None,
    min_client: str | None = None,
    extra_lines: list[str] | None = None,
):
    """打包并挂到假 CDN。count 默认＝有效条目数；extra_lines 追加原始坏行。"""
    lines = [json.dumps(e, ensure_ascii=False) for e in entries] + list(extra_lines or [])
    body = "\n".join(lines).encode()
    digest = hashlib.sha256(body).hexdigest()
    manifest = {
        "version": version, "format_version": fmt,
        "entry_count": len(entries) if count is None else count,
        "generated_at": "2026-11-02T00:00:00Z",
        "files": [{"path": "entries.jsonl",
                   "sha256": ("deadbeef" + digest[8:]) if bad_hash else digest}],
    }
    if min_client:
        manifest["min_client_version"] = min_client
    signed = sign_manifest(manifest, _TEST_PRIV, _TEST_KID)
    _CDN.latest = _signed_latest(
        version,
        hashlib.sha256(json.dumps(signed, ensure_ascii=False).encode()).hexdigest(),
        min_client=min_client,
    )
    _CDN.manifest_raw = json.dumps(signed, ensure_ascii=False).encode()
    _CDN.entries_raw = body


def _layer_state() -> tuple[dict[str, KbBaselineEntry], int, int]:
    """回读只读层：{src_key: row}，标签行数，pack_version（AppMeta）。"""

    async def _go():
        async with async_session() as db:
            rows = (await db.execute(sel(KbBaselineEntry))).scalars().all()
            tags = (await db.execute(sel(KbBaselineTag))).scalars().all()
            meta = await db.get(AppMeta, "kb_baseline_version")
            return (
                {r.src_key: r for r in rows},
                len(tags),
                int(meta.value) if meta else 0,
            )

    return _run(_go())


def _overlays(src_key: str) -> dict[str, KbBaselineOverlay]:
    async def _go():
        async with async_session() as db:
            rows = (await db.execute(
                sel(KbBaselineOverlay).where(KbBaselineOverlay.src_key == src_key)
            )).scalars().all()
            return {r.user_id: r for r in rows}

    return _run(_go())


def _capture(fn):
    """执行 fn 并捕获全部 SQL 语句（校验幂等路径零写）。"""
    seen: list[str] = []

    def _rec(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _rec)
    try:
        out = fn()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", _rec)
    return out, seen


@pytest.fixture
def sync_env(monkeypatch):
    from db import Base
    from kb import baseline as bl
    from models.kb import KbBaselineEntry as _E
    from models.kb import KbBaselineOverlay as _O
    from models.kb import KbBaselineTag as _T

    monkeypatch.setattr(bl, "_TRUST_PUBKEYS", _TEST_PUBKEYS)
    monkeypatch.setattr(bl, "_cdn_base", lambda: _BASE)
    monkeypatch.setattr(bl, "_validate_outbound", lambda url: True)
    monkeypatch.setattr(bl, "_fetch_json", _CDN.get_json)
    monkeypatch.setattr(bl, "_fetch_bytes", _CDN.get_bytes)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(lambda sc: Base.metadata.create_all(
                sc, tables=[_E.__table__, _O.__table__, _T.__table__]))

    _run(_setup())

    def _reset():
        from sqlalchemy import delete

        async def _go():
            async with async_session() as db:
                await db.execute(delete(_T))
                await db.execute(delete(_E))
                await db.execute(delete(_O))
                meta = await db.get(AppMeta, bl.VERSION_KEY)
                if meta:
                    await db.delete(meta)
                await db.commit()

        _run(_go())

    _reset()
    yield bl
    _reset()


def _sync(bl, *, db=None):
    return _run(bl.sync_baseline(db))


def test_首装_整层落库_标签物化(sync_env):
    bl = sync_env
    e = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [e])
    r = _sync(bl)
    assert r["status"] == "synced" and r["entries"] == 1, f"got {r}"
    assert r["version"] == 1 and r["tags"] == 5  # concept/genre/slot/scope/scene

    rows, tags, ver = _layer_state()
    assert set(rows) == {e["src_key"]}
    row = rows[e["src_key"]]
    assert row.entry_id == proxy_id(e["src_key"])  # 确定性代理键
    assert row.pack_version == 1
    assert row.concept == "手法" and row.genre == "玄幻"
    assert row.scope == "scene" and row.slot == "打斗-节奏"
    assert row.content_sha256 == hashlib.sha256(e["instruction"].encode()).hexdigest()
    assert row.published_at is not None
    assert ver == 1 and tags == 5


def test_同版本_零写_零DELETE(sync_env):
    bl = sync_env
    _publish(1, [_entry("baseline:玄幻:tech-a", "玄幻手法A")])
    assert _sync(bl)["status"] == "synced"

    r, stmts = _capture(lambda: _sync(bl))
    assert r["status"] == "current" and r["version"] == 1
    writes = [s for s in stmts if s.lstrip().upper().startswith(("DELETE", "INSERT", "UPDATE"))]
    assert writes == [], f"同版本不得有任何写语句，实际：{writes[:3]}"


def test_坏哈希保旧层(sync_env):
    bl = sync_env
    old = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [old])
    assert _sync(bl)["status"] == "synced"

    _publish(2, [_entry("baseline:玄幻:tech-b", "玄幻手法B")], bad_hash=True)
    r = _sync(bl)
    assert r["status"] == "failed" and r["reason"] == "entries_hash"
    rows, _, ver = _layer_state()
    assert set(rows) == {old["src_key"]}  # 旧层原样
    assert rows[old["src_key"]].pack_version == 1 and ver == 1


def test_新格式静默跳过保旧层(sync_env):
    bl = sync_env
    old = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [old])
    assert _sync(bl)["status"] == "synced"

    _publish(2, [_entry("baseline:玄幻:tech-b", "玄幻手法B")], fmt=2)
    r = _sync(bl)
    assert r["status"] == "skipped" and r["reason"] == "format_newer"
    rows, _, ver = _layer_state()
    assert set(rows) == {old["src_key"]} and ver == 1


def test_客户端过旧跳过保旧层(sync_env):
    bl = sync_env
    old = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [old])
    assert _sync(bl)["status"] == "synced"

    _publish(2, [_entry("baseline:玄幻:tech-b", "玄幻手法B")], min_client="9.9.9")
    r = _sync(bl)
    assert r["status"] == "skipped" and r["reason"] == "min_client_version"
    rows, _, ver = _layer_state()
    assert set(rows) == {old["src_key"]} and ver == 1


def test_断网保旧层(sync_env):
    bl = sync_env
    old = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [old])
    assert _sync(bl)["status"] == "synced"

    _CDN.latest = None
    r = _sync(bl)
    assert r["status"] == "failed" and r["reason"] == "latest_invalid"
    rows, _, ver = _layer_state()
    assert set(rows) == {old["src_key"]} and ver == 1


def test_坏行跳过_有效行照落(sync_env):
    bl = sync_env
    good = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(
        1, [good],
        extra_lines=[
            json.dumps(_entry("baseline:玄幻:tech-x", "坏指令",
                              instruction="太短"), ensure_ascii=False),
            json.dumps(_entry("baseline:玄幻:tech-a", "重复键"), ensure_ascii=False),
            "not-json",
        ],
    )
    r = _sync(bl)
    assert r["status"] == "synced" and r["skipped"] == 3, f"got {r}"
    rows, _, _ = _layer_state()
    assert set(rows) == {good["src_key"]}


def test_升级演练_双哈希_孤儿hide_重同步_回退(sync_env):
    bl = sync_env
    a = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    b = _entry("baseline:玄幻:tech-b", "玄幻手法B")
    _publish(1, [a, b])
    assert _sync(bl)["status"] == "synced"

    from kb.baseline import content_sha

    uid = f"ov-{uuid.uuid4().hex[:8]}"

    async def _seed_overlays():
        async with async_session() as db:
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=a["src_key"], action="edit",
                content="用户改写的交手心法。", base_content_sha256=content_sha(a["instruction"])))
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=b["src_key"], action="hide",
                content="", base_content_sha256=content_sha(b["instruction"])))
            await db.commit()

    _run(_seed_overlays())

    # v2：A 官方修订（→ 双哈希 mismatch），B 下架，C 新增
    a2 = _entry("baseline:玄幻:tech-a", "玄幻手法A",
                instruction="官方修订版：交手先守后攻，再借力反打。")
    c2 = _entry("baseline:玄幻:tech-c", "玄幻手法C")
    _publish(2, [a2, c2])
    r = _sync(bl)
    assert r["status"] == "synced" and r["version"] == 2
    rows, _, ver = _layer_state()
    assert set(rows) == {a2["src_key"], c2["src_key"]} and ver == 2
    assert all(row.pack_version == 2 for row in rows.values())

    ovs = _overlays(a["src_key"])
    assert uid in ovs and ovs[uid].action == "edit"
    assert ovs[uid].content == "用户改写的交手心法。"  # 用户副本继续生效
    # mismatch＝「官方有新版」可判定（双哈希零写放大）
    assert ovs[uid].base_content_sha256 != rows[a2["src_key"]].content_sha256
    assert _overlays(b["src_key"]) == {}  # 下架条目的 hide 孤儿被清（edit 才保留）

    # 重同步同版本：零写、副本原样（带回）
    r2, stmts = _capture(lambda: _sync(bl))
    assert r2["status"] == "current"
    assert not [s for s in stmts if s.lstrip().upper().startswith(("DELETE", "INSERT", "UPDATE"))]
    assert _overlays(a["src_key"])[uid].content == "用户改写的交手心法。"

    # 回退到 v1（允许回退）：旧版原文透明，副本仍遮蔽
    _publish(1, [a, b])
    assert _sync(bl)["status"] == "synced"
    rows, _, ver = _layer_state()
    assert rows[a["src_key"]].instruction == a["instruction"] and ver == 1
    assert _overlays(a["src_key"])[uid].action == "edit"


def test_双账号隔离(sync_env):
    bl = sync_env
    e = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [e])
    assert _sync(bl)["status"] == "synced"

    u1, u2 = f"iso1-{uuid.uuid4().hex[:8]}", f"iso2-{uuid.uuid4().hex[:8]}"

    async def _seed():
        async with async_session() as db:
            db.add(KbBaselineOverlay(user_id=u1, src_key=e["src_key"], action="edit",
                                     content="一号的改写。", base_content_sha256="h1"))
            db.add(KbBaselineOverlay(user_id=u2, src_key=e["src_key"], action="hide",
                                     content="", base_content_sha256="h2"))
            await db.commit()

    _run(_seed())
    e2 = dict(e)
    e2["instruction"] = "官方第二版：动作收在第三拍之后。"
    _publish(2, [e2])
    assert _sync(bl)["status"] == "synced"

    ovs = _overlays(e["src_key"])
    assert set(ovs) == {u1, u2}
    assert ovs[u1].action == "edit" and ovs[u1].content == "一号的改写。"
    assert ovs[u1].base_content_sha256 == "h1"
    assert ovs[u2].action == "hide" and ovs[u2].content == ""
    assert ovs[u2].base_content_sha256 == "h2"


def test_未配置静默跳过(sync_env, monkeypatch):
    bl = sync_env
    monkeypatch.setattr(bl, "_cdn_base", lambda: "")
    r = _sync(bl)
    assert r["status"] == "skipped" and r["reason"] == "not_configured"


def test_启动补偿_无事件循环静默跳过():
    from kb import baseline as bl

    async def _boom():  # 不该被调用
        raise AssertionError("no running loop 时不得发同步")

    orig = bl.sync_baseline
    bl.sync_baseline = _boom
    try:
        bl.schedule_sync()  # 同步上下文无 loop：静默返回，不抛
    finally:
        bl.sync_baseline = orig


def test_启动补偿_后台任务执行(monkeypatch):
    from kb import baseline as bl

    calls: list[int] = []

    async def _fake():
        calls.append(1)
        return {"status": "current"}

    monkeypatch.setattr(bl, "sync_baseline", _fake)

    async def _go():
        bl.schedule_sync()  # 不 await：立即返回
        assert calls == []  # 挂接本身不阻塞
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    _run(_go())
    assert calls == [1]
