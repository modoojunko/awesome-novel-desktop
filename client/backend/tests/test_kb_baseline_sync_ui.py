"""基线更新探测与触达测试（c-kb-baseline-update-ux）：probe 三态＋maybe_sync 补装钩子。

网络面全注入（照 test_kb_baseline_sync.py 同款 FakeCDN/签名工具模式）；
maybe_sync 走 asyncio 驱动器让 create_task 任务体真跑完再断言。
"""

import asyncio
import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import delete
from sqlalchemy import select as sel

from db import async_session, engine
from manifest_crypto import sign_manifest
from models.app_meta import AppMeta
from models.kb import KbBaselineEntry

_ed_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_TEST_PRIV = base64.b64encode(bytes(range(32))).decode()
_TEST_KID = "test-k"
_TEST_PUBKEYS = {_TEST_KID: _ed_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}
_BASE = "http://127.0.0.1:1/knowledge/baseline"


def _entry(src_key: str) -> dict:
    ins = f"{src_key}：交手先守后攻，招式收在第三拍。"
    return {
        "src_key": src_key, "title": src_key, "concept": "手法", "genre": "玄幻",
        "instruction": ins,
        "payload": {"instruction": ins, "slot": "打斗-节奏", "scene": "打斗"},
        "when": {"scene": "打斗"},
    }


class _FakeCDN:
    def __init__(self):
        self.latest = None
        self.hits: list[str] = []

    async def get_json(self, client=None, url="", **kw):
        self.hits.append(url)
        return self.latest if url.endswith("latest.json") else None

    async def get_bytes(self, client=None, url="", **kw):
        return None


_CDN = _FakeCDN()


def _publish(version: int, entries: list[dict]):
    body = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries).encode()
    manifest = {
        "version": version, "entry_count": len(entries),
        "generated_at": "2026-11-02T00:00:00Z",
        "files": [{"path": "entries.jsonl", "sha256": hashlib.sha256(body).hexdigest()}],
    }
    signed = sign_manifest(manifest, _TEST_PRIV, _TEST_KID)
    _CDN.latest = sign_manifest(
        {"version": version,
         "manifest_sha256": hashlib.sha256(json.dumps(signed, ensure_ascii=False).encode()).hexdigest()},
        _TEST_PRIV, _TEST_KID,
    )
    # entries 面由兄弟测试的注入负责；本文件只测 probe/maybe_sync（不拉包体），
    # 但 maybe_sync 触发的全量同步会走 _fetch_bytes——直接给它一份对得上的包体。
    async def _fake_bytes(client=None, url="", **kw):
        if url.endswith("entries.jsonl"):
            return body
        if url.endswith("tombstones.json"):
            return b'{"removed": []}'
        if url.endswith("manifest.json"):
            return json.dumps(signed, ensure_ascii=False).encode()
        return None

    _FAKE_BYTES_HOLDER["fn"] = _fake_bytes


_FAKE_BYTES_HOLDER: dict = {"fn": None}


@pytest.fixture
def sync_env(monkeypatch):
    from kb import baseline as bl

    monkeypatch.setattr(bl, "_TRUST_PUBKEYS", _TEST_PUBKEYS)
    monkeypatch.setattr(bl, "_cdn_base", lambda: _BASE)
    monkeypatch.setattr(bl, "_cdn_bases", lambda: [_BASE])
    monkeypatch.setattr(bl, "_validate_outbound", lambda url: (True, "ok"))
    monkeypatch.setattr(bl, "_fetch_json", _CDN.get_json)
    monkeypatch.setattr(bl, "_fetch_bytes", lambda *a, **kw: _FAKE_BYTES_HOLDER["fn"](*a, **kw))

    from db import Base as _B
    from models.kb import KbBaselineEntry as _E
    from models.kb import KbBaselineOverlay as _O
    from models.kb import KbBaselineTag as _T

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(lambda sc: _B.metadata.create_all(
                sc, tables=[_E.__table__, _O.__table__, _T.__table__]))

    asyncio.run(_setup())

    def _reset():
        async def _go():
            async with async_session() as db:
                await db.execute(delete(_T))
                await db.execute(delete(_E))
                await db.execute(delete(_O))
                meta = await db.get(AppMeta, bl.VERSION_KEY)
                if meta:
                    await db.delete(meta)
                await db.commit()

        asyncio.run(_go())

    _reset()
    _CDN.hits.clear()
    yield bl
    _reset()


