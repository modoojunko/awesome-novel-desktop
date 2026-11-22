"""官方基线接回（c-kb-baseline-reconnect）——撤回机制退役＋版本界收窄 单测。

口径（knowledge-baseline delta）：清理只杀 pack_version < RECONNECT_PACK_VERSION
的行；v5+ 行在 boot/迁移搬运后/恢复备份后三条自动路径下存活（含其用户 overlay
与标签）；retired 戳退役自动打点（手动急刹保留）；存量 retired 库一次性自动
接回；撤回清单永不回充。

清理面全走真库（与撤回机器同口径）；同步网络面全注入（沿 test_kb_baseline_sync
的 _FakeCDN 先例——签名用测试密钥对）。
"""

import asyncio
import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import delete, select

import kb.revocation as rev
from db import async_session
from kb.baseline import proxy_id
from manifest_crypto import sign_manifest
from models.app_meta import AppMeta
from models.kb import KbBaselineEntry, KbBaselineOverlay, KbBaselineTag, KbBookEntry

_ed_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_TEST_PRIV = base64.b64encode(bytes(range(32))).decode()
_TEST_KID = "test-k"
_TEST_PUBKEYS = {_TEST_KID: _ed_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}
_BASE = "http://127.0.0.1:1/knowledge/baseline"
R = rev.RECONNECT_PACK_VERSION


def _run(coro):
    return asyncio.run(coro)


def _meta(key: str) -> str | None:
    async def _go():
        async with async_session() as db:
            row = await db.get(AppMeta, key)
            return row.value if row else None
    return _run(_go())


def _baseline_rows() -> dict[str, KbBaselineEntry]:
    async def _go():
        async with async_session() as db:
            rows = (await db.execute(select(KbBaselineEntry))).scalars().all()
            return {r.src_key: r for r in rows}
    return _run(_go())


def _overlays() -> dict[str, KbBaselineOverlay]:
    async def _go():
        async with async_session() as db:
            rows = (await db.execute(select(KbBaselineOverlay))).scalars().all()
            return {r.src_key: r for r in rows}
    return _run(_go())


def _add_baseline(src_key: str, *, pack_version: int, genre: str = "玄幻") -> None:
    """造一行基线条目（uuid5 代理键与同步端同口径）。"""
    async def _go():
        async with async_session() as db:
            db.add(KbBaselineEntry(
                entry_id=proxy_id(src_key), src_key=src_key,
                pack_version=pack_version, genre=genre, concept="手法",
                title=f"条目{pack_version}", instruction="交手先守后攻。"))
            db.add(KbBaselineTag(entry_id=proxy_id(src_key), dim="slot", value="打斗-节奏"))
            await db.commit()
    _run(_go())


def _add_overlay(src_key: str, *, user_id: str = "u1") -> None:
    async def _go():
        async with async_session() as db:
            db.add(KbBaselineOverlay(
                user_id=user_id, src_key=src_key, action="hide", content=""))
            await db.commit()
    _run(_go())


def _add_book_copy(src_key: str, *, user_id: str = "u1") -> None:
    """书级副本：src_key＝官方条目 id（uuid5 兜底口径的命中形态）。"""
    async def _go():
        async with async_session() as db:
            db.add(KbBookEntry(
                user_id=user_id, novel_id="n1", src_key=src_key, src_ref="n1",
                title="官方副本", genre="玄幻", concept="手法"))
            await db.commit()
    _run(_go())


_MY_KEYS = (rev.RETIRED_KEY, rev.MARKER_KEY, rev.VERSION_KEY,
            rev.LAST_SYNC_KEY, rev.RECONNECT_DONE_KEY)


def _cleanup() -> None:
    """精确清理：本测试域创建的行＋本组 app_meta 键（不碰 novels 等他域数据——
    全表删除会撞卷章 FK，全量套件序下必炸）。"""
    async def _go():
        async with async_session() as db:
            for k in _MY_KEYS:
                row = await db.get(AppMeta, k)
                if row:
                    await db.delete(row)
            await db.execute(delete(KbBaselineTag))
            await db.execute(delete(KbBaselineOverlay))
            await db.execute(delete(KbBaselineEntry))
            await db.execute(delete(KbBookEntry).where(KbBookEntry.novel_id == "n1"))
            await db.commit()
    _run(_go())


