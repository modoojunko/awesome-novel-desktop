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


async def _fetch_none(client, url):
    """探测必空桩：verdict 由 _validate_outbound 桩控制，fetch 恒 None。"""
    return None



def _entry(src_key: str, title: str = "条目", *, instruction: str | None = None,
           genre: str = "玄幻", when: dict | None = None, concept: str = "手法",
           payload: dict | None = None) -> dict:
    # 判据集与内容仓同集（kb.gates.check_baseline_entry）：手法须带 payload.instruction
    ins = instruction or f"{title}：交手先守后攻，招式收在第三拍。"
    return {
        "src_key": src_key, "title": title, "concept": concept, "genre": genre,
        "instruction": ins,
        "payload": payload or {"instruction": ins, "slot": "打斗-节奏", "scene": "打斗"},
        "when": when if when is not None else {"scene": "打斗"},
    }


def _signed_latest(version: int, manifest_sha: str) -> dict:
    return sign_manifest(
        {"version": version, "manifest_sha256": manifest_sha}, _TEST_PRIV, _TEST_KID
    )


class _FakeCDN:
    def __init__(self):
        self.latest = None
        self.manifest_raw = b"{}"
        self.entries_raw = b"[]"
        self.dead: set[str] = set()  # 含这些片段的主机一律失败（兜底域用例）

    async def get_json(self, client=None, url="", **kw):
        if any(d in url for d in self.dead):
            return None
        if url.endswith("latest.json"):
            return self.latest
        if url.endswith("manifest.json"):
            return json.loads(self.manifest_raw)
        return None

    async def get_bytes(self, client=None, url="", **kw):
        if any(d in url for d in self.dead):
            return None
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
    format_client: str | None = None,
    bad_hash: bool = False,
    count: int | None = None,
    extra_lines: list[str] | None = None,
):
    """打包并挂到假 CDN。count 默认＝有效条目数；extra_lines 追加原始坏行。

    包里只有内容包 version 与 format_client（按哪代客户端写）两个版本概念。
    """
    lines = [json.dumps(e, ensure_ascii=False) for e in entries] + list(extra_lines or [])
    body = "\n".join(lines).encode()
    digest = hashlib.sha256(body).hexdigest()
    manifest = {
        "version": version,
        "entry_count": len(entries) if count is None else count,
        "generated_at": "2026-11-02T00:00:00Z",
        "files": [{"path": "entries.jsonl",
                   "sha256": ("deadbeef" + digest[8:]) if bad_hash else digest}],
    }
    if format_client:
        manifest["format_client"] = format_client
    signed = sign_manifest(manifest, _TEST_PRIV, _TEST_KID)
    _CDN.latest = _signed_latest(
        version,
        hashlib.sha256(json.dumps(signed, ensure_ascii=False).encode()).hexdigest(),
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
    monkeypatch.setattr(bl, "_validate_outbound", lambda url: (True, "ok"))
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
    _CDN.dead = set()
    yield bl
    _CDN.dead = set()
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


# ── 格式随客户端版本走：manifest 只有 format_client 一个兼容标记 ─────────────


def test_格式代_已登记客户端版本_照收(sync_env):
    """新包带 format_client="0.45.0"（本端代际）→ 照常同步。"""
    bl = sync_env
    e = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [e], format_client="0.45.0")
    r = _sync(bl)
    assert r["status"] == "synced" and r["entries"] == 1, f"got {r}"


def test_格式代_更新的客户端版本_静默跳过保旧层(sync_env):
    """format_client 是不认识的更新代际 → 保持旧层（不猜）。"""
    bl = sync_env
    old = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [old])
    assert _sync(bl)["status"] == "synced"

    _publish(2, [_entry("baseline:玄幻:tech-b", "玄幻手法B")], format_client="0.50.0")
    r = _sync(bl)
    assert r["status"] == "skipped" and r["reason"] == "format_newer", f"got {r}"
    rows, _, ver = _layer_state()
    assert set(rows) == {old["src_key"]} and ver == 1