def _sync(bl, version: int, entries: list[dict]):
    _publish(version, entries)
    return asyncio.run(bl.sync_baseline())


def _drive_maybe_sync(bl) -> None:
    """同步上下文里触发 maybe_sync 并等 create_task 的任务体跑完。"""
    async def _go():
        bl.maybe_sync()
        for _ in range(50):
            await asyncio.sleep(0.01)

    asyncio.run(_go())


def _layer_count() -> int:
    async def _go():
        async with async_session() as db:
            return len((await db.execute(sel(KbBaselineEntry))).scalars().all())

    return asyncio.run(_go())


# ─── probe_latest：三态 ───────────────────────────────────────────────


def test_probe_同版_不可更新(sync_env):
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    r = asyncio.run(sync_env.probe_latest())
    assert r == {"installed": 1, "latest": 1, "update_available": False}


def test_probe_新版_可更新(sync_env):
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _publish(2, [_entry("baseline:玄幻:a"), _entry("baseline:玄幻:b")])
    r = asyncio.run(sync_env.probe_latest())
    assert r == {"installed": 1, "latest": 2, "update_available": True}


def test_probe_CDN不可达_不可更新带原因(sync_env):
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _CDN.latest = None
    r = asyncio.run(sync_env.probe_latest())
    assert r["update_available"] is False
    assert r["reason"] == "latest_invalid"
    assert r["installed"] == 1


def test_probe_验签失败_不可更新(sync_env):
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _CDN.latest = {"version": 2}  # 未签名
    r = asyncio.run(sync_env.probe_latest())
    assert r["update_available"] is False
    assert r["reason"] == "latest_invalid"


def test_probe_未配置信任钥_静默(sync_env, monkeypatch):
    monkeypatch.setattr(sync_env, "_trust_keys", dict)
    r = asyncio.run(sync_env.probe_latest())
    assert r["update_available"] is False
    assert r["reason"] == "not_configured"


# ─── maybe_sync：补装钩子 ─────────────────────────────────────────────