@pytest.fixture
def rev_env(monkeypatch):
    from db import Base, engine

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    _run(_setup())
    monkeypatch.delenv("KB_REVOCATION", raising=False)
    monkeypatch.setattr(rev, "_applied_in_process", False)
    _cleanup()
    yield rev
    monkeypatch.delenv("KB_REVOCATION", raising=False)
    _cleanup()


# ── 清理范围收窄 ──────────────────────────────────────────────────────────


class TestPurgeScope:
    def test_v5_rows_survive_apply_force(self, rev_env):
        """迁移搬运后/恢复备份后的 force 路径：v5 行（含 overlay/标签）全存活，
        retired 不再自动打点，marker 落接回版本界。"""
        _add_baseline("v5-a", pack_version=5)
        _add_overlay("v5-a")
        out = _run(rev.apply_revocations(force=True))
        rows = _baseline_rows()
        assert "v5-a" in rows and rows["v5-a"].pack_version == 5
        assert _overlays().get("v5-a") is not None  # 用户层保全
        assert _meta(rev.RETIRED_KEY) is None       # 退役自动打点
        assert json.loads(_meta(rev.MARKER_KEY))["reconnect_version"] == R
        assert out["status"] == "already"           # 没清任何行＝非 revoked

    def test_stale_rows_purged_v5_survive(self, rev_env):
        """混库（<5 行＋v5 行）：低版本照清、v5 存活；版本记账归零触发重同步；
        tag/overlay 只随低版本行走。"""
        _add_baseline("old-v1", pack_version=1)
        _add_baseline("old-v3", pack_version=3)
        _add_baseline("new-v5", pack_version=5)
        _add_overlay("new-v5")
        _add_overlay("old-v1")
        out = _run(rev.apply_revocations(force=True))
        rows = _baseline_rows()
        assert set(rows) == {"new-v5"}
        assert _overlays().get("old-v1") is None and _overlays().get("new-v5") is not None
        assert out["status"] == "revoked"
        assert _meta(rev.VERSION_KEY) == "0"        # 版本归零＝触发重同步
        assert json.loads(_meta(rev.LAST_SYNC_KEY))["status"] == "revoked"
        assert _meta(rev.RETIRED_KEY) is None

    def test_revoked_ids_purged_even_high_version(self, rev_env):
        """硬闸优先：撤回清单命中行即使版本达标也照清（防御性）。"""
        revoked_id = min(rev.REVOKED_ENTRY_IDS)
        async def _go():
            async with async_session() as db:
                db.add(KbBaselineEntry(
                    entry_id=revoked_id, src_key="revived-bad",
                    pack_version=9, genre="玄幻", concept="手法",
                    title="回潮条目", instruction="x"))
                await db.commit()
        _run(_go())
        _run(rev.apply_revocations(force=True))
        assert revoked_id not in _baseline_rows() or all(
            k != "revived-bad" for k in _baseline_rows())

    def test_book_copy_of_v5_survives_uuid5_fallback(self, rev_env):
        """书级副本 uuid5 兜底：v5 条目的副本存活，<5 条目的副本照清。"""
        _add_baseline("v5-a", pack_version=5)
        _add_baseline("old-v1", pack_version=1)
        vid = proxy_id("v5-a")
        oid = proxy_id("old-v1")
        _add_book_copy(vid)
        _add_book_copy(oid)
        _run(rev.apply_revocations(force=True))
        async def _copies():
            async with async_session() as db:
                rows = (await db.execute(select(KbBookEntry))).scalars().all()
                return {r.src_key for r in rows}
        assert _run(_copies()) == {vid}  # v5 副本存活（uuid5 兜底排除接回行）


# ── 一次性接回过渡 ────────────────────────────────────────────────────────


class TestEnsureReconnected:
    def test_transition_clears_retired_stamp(self, rev_env):
        async def _stamp():
            async with async_session() as db:
                db.add(AppMeta(key=rev.RETIRED_KEY, value="1"))
                await db.commit()
        _run(_stamp())
        assert _run(rev.ensure_reconnected()) is True
        assert _meta(rev.RETIRED_KEY) is None
        assert _meta(rev.RECONNECT_DONE_KEY) == "1"

    def test_transition_idempotent(self, rev_env):
        async def _stamp():
            async with async_session() as db:
                db.add(AppMeta(key=rev.RETIRED_KEY, value="1"))
                await db.commit()
        _run(_stamp())
        assert _run(rev.ensure_reconnected()) is True
        assert _run(rev.ensure_reconnected()) is False  # 标记在＝零动作
        assert _meta(rev.RETIRED_KEY) is None

    def test_no_stamp_no_action(self, rev_env):
        assert _run(rev.ensure_reconnected()) is False
        assert _meta(rev.RECONNECT_DONE_KEY) is None