def test_历史包无格式声明_照收(sync_env):
    """已发布的 v1 只有整数 format_version、没有 format_client → 属第一代，照收。"""
    bl = sync_env
    e = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [e])
    r = _sync(bl)
    assert r["status"] == "synced" and r["entries"] == 1, f"got {r}"


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


# ── 向前兼容（c-kb-forward-compat）：新包里的「新东西」不拖垮老客户端 ─────────


def test_新概念条目_只跳过该条不整包拒收(sync_env):
    """新包引入老客户端不认识的 concept：跳过那一条，其余照常落层。"""
    bl = sync_env
    a = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    b = _entry("baseline:玄幻:tech-b", "玄幻手法B")
    future = _entry("baseline:玄幻:dialog-x", "对话手法X", concept="对话",
                    payload={"instruction": "对话不要每次说完。"})
    _publish(1, [a, b, future])  # entry_count=3，老客户端只认得 2 条
    r = _sync(bl)
    assert r["status"] == "synced" and r["entries"] == 2 and r["skipped"] == 1, f"got {r}"
    rows, _, _ = _layer_state()
    assert set(rows) == {a["src_key"], b["src_key"]}


def test_未知适用维度_跳过该条不整包拒收(sync_env):
    """新包给 when 加了老客户端不认识的维度：该条整条跳过（不敢按窄条件外扩注入）。"""
    bl = sync_env
    ok = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    future = _entry("baseline:玄幻:tech-b", "玄幻手法B",
                    when={"scene": "打斗", "pace": "快"})
    _publish(1, [ok, future])
    r = _sync(bl)
    assert r["status"] == "synced" and r["entries"] == 1 and r["skipped"] == 1, f"got {r}"
    rows, _, _ = _layer_state()
    assert set(rows) == {ok["src_key"]}


def test_读不懂的条目沿用旧层_不缩水不算下架(sync_env):
    """评审 P2：本端读不懂 ≠ 官方下架。

    官方仍发布的条目（只是加了本端不认识的条件维度）必须沿用旧层原文：
    条目不少、用户副本不被误提升成「官方精选（已下架）」。
    """
    from kb.baseline import content_sha
    from models.app_meta import AppMeta
    from models.kb import KbEntry, KbEntryTag
    from models.user import User

    bl = sync_env
    a = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    b = _entry("baseline:玄幻:tech-b", "玄幻手法B")
    _publish(1, [a, b])
    assert _sync(bl)["status"] == "synced"
    old_b_text = _layer_state()[0][b["src_key"]].instruction

    uid = f"carry-{uuid.uuid4().hex[:8]}"

    async def _seed_ov():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=b["src_key"], action="edit",
                content="我的副本：先让三招。", base_content_sha256=content_sha(old_b_text)))
            await db.commit()

    _run(_seed_ov())

    # v2：A 不变、B 加了本端不认识的维度、C 新增
    b_future = _entry("baseline:玄幻:tech-b", "玄幻手法B",
                      when={"scene": "打斗", "pace": "快"})
    c = _entry("baseline:玄幻:tech-c", "玄幻手法C")
    _publish(2, [a, b_future, c])
    r = _sync(bl)
    assert r["status"] == "synced" and r["skipped"] == 1 and r["carried"] == 1, f"got {r}"

    rows, _, ver = _layer_state()
    assert set(rows) == {a["src_key"], b["src_key"], c["src_key"]}  # 不缩水
    assert rows[b["src_key"]].instruction == old_b_text  # 沿用旧原文
    assert rows[b["src_key"]].pack_version == 1  # 内容确实来自上一包
    assert ver == 2

    async def _check():
        async with async_session() as db:
            ovs = (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid))).scalars().all()
            promoted = (await db.execute(sel(KbEntry).where(
                KbEntry.user_id == uid))).scalars().all()
            meta = await db.get(AppMeta, "kb_baseline_last_sync")
            return ovs, promoted, json.loads(meta.value) if meta else {}

    ovs, promoted, last = _run(_check())
    assert len(ovs) == 1 and ovs[0].action == "edit"  # 副本仍在，没被当孤儿
    assert promoted == []  # 没被误提升成「官方精选（已下架）」
    # 摘要口径（评审 P3）：accepted 只计入闸子集，entries 是层内总数（含 carried）
    assert last.get("accepted") == 2 and last.get("skipped") == 1 and last.get("carried") == 1
    assert r["entries"] == 3

    async def _cleanup():
        from sqlalchemy import delete as _del

        async with async_session() as db:
            await db.execute(_del(KbEntryTag).where(KbEntryTag.user_id == uid))
            await db.execute(_del(KbEntry).where(KbEntry.user_id == uid))
            await db.execute(_del(KbBaselineOverlay).where(KbBaselineOverlay.user_id == uid))
            await db.commit()

    _run(_cleanup())


