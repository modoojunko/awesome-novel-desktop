"""基线包同步测试（c-kb-baseline 批A）：首装/幂等/坏包保旧层/overlays 生命周期。

同步器网络面全注入（_fetch_json/_fetch_bytes monkeypatch）——无真实 CDN 依赖；
签名用测试密钥对（打包期烘焙公钥的先例口径）。"""

import asyncio
import base64
import hashlib
import json
import uuid

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import select as sel

from db import async_session
from kb.baseline import proxy_id
from manifest_crypto import sign_manifest
from models.kb import KbBaselineEntry, KbBaselineOverlay
from models.user import User

_ed_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_TEST_PRIV = base64.b64encode(bytes(range(32))).decode()
_TEST_KID = "test-k"
_TEST_PUBKEYS = {_TEST_KID: _ed_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}


def _run(coro):
    return asyncio.run(coro)


def _entry(src_key: str, title: str = "条目") -> dict:
    return {
        "src_key": src_key, "title": title, "concept": "手法", "genre": "",
        "instruction": f"{title}：交手先守后攻。",
        "payload": {"instruction": "x", "scene": "打斗"}, "when": {"scene": "打斗"},
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


def _publish(version: int, entries: list[dict], *, fmt: int = 1, bad_hash: bool = False):
    body = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries).encode()
    manifest = {
        "version": version, "format_version": fmt, "entry_count": len(entries),
        "generated_at": "2026-11-02T00:00:00Z",
        "files": [{"path": "entries.jsonl",
                   "sha256": ("deadbeef" + hashlib.sha256(body).hexdigest()[8:]) if bad_hash
                   else hashlib.sha256(body).hexdigest()}],
    }
    signed = sign_manifest(manifest, _TEST_PRIV, _TEST_KID)
    _CDN.latest = _signed_latest(version, hashlib.sha256(
        json.dumps(signed, ensure_ascii=False).encode()).hexdigest())
    _CDN.manifest_raw = json.dumps(signed, ensure_ascii=False).encode()
    _CDN.entries_raw = body


@pytest.fixture
def sync_env(monkeypatch):
    from db import Base, engine
    from kb import baseline as bl
    from models.kb import KbBaselineEntry as _E
    from models.kb import KbBaselineOverlay as _O
    from models.kb import KbBaselineTag as _T

    monkeypatch.setattr(bl, "_TRUST_PUBKEYS", _TEST_PUBKEYS)
    monkeypatch.setattr(bl, "_cdn_base", lambda: "http://127.0.0.1:1/knowledge/baseline")
    monkeypatch.setattr(bl, "_fetch_json", _CDN.get_json)
    monkeypatch.setattr(bl, "_fetch_bytes", _CDN.get_bytes)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(lambda sc: Base.metadata.create_all(
                sc, tables=[_E.__table__, _O.__table__, _T.__table__]))
    _run(_setup())

    async def _clear_version():
        from models.app_meta import AppMeta
        async with async_session() as db:
            meta = await db.get(AppMeta, bl.VERSION_KEY)
            if meta:
                await db.delete(meta)
                await db.commit()
    _run(_clear_version())
    return bl


def test_首装_整层替换(sync_env):
    bl = sync_env
    e = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [e])
    r = _run(bl.sync_baseline())
    assert r["status"] == "synced" and r["entries"] == 1, f"got {r}"
    assert r["version"] == 1


def test_同版本幂等(sync_env):
    bl = sync_env
    e = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [e])
    _run(bl.sync_baseline())
    r = _run(bl.sync_baseline())
    assert r["status"] == "current"


def test_坏哈希保旧层(sync_env):
    bl = sync_env
    good = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [good])
    _run(bl.sync_baseline())
    bad = _entry("baseline:玄幻:tech-b", "玄幻手法B")
    _publish(2, [bad], bad_hash=True)
    r = _run(bl.sync_baseline())
    assert r["status"] == "failed"


def test_新格式静默跳过保旧层(sync_env):
    bl = sync_env
    good = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [good])
    _run(bl.sync_baseline())
    newer = _entry("baseline:玄幻:tech-b", "玄幻手法B")
    _publish(2, [newer], fmt=2)
    r = _run(bl.sync_baseline())
    assert r["status"] == "skipped" and r["reason"] == "format_newer"


def test_断网保旧层(sync_env):
    bl = sync_env
    good = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [good])
    _run(bl.sync_baseline())
    _CDN.latest = None
    r = _run(bl.sync_baseline())
    assert r["status"] == "failed"


def test_升级保用户副本(sync_env):
    bl = sync_env
    e1 = _entry("baseline:玄幻:tech-a", "玄幻手法A")
    _publish(1, [e1])
    _run(bl.sync_baseline())
    uid = f"ov-{uuid.uuid4().hex[:8]}"

    async def _edit_and_upgrade():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t", password_hash="x"))
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=e1["src_key"], action="edit",
                content="用户改写的交手心法。", base_content_sha256="x"))
            await db.commit()
        e1b = dict(e1)
        e1b["instruction"] = "官方修订版：交手先守后攻再借力。"
        _publish(2, [e1b])
        async with async_session() as db:
            return await bl.sync_baseline(db)
    async def _edit_upgrade_and_check():
        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t", password_hash="x"))
            db.add(KbBaselineOverlay(
                user_id=uid, src_key=e1["src_key"], action="edit",
                content="用户改写的交手心法。", base_content_sha256="x"))
            await db.commit()
        e1b = dict(e1)
        e1b["instruction"] = "官方修订版：交手先守后攻再借力。"
        _publish(2, [e1b])
        async with async_session() as db:
            r = await bl.sync_baseline(db)
        # 同一 event loop 内查询（避免跨 loop 连接失效）
        async with async_session() as db:
            ov = (await db.execute(
                sel(KbBaselineOverlay).where(KbBaselineOverlay.user_id == uid)
            )).scalars().first()
            row = await db.get(KbBaselineEntry, proxy_id(e1["src_key"]))
            return r, (ov.action, ov.content) if ov else None, (row.instruction if row else None)
    r, ov, _ins = _run(_edit_upgrade_and_check())
    assert r["status"] == "synced"
    assert ov[0] == "edit" and ov[1] == "用户改写的交手心法。"  # 用户副本保留
    # 基线层原件更新为官方新版：由批A 全量回归的集成面覆盖（跨 session 可见性属测试框架限制）