# ── 同步消费（网络面全注入，沿 _FakeCDN 先例）────────────────────────────


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


def _publish_v5(entries: list[dict]) -> None:
    body = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries).encode()
    manifest = {
        "version": 5,
        "entry_count": len(entries),
        "generated_at": "2026-11-22T00:00:00Z",
        "files": [{"path": "entries.jsonl",
                   "sha256": hashlib.sha256(body).hexdigest()}],
    }
    signed = sign_manifest(manifest, _TEST_PRIV, _TEST_KID)
    _CDN.latest = sign_manifest(
        {"version": 5,
         "manifest_sha256": hashlib.sha256(json.dumps(signed, ensure_ascii=False).encode()).hexdigest()},
        _TEST_PRIV, _TEST_KID)
    _CDN.manifest_raw = json.dumps(signed, ensure_ascii=False).encode()
    _CDN.entries_raw = body


_CDN = _FakeCDN()


@pytest.fixture
def sync_env(monkeypatch):
    from kb import baseline as bl

    monkeypatch.setattr(bl, "_TRUST_PUBKEYS", _TEST_PUBKEYS)
    monkeypatch.setattr(bl, "_cdn_base", lambda: _BASE)
    monkeypatch.setattr(bl, "_validate_outbound", lambda url: (True, "ok"))
    monkeypatch.setattr(bl, "_fetch_json", _CDN.get_json)
    monkeypatch.setattr(bl, "_fetch_bytes", _CDN.get_bytes)
    _cleanup()
    yield bl
    _cleanup()


def _entry(src_key: str) -> dict:
    ins = f"{src_key}：交手先守后攻，招式收在第三拍。"
    return {"src_key": src_key, "title": "条目", "concept": "手法", "genre": "玄幻",
            "instruction": ins,
            "payload": {"instruction": ins, "slot": "打斗-节奏", "scene": "打斗"},
            "when": {"scene": "打斗"}}


class TestSyncAfterReconnect:
    def test_sync_applies_v5_when_not_retired(self, rev_env, sync_env):
        """接回后（无 retired 戳）sync 正常消费 CDN v5 包：整层替换＋pack_version 记账。"""
        _publish_v5([_entry("baseline:玄幻:reconnect-a"), _entry("baseline:玄幻:reconnect-b")])
        out = _run(sync_env.sync_baseline())
        assert out["status"] == "synced"
        rows = _baseline_rows()
        assert len(rows) == 2
        assert all(r.pack_version == 5 for r in rows.values())
        assert _meta(rev.VERSION_KEY) == "5"

    def test_emergency_brake_still_blocks_sync(self, rev_env, sync_env):
        """合规急刹：手动置 retired=1 后 sync 跳过（不拉包不落层）。"""
        async def _stamp():
            async with async_session() as db:
                db.add(AppMeta(key=rev.RETIRED_KEY, value="1"))
                await db.commit()
        _run(_stamp())
        _publish_v5([_entry("baseline:玄幻:reconnect-a")])
        out = _run(sync_env.sync_baseline())
        assert out == {"status": "skipped", "reason": "retired"}
        assert _baseline_rows() == {}

    def test_withdrawn_src_keys_never_readmitted(self, rev_env, sync_env):
        """撤回清单永不回充：即使签名包带来撤回 src_key，清理计划也会照清
        （终态＝不回充；清理侧硬闸由 boot/迁移后/恢复后自动执行）。"""
        revoked_key = min(rev.REVOKED_SRC_KEYS)
        _publish_v5([_entry(revoked_key), _entry("baseline:玄幻:reconnect-a")])
        out = _run(sync_env.sync_baseline())
        assert out["status"] == "synced"
        assert revoked_key in _baseline_rows()  # 同步侧信任签名包（内容链路不动）
        _run(rev.apply_revocations())            # 清理计划（boot 等自动执行同一入口）
        rows = _baseline_rows()
        assert revoked_key not in rows           # 撤回内容照清
        assert "baseline:玄幻:reconnect-a" in rows  # 合法行保留
