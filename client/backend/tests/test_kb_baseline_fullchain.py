"""基线包全链验证（s-kb-signed-delivery 本地版）：本地 HTTP 包→真实 HTTP 下载→
真实 Ed25519 验签→按题材入库→merged/选择器→hide 生效。

不 mock 传输层：只把 S 端 `sign` 换成返回本地 URL 的桩（S 端自身在 S 端仓测试里覆盖）；
`server_api.fetch_signed` 走真实 httpx＋真实出站守卫（KB_STORAGE_HOSTS=127.0.0.1）。
"""

import asyncio
import base64
import hashlib
import http.server
import json
import shutil
import socketserver
import tempfile
import threading
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import delete, select

from db import async_session
from kb import server_api
from kb.baseline import proxy_id
from manifest_crypto import sign_manifest
from models.app_meta import AppMeta
from models.kb import KbBaselineEntry, KbBaselineOverlay, KbBaselineTag

_KEY_RAW = bytes(range(32))
_PRIV = Ed25519PrivateKey.from_private_bytes(_KEY_RAW)
_PRIV_B64 = base64.b64encode(_KEY_RAW).decode()
_KID = "fullchain-k"
_PUB = {_KID: _PRIV.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}
_GENRE = "玄幻"


def _inline_pack(serve: Path) -> int:
    """按新布局打一个最小 release：genres/<slug>.jsonl + manifest + latest。"""
    entries = [
        {
            "src_key": "baseline:玄幻:fullchain-a", "title": "全链手法A", "concept": "手法",
            "genre": _GENRE, "instruction": "全链验证用条目：交手先守后攻，收在第三拍。",
            "payload": {"instruction": "全链验证用条目：交手先守后攻，收在第三拍。",
                        "slot": "打斗-节奏", "scene": "打斗"},
            "when": {"scene": "打斗"},
        },
        {
            "src_key": "baseline:玄幻:fullchain-b", "title": "全链手法B", "concept": "手法",
            "genre": _GENRE, "instruction": "全链验证用第二条：错身时先让半步再借力。",
            "payload": {"instruction": "全链验证用第二条：错身时先让半步再借力。",
                        "slot": "打斗-节奏", "scene": "打斗"},
            "when": {"scene": "打斗"},
        },
    ]
    body = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries).encode()
    rel = f"genres/{hashlib.sha1(_GENRE.encode()).hexdigest()[:16]}.jsonl"
    vdir = serve / "baseline/v1"
    (vdir / "genres").mkdir(parents=True, exist_ok=True)
    (vdir / rel).write_bytes(body)
    manifest = sign_manifest(
        {
            "version": 1,
            "entry_count": len(entries),
            "generated_at": "2026-11-02T00:00:00Z",
            "genres": {
                _GENRE: {
                    "path": rel,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "bytes": len(body),
                    "entry_count": len(entries),
                }
            },
        },
        _PRIV_B64,
        _KID,
    )
    mb = json.dumps(manifest, ensure_ascii=False).encode()
    (vdir / "manifest.json").write_bytes(mb)
    latest = sign_manifest(
        {
            "version": 1,
            "manifest_sha256": hashlib.sha256(mb).hexdigest(),
            "resume_baseline": False,
        },
        _PRIV_B64,
        _KID,
    )
    (serve / "baseline/latest.json").write_text(
        json.dumps(latest, ensure_ascii=False), encoding="utf-8"
    )
    return len(entries)


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: A002 — 静默访问日志
        return


def _serve(directory: Path) -> tuple[socketserver.TCPServer, int]:
    handler = lambda *a, **k: _Quiet(*a, directory=str(directory), **k)  # noqa: E731
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


async def _reset() -> None:
    async with async_session() as db:
        await db.execute(delete(KbBaselineTag))
        await db.execute(delete(KbBaselineEntry))
        await db.execute(delete(KbBaselineOverlay))
        for key in ("kb_baseline_version", "kb_baseline_genres", "kb_baseline_last_sync"):
            meta = await db.get(AppMeta, key)
            if meta:
                await db.delete(meta)
        await db.commit()


@pytest.mark.anyio
def test_全链_本地包真实下载验签入库出块(monkeypatch):
    from kb import baseline as bl
    from kb.match import MatchSignals, select_block
    from kb.merged import load_baseline_entries, set_overlay

    tmp = Path(tempfile.mkdtemp(prefix="kb-fullchain-"))
    expected = _inline_pack(tmp)
    srv, port = _serve(tmp)
    base = f"http://127.0.0.1:{port}/baseline"

    async def _sign(scope, *, version=None, path="", genre=""):
        if scope == "baseline_pointer":
            url = f"{base}/latest.json"
        elif scope == "baseline_manifest":
            url = f"{base}/v{version}/manifest.json"
        elif scope == "baseline_genre":
            url = f"{base}/v{version}/{path}"
        else:
            return {"code": 400, "msg": "bad scope"}
        return {
            "code": 0,
            "data": {
                "url": url,
                "quota": {"limit": 2, "used": 0, "remaining": 2},
                "version": version,
            },
        }

    asyncio.run(_reset())
    try:
        monkeypatch.setattr(bl, "_TRUST_PUBKEYS", _PUB)
        monkeypatch.setattr(server_api, "sign", _sign)
        monkeypatch.setenv("KB_STORAGE_HOSTS", "127.0.0.1")

        r = asyncio.run(bl.sync_genre(_GENRE))
        assert r["status"] == "synced", r
        assert 0 < r["entries"] <= expected, (r["entries"], expected)
        assert r["version"] == 1 and r["genre"] == _GENRE

        async def _check():
            async with async_session() as db:
                n = len((await db.execute(select(KbBaselineEntry))).scalars().all())
                assert n == r["entries"] and 0 < n <= expected, (n, expected)
                rows = await load_baseline_entries(
                    db, user_id="fullchain-user", genre=_GENRE
                )
                assert rows, "merged 域应能取到玄幻基线"
                assert rows[0].layer == "baseline" and rows[0].src_key.startswith("baseline:")

                sel = await select_block(
                    db, user_id="fullchain-user",
                    signals=MatchSignals(scene="打斗", emotion="燃"), genre=_GENRE,
                )
                assert sel is not None and sel.items
                hit_id = sel.items[0].entry.id
                assert hit_id in {i.id for i in rows}

                await set_overlay(
                    db, user_id="fullchain-user", entry_id=hit_id, action="hide"
                )
                sel2 = await select_block(
                    db, user_id="fullchain-user",
                    signals=MatchSignals(scene="打斗", emotion="燃"), genre=_GENRE,
                )
                shown = {i.entry.id for i in (sel2.items if sel2 else [])}
                assert hit_id not in shown

        asyncio.run(_check())

        # 同题材同内容二次同步：零下载（current）
        r2 = asyncio.run(bl.sync_genre(_GENRE))
        assert r2["status"] == "current"
    finally:
        srv.shutdown()
        srv.server_close()
        asyncio.run(_reset())
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.anyio
def test_代理id稳定性_跨包一致():
    """同一 src_key 在不同包版本里代理主键不变（run 快照/反馈跨版本可回读）。"""
    key = f"baseline:玄幻:{uuid.uuid4().hex[:6]}"
    assert proxy_id(key) == proxy_id(key)
    assert proxy_id(key) != proxy_id(key + "x")