def test_未知顶层字段_照收(sync_env):
    """包级扩展字段（如未来的 published_by）不进判据：老客户端忽略即可。"""
    bl = sync_env
    e = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    e["future_field"] = {"anything": 1}
    _publish(1, [e])
    r = _sync(bl)
    assert r["status"] == "synced" and r["entries"] == 1, f"got {r}"
    rows, _, _ = _layer_state()
    assert set(rows) == {e["src_key"]}


def test_整包读不懂_保旧层不清空(sync_env):
    """一条都读不懂＝代际不兼容：拒绝本次同步，旧层原样保留（绝不落空层）。"""
    bl = sync_env
    old = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [old])
    assert _sync(bl)["status"] == "synced"

    _publish(2, [
        _entry("baseline:玄幻:new-1", "新概念一", concept="对话",
               payload={"instruction": "对话别说完。"}),
        _entry("baseline:玄幻:new-2", "新概念二", concept="对话",
               payload={"instruction": "对话留半句。"}),
    ])
    r = _sync(bl)
    assert r["status"] == "failed" and r["reason"] == "entry_count", f"got {r}"
    rows, _, ver = _layer_state()
    assert set(rows) == {old["src_key"]} and ver == 1  # 旧层零变化


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


def test_未配置信任钥静默跳过(sync_env, monkeypatch):
    bl = sync_env
    monkeypatch.setattr(bl, "_trust_keys", dict)
    r = _sync(bl)
    assert r["status"] == "skipped" and r["reason"] == "not_configured"


def test_生产默认_静态托管同域与烘焙公钥(monkeypatch):
    """不另造 CDN/钥：基线走 www.awesomenovel.com 静态托管 + 提示词包 pack-k1 同一把钥。"""
    from kb import baseline as bl

    monkeypatch.delenv("CLIENT_KB_PUBKEYS", raising=False)
    monkeypatch.delenv("CLIENT_PACK_PUBKEYS", raising=False)
    monkeypatch.setattr(bl, "_TRUST_PUBKEYS", {})
    assert bl._DEFAULT_CDN_BASE == "https://www.awesomenovel.com/knowledge/baseline"
    keys = bl._trust_keys()
    assert set(keys) == {"pack-k1"}
    assert len(keys["pack-k1"]) == 32
    assert base64.b64encode(keys["pack-k1"]).decode() == "UaJFasM5PBIB3Tg1o03cjG6Opeq5CaKtPv2ooLyNPPM="
    assert "www.awesomenovel.com" in bl._trusted_hosts()


def test_烘焙公钥与打包常量同源(monkeypatch):
    """轮换漂移防线：默认钥改错一处 = 每次同步 latest_invalid（与断网无法区分）。"""
    import re
    from pathlib import Path

    from kb import baseline as bl

    src = (
        Path(__file__).resolve().parents[3]
        / "client" / "packaging" / "build" / "pywebview_app.py"
    ).read_text(encoding="utf-8")
    m = re.search(r"^PROD_PACK_PUBKEYS = '(.+)'$", src, re.MULTILINE)
    assert m, "pywebview_app.py 缺 PROD_PACK_PUBKEYS 常量"
    assert json.loads(m.group(1)) == json.loads(bl._PROD_PUBKEYS_JSON)


