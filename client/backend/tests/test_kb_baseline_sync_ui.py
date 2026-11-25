"""基线探测与触达测试（s-kb-signed-delivery）：probe 三态＋登录/周期只探测不下载。

网络面全注入（server_api.sign/fetch_signed monkeypatch）；题材下载由用户手动触发，
登录钩子/周期复查只做免费探测——不静默扣每日题材配额。
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
from kb import server_api
from manifest_crypto import sign_manifest
from models.app_meta import AppMeta
from models.kb import KbBaselineEntry

_ed_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_TEST_PRIV = base64.b64encode(bytes(range(32))).decode()
_TEST_KID = "test-k"
_TEST_PUBKEYS = {_TEST_KID: _ed_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}


def _entry(src_key: str) -> dict:
    ins = f"{src_key}：交手先守后攻，招式收在第三拍。"
    return {
        "src_key": src_key, "title": src_key, "concept": "手法", "genre": "玄幻",
        "instruction": ins,
        "payload": {"instruction": ins, "slot": "打斗-节奏", "scene": "打斗"},
        "when": {"scene": "打斗"},
    }


class _FakeServer:
    def __init__(self):
        self.latest = None
        self.manifest_raw = b"{}"
        self.files: dict[str, bytes] = {}
        self.hits: list[str] = []
        self.dead = False
        self.verdict = "ok"

    def reset(self):
        self.latest = None
        self.manifest_raw = b"{}"
        self.files = {}
        self.hits = []
        self.dead = False
        self.verdict = "ok"

    async def sign(self, scope, *, version=None, path="", genre=""):
        self.hits.append(scope)
        if self.dead:
            return {"code": -1, "msg": "unreachable"}
        return {
            "code": 0,
            "data": {
                "url": f"fake://{scope}/{version or 0}/{path}",
                "quota": {"limit": 2, "used": 0, "remaining": 2},
            },
        }

    async def fetch_signed(self, url, max_bytes):
        self.hits.append(url)
        if self.dead:
            return None, self.verdict
        if self.verdict != "ok":
            return None, self.verdict
        if "baseline_pointer" in url:
            if self.latest is None:
                return None, "ok"
            return json.dumps(self.latest).encode(), "ok"
        if "baseline_manifest" in url:
            return self.manifest_raw, "ok"
        if "baseline_genre" in url:
            for path, data in self.files.items():
                if path in url:
                    return data, "ok"
        return None, "ok"


_CDN = _FakeServer()


def _publish(version: int, entries: list[dict], genre: str = "玄幻"):
    body = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries).encode()
    rel = f"genres/{hashlib.sha1(genre.encode()).hexdigest()[:16]}.jsonl"
    manifest = {
        "version": version,
        "entry_count": len(entries),
        "generated_at": "2026-11-02T00:00:00Z",
        "genres": {
            genre: {
                "path": rel,
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "entry_count": len(entries),
            }
        },
    }
    signed = sign_manifest(manifest, _TEST_PRIV, _TEST_KID)
    _CDN.latest = sign_manifest(
        {
            "version": version,
            "manifest_sha256": hashlib.sha256(
                json.dumps(signed, ensure_ascii=False).encode()
            ).hexdigest(),
            "resume_baseline": False,
        },
        _TEST_PRIV,
        _TEST_KID,
    )
    _CDN.manifest_raw = json.dumps(signed, ensure_ascii=False).encode()
    _CDN.files = {rel: body}


@pytest.fixture
def sync_env(monkeypatch):
    from kb import baseline as bl

    monkeypatch.setattr(bl, "_TRUST_PUBKEYS", _TEST_PUBKEYS)
    monkeypatch.setattr(server_api, "sign", _CDN.sign)
    monkeypatch.setattr(server_api, "fetch_signed", _CDN.fetch_signed)

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
                for key in (bl.VERSION_KEY, bl.GENRES_KEY, bl.LAST_SYNC_KEY):
                    meta = await db.get(AppMeta, key)
                    if meta:
                        await db.delete(meta)
                await db.commit()

        asyncio.run(_go())

    _CDN.reset()
    _reset()
    yield bl
    _CDN.reset()
    _reset()


def _sync(bl, version: int, entries: list[dict]):
    _publish(version, entries)
    return asyncio.run(bl.sync_genre("玄幻"))


def _drive_maybe_sync(bl) -> None:
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


def _hits(*needles: str) -> list[str]:
    return [h for h in _CDN.hits if any(n in h for n in needles)]


# ─── probe_latest：三态 ───────────────────────────────────────────────


def test_probe_同版_不可更新(sync_env):
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    r = asyncio.run(sync_env.probe_latest())
    assert r["installed"] == 1 and r["latest"] == 1
    assert r["update_available"] is False
    assert r["installed_genres"]["玄幻"]["version"] == 1
    assert r["quota"]["limit"] == 2


def test_probe_新版_可更新(sync_env):
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _publish(2, [_entry("baseline:玄幻:a"), _entry("baseline:玄幻:b")])
    r = asyncio.run(sync_env.probe_latest())
    assert r["installed"] == 1 and r["latest"] == 2
    assert r["update_available"] is True
    assert r["updates"] == ["玄幻"]


def test_probe_S端不可达_不可更新带原因(sync_env):
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _CDN.latest = None
    r = asyncio.run(sync_env.probe_latest())
    assert r["update_available"] is False
    assert r["reason"] == "pointer_fetch"
    assert r["installed"] == 1


def test_probe_验签失败_不可更新(sync_env):
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _CDN.latest = {"version": 2}  # 未签名
    r = asyncio.run(sync_env.probe_latest())
    assert r["update_available"] is False
    assert r["reason"] == "pointer_invalid"


def test_probe_未配置信任钥_静默(sync_env, monkeypatch):
    monkeypatch.setattr(sync_env, "_trust_keys", dict)
    r = asyncio.run(sync_env.probe_latest())
    assert r["update_available"] is False
    assert r["reason"] == "not_configured"


# ─── maybe_sync：登录钩子只探测，不静默下载 ───────────────────────────


def test_maybe_sync_层空_只探测不下载(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")
    _publish(1, [_entry("baseline:玄幻:a")])
    assert _layer_count() == 0
    _CDN.hits.clear()
    _drive_maybe_sync(sync_env)
    assert _layer_count() == 0, "登录钩子不得静默下载题材"
    assert _hits("baseline_pointer"), "应做免费指针探测"
    assert _hits("baseline_genre") == []


def test_maybe_sync_已装_仍只探测(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    assert _layer_count() == 1
    _CDN.hits.clear()
    _drive_maybe_sync(sync_env)
    assert _layer_count() == 1
    assert _hits("baseline_pointer")
    assert _hits("baseline_genre") == []


def test_maybe_sync_测试闸_短路(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "0")
    _publish(1, [_entry("baseline:玄幻:a")])
    _CDN.hits.clear()
    _drive_maybe_sync(sync_env)
    assert _CDN.hits == [] and _layer_count() == 0


# ─── 会话内周期复查：只探测（免费），不自动下载 ────────────────────────


def test_周期复查_失败缩短间隔其余常规(sync_env):
    assert sync_env._next_recheck_delay({"status": "failed"}) == sync_env.RECHECK_RETRY_INTERVAL
    for status in ("probed", "skipped", "current"):
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


def test_周期复查_到点只探测不下载(sync_env, monkeypatch):
    """常驻期间到点只刷指针（免费）；题材仍由用户手动同步。"""
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")
    monkeypatch.setattr(sync_env, "_recheck_task", None)
    monkeypatch.setattr(sync_env, "RECHECK_INTERVAL", 0.05)
    monkeypatch.setattr(sync_env, "RECHECK_RETRY_INTERVAL", 0.05)
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _publish(2, [_entry("baseline:玄幻:a"), _entry("baseline:玄幻:b")])
    _CDN.hits.clear()

    async def _go():
        async def _count():
            async with async_session() as db:
                return len((await db.execute(sel(KbBaselineEntry))).scalars().all())

        sync_env.schedule_periodic_recheck()
        await asyncio.sleep(0.2)
        sync_env._recheck_task.cancel()
        assert await _count() == 1, "周期复查不得自动下载题材"
        assert _hits("baseline_pointer"), "应做免费指针探测"
        assert _hits("baseline_genre") == []

    asyncio.run(_go())


def test_周期复查_失败保持旧层并继续重试(sync_env, monkeypatch):
    monkeypatch.setenv("KB_BASELINE_SYNC", "1")
    monkeypatch.setattr(sync_env, "_recheck_task", None)
    monkeypatch.setattr(sync_env, "RECHECK_INTERVAL", 0.05)
    monkeypatch.setattr(sync_env, "RECHECK_RETRY_INTERVAL", 0.05)
    _sync(sync_env, 1, [_entry("baseline:玄幻:a")])
    _CDN.latest = None  # 下一跳必失败
    _CDN.hits.clear()

    async def _go():
        async def _count():
            async with async_session() as db:
                return len((await db.execute(sel(KbBaselineEntry))).scalars().all())

        sync_env.schedule_periodic_recheck()
        await asyncio.sleep(0.2)
        assert await _count() == 1  # 失败保持旧层
        assert len(_hits("baseline_pointer")) >= 2, "失败应按短间隔继续探测"
        sync_env._recheck_task.cancel()

    asyncio.run(_go())


def test_lifespan_挂载周期复查():
    """源级钉（轻量）：启动补偿之后并排挂会话内周期复查。"""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "from kb.baseline import schedule_periodic_recheck" in src
    assert src.index("schedule_sync()") < src.index("schedule_periodic_recheck()")


# ─── 登录钩子挂点（源级钉：挂载在 browser_auth 成功段） ────────────────


def test_browser_auth_成功段挂基线与树钩子():
    import inspect

    from auth_local import service

    src = inspect.getsource(service.browser_auth)
    assert "from kb.baseline import maybe_sync" in src
    assert "maybe_sync()" in src
    assert "from kb.tree_sync import maybe_sync as tree_maybe_sync" in src
    assert src.index("maybe_after_auth()") < src.index("maybe_sync()")
    assert src.index("maybe_sync()") < src.index("tree_maybe_sync()")


# ─── probe 端点（router 装配） ────────────────────────────────────────


def test_probe_端点_信封与只读():
    import inspect

    from kb import router

    src = inspect.getsource(router)
    assert '@router.get("/baseline/probe")' in src
    fn = router.baseline_probe_api
    body = inspect.getsource(fn)
    assert "probe_latest" in body and "sync_baseline" not in body