def test_maybe_sync_层空_触发补装(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")  # conftest 默认 0，这里开闸
    _publish(1, [_entry("baseline:玄幻:a")])
    assert _layer_count() == 0
    _drive_maybe_sync(sync_env)
    assert _layer_count() == 1


def test_maybe_sync_已装_零外呼(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    assert _layer_count() == 1
    _CDN.hits.clear()
    _drive_maybe_sync(sync_env)
    assert _CDN.hits == []  # 已装早退：不发任何网络请求


def test_maybe_sync_测试闸_短路(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "0")
    _publish(1, [_entry("baseline:玄幻:a")])
    _CDN.hits.clear()
    _drive_maybe_sync(sync_env)
    assert _CDN.hits == [] and _layer_count() == 0


# ─── 会话内周期复查（c-kb-baseline-periodic-recheck） ──────────────────


def test_周期复查_失败缩短间隔其余常规(sync_env):
    assert sync_env._next_recheck_delay({"status": "failed"}) == sync_env.RECHECK_RETRY_INTERVAL
    for status in ("synced", "current", "skipped"):
        assert sync_env._next_recheck_delay({"status": status}) == sync_env.RECHECK_INTERVAL


def test_周期复查_测试闸短路不挂任务(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "0")
    monkeypatch.setattr(sync_env, "_recheck_task", None)

    async def _go():
        sync_env.schedule_periodic_recheck()
        assert sync_env._recheck_task is None

    asyncio.run(_go())


def test_周期复查_重复挂接单实例(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")
    monkeypatch.setattr(sync_env, "_recheck_task", None)

    async def _go():
        sync_env.schedule_periodic_recheck()
        first = sync_env._recheck_task
        assert first is not None
        sync_env.schedule_periodic_recheck()
        assert sync_env._recheck_task is first  # 不叠加第二个任务
        first.cancel()

    asyncio.run(_go())


def test_周期复查_到点自动同步新版(sync_env, monkeypatch):
    """常驻期间无需重启/开知识库页：到点自己把 CDN 新版落层。"""
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")
    monkeypatch.setattr(sync_env, "_recheck_task", None)
    monkeypatch.setattr(sync_env, "RECHECK_INTERVAL", 0.05)
    monkeypatch.setattr(sync_env, "RECHECK_RETRY_INTERVAL", 0.05)
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _publish(2, [_entry("baseline:玄幻:a"), _entry("baseline:玄幻:b")])

    async def _go():
        async def _count():
            async with async_session() as db:
                return len((await db.execute(sel(KbBaselineEntry))).scalars().all())

        sync_env.schedule_periodic_recheck()
        for _ in range(80):
            await asyncio.sleep(0.02)
            if await _count() == 2:
                break
        sync_env._recheck_task.cancel()
        assert await _count() == 2

    asyncio.run(_go())


def test_周期复查_失败保持旧层并继续重试(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")
    monkeypatch.setattr(sync_env, "_recheck_task", None)
    monkeypatch.setattr(sync_env, "RECHECK_INTERVAL", 0.05)
    monkeypatch.setattr(sync_env, "RECHECK_RETRY_INTERVAL", 0.05)
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _CDN.latest = None  # 下一跳必失败

    async def _go():
        async def _count():
            async with async_session() as db:
                return len((await db.execute(sel(KbBaselineEntry))).scalars().all())

        sync_env.schedule_periodic_recheck()
        await asyncio.sleep(0.12)  # 至少一跳失败
        assert await _count() == 1  # 失败保持旧层
        _publish(2, [_entry("baseline:玄幻:a"), _entry("baseline:玄幻:b")])
        for _ in range(80):
            await asyncio.sleep(0.02)
            if await _count() == 2:
                break
        sync_env._recheck_task.cancel()
        assert await _count() == 2  # 短间隔重试把新版追了回来

    asyncio.run(_go())


def test_lifespan_挂载周期复查():
    """源级钉（轻量）：启动补偿之后并排挂会话内周期复查。"""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "from kb.baseline import schedule_periodic_recheck" in src
    assert src.index("schedule_sync()") < src.index("schedule_periodic_recheck()")


# ─── 登录钩子挂点（源级钉：挂载在 browser_auth 成功段） ────────────────


def test_browser_auth_成功段挂基线补装钩子():
    """源级钉（轻量）：maybe_after_auth 之后并排挂 kb.baseline.maybe_sync。"""
    import inspect

    from auth_local import service

    src = inspect.getsource(service.browser_auth)
    assert "from kb.baseline import maybe_sync" in src
    assert "maybe_sync()" in src
    # 顺序：挂在提示词包钩子之后（同款 try/except S110 不阻塞登录）
    assert src.index("maybe_after_auth()") < src.index("maybe_sync()")


# ─── probe 端点（router 装配） ────────────────────────────────────────


def test_probe_端点_信封与只读():
    import inspect

    from kb import router

    src = inspect.getsource(router)
    assert '@router.get("/baseline/probe")' in src
    # 只读探测：端点体只调 probe_latest，不触发 sync_baseline
    fn = router.baseline_probe_api
    body = inspect.getsource(fn)
    assert "probe_latest" in body and "sync_baseline" not in body