def test_环境钥优先于烘焙默认(monkeypatch):
    from kb import baseline as bl

    monkeypatch.setattr(bl, "_TRUST_PUBKEYS", {})
    monkeypatch.delenv("CLIENT_KB_PUBKEYS", raising=False)
    monkeypatch.setenv("CLIENT_PACK_PUBKEYS", json.dumps(
        {_TEST_KID: base64.b64encode(_TEST_PUBKEYS[_TEST_KID]).decode()}))
    keys = bl._trust_keys()
    assert keys[_TEST_KID] == _TEST_PUBKEYS[_TEST_KID]


def test_主域失败自动走兜底域(sync_env):
    """主域挂掉（DNS/超时/404）→ 兜底域取同一份签名清单，同步照常成功。"""
    bl = sync_env
    _CDN.dead = {"www.awesomenovel.com"}
    e = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [e])
    r = _sync(bl)
    assert r["status"] == "synced" and r["entries"] == 1, f"got {r}"
    rows, _, ver = _layer_state()
    assert set(rows) == {e["src_key"]} and ver == 1


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

    monkeypatch.delenv("KB_BASELINE_SYNC", raising=False)  # conftest 默认关（测试进程防抢锁）
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


def test_启动补偿_测试闸可关(monkeypatch):
    """KB_BASELINE_SYNC=0：lifespan 在测试进程里不乱联网（CI database is locked 定诊）。"""
    from kb import baseline as bl

    monkeypatch.setenv("KB_BASELINE_SYNC", "0")
    called: list[int] = []

    async def _fake():
        called.append(1)
        return {"status": "current"}

    monkeypatch.setattr(bl, "sync_baseline", _fake)

    async def _go():
        bl.schedule_sync()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    _run(_go())
    assert called == []


def test_手动同步不受测试闸影响(monkeypatch):
    """闸只挡启动补偿：sync_baseline() 显式调用照常执行（运维/重试面依赖此性质）。"""
    from kb import baseline as bl

    monkeypatch.setenv("KB_BASELINE_SYNC", "0")
    monkeypatch.setattr(bl, "_trust_keys", dict)  # 无钥＝early return，不发网络
    assert _run(bl.sync_baseline())["reason"] == "not_configured"


def test_下架孤儿edit提升为用户条目(sync_env):
    """D0-6：官方下架条目的用户副本不蒸发——提升为账号自有条目（src_kind≠baseline）。"""
    from sqlalchemy import delete

    from kb.baseline import content_sha
    from models.kb import KbEntry, KbEntryTag

    bl = sync_env
    a = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    keep = _entry("baseline:玄幻:tech-b", "玄幻手法B")
    _publish(1, [a, keep])
    assert _sync(bl)["status"] == "synced"

    uid = f"promote-{uuid.uuid4().hex[:8]}"

    async def _seed_overlay():
        async with async_session() as db:
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=a["src_key"], action="edit",
                content="我的说法：交手先让三招再还手。",
                base_content_sha256=content_sha(a["instruction"])))
            await db.commit()

    _run(_seed_overlay())

    # v2：A 官方下架（B 保留）
    _publish(2, [keep])
    r = _sync(bl)
    assert r["status"] == "synced" and r["promoted"] == 1, f"got {r}"
    assert _overlays(a["src_key"]) == {}  # 覆盖记录已消费

    async def _user_entries():
        async with async_session() as db:
            rows = (await db.execute(sel(KbEntry).where(KbEntry.user_id == uid))).scalars().all()
            tags = (await db.execute(sel(KbEntryTag).where(KbEntryTag.user_id == uid))).scalars().all()
            return rows, tags

    rows, tags = _run(_user_entries())
    assert len(rows) == 1
    e = rows[0]
    assert e.instruction == "我的说法：交手先让三招再还手。"
    assert e.concept == a["concept"] and e.genre == a["genre"]
    assert e.title == a["title"]
    assert e.src_kind == "manual"  # delta 硬约束：不得落 baseline
    assert e.src_novel_name == "官方精选（已下架）"
    assert set(e.payload_json) > {"{"} and "打斗-节奏" in e.payload_json
    assert len(tags) >= 3  # concept/scope/scene 物化
    assert any(t.dim == "scene" and t.value == "打斗" for t in tags)

    # 再同步（同版本）零写；升 v3 不重复提升
    _publish(3, [keep])
    assert _sync(bl)["status"] == "synced"
    rows2, _tags2 = _run(_user_entries())
    assert len(rows2) == 1

    # 清理提升件，避免污染共享测试库
    async def _cleanup():
        async with async_session() as db:
            await db.execute(delete(KbEntryTag).where(KbEntryTag.user_id == uid))
            await db.execute(delete(KbEntry).where(KbEntry.user_id == uid))
            await db.commit()

    _run(_cleanup())


def test_回退再上架_提升副本与复活原件不重复(sync_env):
    """P3 修复钉：下架提升后回退/再上架，官方条目不与用户副本重复显示。"""
    from sqlalchemy import delete

    from kb.baseline import content_sha
    from kb.merged import load_baseline_entries, load_hidden_entries
    from models.kb import KbEntry, KbEntryTag

    bl = sync_env
    a = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [a])
    assert _sync(bl)["status"] == "synced"

    uid = f"readd-{uuid.uuid4().hex[:8]}"

    async def _edit():
        async with async_session() as db:
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=a["src_key"], action="edit",
                content="我的说法：先让三招再还手。",
                base_content_sha256=content_sha(a["instruction"])))
            await db.commit()

    _run(_edit())

    _publish(2, [])  # 下架 → 提升
    r = _sync(bl)
    assert r["status"] == "synced" and r["promoted"] == 1, f"got {r}"

    _publish(3, [a])  # 回退/再上架
    assert _sync(bl)["status"] == "synced"

    async def _check():
        async with async_session() as db:
            visible = await load_baseline_entries(db, user_id=uid, genre="玄幻")
            hidden = await load_hidden_entries(db, user_id=uid)
            entries = (await db.execute(
                sel(KbEntry).where(KbEntry.user_id == uid))).scalars().all()
            ov = (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid))).scalars().all()
            return visible, hidden, entries, ov

    visible, hidden, entries, ov = _run(_check())
    assert [e.src_key for e in visible] == []          # 官方不重复露出
    assert [e.src_key for e in hidden] == [a["src_key"]]  # 在「已隐藏」可恢复
    assert len(entries) == 1 and entries[0].instruction.startswith("我的说法")
    assert [(o.action, o.src_key) for o in ov] == [("hide", a["src_key"])]

    # 用户手动恢复官方版后，后续版本升级不得把 auto-hide 盖回来（用户选择优先）
    async def _restore():
        async with async_session() as db:
            ov = (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid))).scalar_one()
            await db.delete(ov)
            await db.commit()

    _run(_restore())
    _publish(4, [a])
    assert _sync(bl)["status"] == "synced"

    async def _after_restore():
        async with async_session() as db:
            visible = await load_baseline_entries(db, user_id=uid, genre="玄幻")
            ov = (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid))).scalars().all()
            return [e.src_key for e in visible], ov

    visible_keys, overlays = _run(_after_restore())
    assert visible_keys == [a["src_key"]]  # 恢复后官方重新露出
    assert overlays == []                  # 升级不会重建 auto-hide

    async def _cleanup():
        async with async_session() as db:
            await db.execute(delete(KbEntryTag).where(KbEntryTag.user_id == uid))
            await db.execute(delete(KbEntry).where(KbEntry.user_id == uid))
            await db.execute(delete(KbBaselineOverlay).where(KbBaselineOverlay.user_id == uid))
            await db.commit()

    _run(_cleanup())


def test_hide带正文_下架不丢副本内容(sync_env):
    """P3 修复钉：edit→hide 保留的正文在官方下架时不得整条删除。"""
    bl = sync_env
    a = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [a])
    assert _sync(bl)["status"] == "synced"

    uid = f"hidekeep-{uuid.uuid4().hex[:8]}"

    async def _hide_with_content():
        async with async_session() as db:
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=a["src_key"], action="hide",
                content="我写过的旧副本。", base_content_sha256="h1"))
            await db.commit()

    _run(_hide_with_content())
    _publish(2, [])  # 官方下架
    assert _sync(bl)["status"] == "synced"

    async def _row():
        async with async_session() as db:
            return (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid))).scalar_one_or_none()

    row = _run(_row())
    assert row is not None and row.action == "hide"
    assert row.content == "我写过的旧副本。"


def test_再次下架_已提升副本原地更新不重复(sync_env):
    """P3 回归：提升副本已存在时再次下架，不得新建第二份（同步路径同吃幂等锁）。"""
    from sqlalchemy import delete

    from kb.baseline import content_sha
    from models.kb import KbEntry, KbEntryTag

    bl = sync_env
    a = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [a])
    assert _sync(bl)["status"] == "synced"

    uid = f"repromote-{uuid.uuid4().hex[:8]}"

    async def _overlay(text: str):
        async with async_session() as db:
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=a["src_key"], action="edit", content=text,
                base_content_sha256=content_sha(a["instruction"])))
            await db.commit()

    _run(_overlay("第一版副本：先让三招。"))
    _publish(2, [])
    assert _sync(bl)["promoted"] == 1

    _publish(3, [a])           # 再上架（会给该用户补 auto-hide）
    assert _sync(bl)["status"] == "synced"

    async def _restore_and_edit():
        async with async_session() as db:
            ov = (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid))).scalar_one()
            await db.delete(ov)
            await db.commit()
        await _overlay("第二版副本：先让五招。")   # 恢复官方后再改一次

    _run(_restore_and_edit())

    _publish(4, [])            # 再次下架：已有提升副本 → 原地更新
    r = _sync(bl)
    assert r["status"] == "synced" and r["promoted"] == 1, f"got {r}"

    async def _check():
        async with async_session() as db:
            entries = (await db.execute(sel(KbEntry).where(
                KbEntry.user_id == uid))).scalars().all()
            ovs = (await db.execute(sel(KbBaselineOverlay).where(
                KbBaselineOverlay.user_id == uid))).scalars().all()
            return entries, ovs

    entries, ovs = _run(_check())
    assert len(entries) == 1, "不得出现第二份提升副本"
    assert entries[0].instruction == "第二版副本：先让五招。"
    assert ovs == []  # 覆盖已被消费

    async def _cleanup():
        async with async_session() as db:
            await db.execute(delete(KbEntryTag).where(KbEntryTag.user_id == uid))
            await db.execute(delete(KbEntry).where(KbEntry.user_id == uid))
            await db.commit()

    _run(_cleanup())


# ── fake-ip 代理环境失败细分（c-proxy-fakeip-compat）────────────────────────


def test_fakeip环境同步失败记proxy_fake_ip(sync_env, monkeypatch):
    """TUN fake-ip（解析全落 198.18.0.0/15，放行但代理节点不通）→ 失败原因
    proxy_fake_ip，与 latest_invalid 可区分——弹窗据此呈现代理指路文案。"""
    from kb import baseline as bl

    monkeypatch.setattr(bl, "_validate_outbound", lambda url: (True, "fakeip"))
    monkeypatch.setattr(bl, "_fetch_json", _fetch_none)
    r = _run(bl.sync_baseline())
    assert r["status"] == "failed" and r["reason"] == "proxy_fake_ip"


def test_blocked解析仍记latest_invalid(sync_env, monkeypatch):
    """混合/私网解析（verdict=blocked）维持既有失败原因，行为不变。"""
    from kb import baseline as bl

    monkeypatch.setattr(bl, "_validate_outbound", lambda url: (False, "blocked"))
    monkeypatch.setattr(bl, "_fetch_json", _fetch_none)
    r = _run(bl.sync_baseline())
    assert r["status"] == "failed" and r["reason"] == "latest_invalid"
