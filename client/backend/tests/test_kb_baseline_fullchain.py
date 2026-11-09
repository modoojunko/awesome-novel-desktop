"""基线包全链验证（c-kb-baseline C4 本地版）：内容仓构建→发布→真实 HTTP→同步→出块。

不 mock 网络层：本地起 http.server 服务发布目录，走真实 httpx＋真实验签＋真实
入库，最后经 merged 域选出条目并验证 hide 生效。内容仓在本机时用其 build/publish
真实产物（跨仓口径），不在时用等价的内联包（主库 CI 单仓也能跑）。
"""

import base64
import http.server
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from sqlalchemy import delete, select

from db import async_session
from kb.baseline import proxy_id
from manifest_crypto import sign_manifest
from models.app_meta import AppMeta
from models.kb import KbBaselineEntry, KbBaselineOverlay, KbBaselineTag

_KEY_RAW = bytes(range(32))
_PRIV = Ed25519PrivateKey.from_private_bytes(_KEY_RAW)
_PRIV_B64 = base64.b64encode(_KEY_RAW).decode()
_KID = "fullchain-k"
_PUB = {_KID: _PRIV.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}


def _content_repo() -> Path | None:
    env = os.environ.get("KNOWLEDGE_REPO_DIR")
    cand = [Path(env)] if env else []
    cand.append(Path(__file__).resolve().parents[4] / "awesome-novel-knowledge")
    for p in cand:
        if p and (p / "tools" / "build.py").is_file():
            return p
    return None


def _publish_content_repo(repo: Path, serve: Path) -> int:
    """内容仓真实构建＋发布到本地演练目录；返回包内条目数。"""
    dist = serve / "_dist"
    env = {
        **os.environ,
        "KNOWLEDGE_DIST_DIR": str(dist),
        "KNOWLEDGE_CDN_DIR": str(serve),
        "KNOWLEDGE_SIGNING_PRIVATE_KEY": _PRIV_B64,
        "KNOWLEDGE_SIGNING_KEY_ID": _KID,
    }
    env.pop("GITHUB_ACTIONS", None)
    subprocess.run(
        [sys.executable, "tools/build.py", "--version", "1"], cwd=repo, env=env,
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        [sys.executable, "tools/publish.py", "--version", "1"], cwd=repo, env=env,
        check=True, capture_output=True, text=True,
    )
    manifest = json.loads((serve / "knowledge/baseline/v1/manifest.json").read_text())
    return int(manifest["entry_count"])


def _inline_pack(serve: Path) -> int:
    """无内容仓时的等价包（同发布布局；仅两条，够验链路）。"""
    entries = [
        {
            "src_key": "baseline:玄幻:fullchain-a", "title": "全链手法A", "concept": "手法",
            "genre": "玄幻", "instruction": "全链验证用条目：交手先守后攻，收在第三拍。",
            "payload": {"instruction": "全链验证用条目：交手先守后攻，收在第三拍。",
                        "slot": "打斗-节奏", "scene": "打斗"},
            "when": {"scene": "打斗"},
        },
        {
            "src_key": "baseline:玄幻:fullchain-b", "title": "全链手法B", "concept": "手法",
            "genre": "玄幻", "instruction": "全链验证用第二条：错身时先让半步再借力。",
            "payload": {"instruction": "全链验证用第二条：错身时先让半步再借力。",
                        "slot": "打斗-节奏", "scene": "打斗"},
            "when": {"scene": "打斗"},
        },
    ]
    body = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries).encode()
    vdir = serve / "knowledge/baseline/v1"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / "entries.jsonl").write_bytes(body)
    import hashlib

    manifest = sign_manifest({
        "version": 1, "format_version": 1, "entry_count": len(entries),
        "generated_at": "2026-11-02T00:00:00Z",
        "files": [{"path": "entries.jsonl", "sha256": hashlib.sha256(body).hexdigest()}],
    }, _PRIV_B64, _KID)
    mb = json.dumps(manifest, ensure_ascii=False).encode()
    (vdir / "manifest.json").write_bytes(mb)
    latest = sign_manifest({
        "version": 1, "manifest_sha256": hashlib.sha256(mb).hexdigest(),
    }, _PRIV_B64, _KID)
    (serve / "knowledge/baseline/latest.json").write_text(json.dumps(latest))
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
        meta = await db.get(AppMeta, "kb_baseline_version")
        if meta:
            await db.delete(meta)
        await db.commit()


@pytest.mark.anyio
def test_全链_构建发布同步出块(monkeypatch):
    import asyncio

    from kb import baseline as bl
    from kb.match import MatchSignals, select_block
    from kb.merged import load_baseline_entries, set_overlay

    repo = _content_repo()
    tmp = Path(tempfile.mkdtemp(prefix="kb-fullchain-"))
    if repo is not None:
        # 内容仓产物含中文目录（仙侠/修真），cp 语义无碍；直接发到 tmp
        expected = _publish_content_repo(repo, tmp)
    else:
        expected = _inline_pack(tmp)
    srv, port = _serve(tmp)

    asyncio.run(_reset())
    try:
        monkeypatch.setenv(
            "KNOWLEDGE_CDN_BASE", f"http://127.0.0.1:{port}/knowledge/baseline"
        )
        monkeypatch.setattr(bl, "_TRUST_PUBKEYS", _PUB)

        r = asyncio.run(bl.sync_baseline())
        assert r["status"] == "synced", r
        # v2 内容源（714 条真实拆书）经 C 端 gates 诚实过滤：echo/结构重语言条目
        # 整条跳过——entries ≤ 包内数且非零（有收有跳＝闸在工作）
        assert 0 < r["entries"] <= expected, (r["entries"], expected)
        assert r["version"] == 1

        async def _check():
            async with async_session() as db:
                n = len((await db.execute(select(KbBaselineEntry))).scalars().all())
                # gates 诚实过滤：落库数＝收下数（≤包内数且非零），跳过条不落库
                assert n == r["entries"] and 0 < n <= expected, (n, expected)
                rows = await load_baseline_entries(db, user_id="fullchain-user", genre="玄幻")
                assert rows, "merged 域应能取到玄幻基线"
                assert rows[0].layer == "baseline" and rows[0].src_key.startswith("baseline:")

                # 选择器：打斗信号 → 命中基线条目（代理 id）
                sel = await select_block(
                    db, user_id="fullchain-user",
                    signals=MatchSignals(scene="打斗", emotion="燃"), genre="玄幻",
                )
                assert sel is not None and sel.items
                hit_id = sel.items[0].entry.id
                assert hit_id in {i.id for i in rows}

                # 隐藏生效（写时复制 upper 层）
                await set_overlay(db, user_id="fullchain-user", entry_id=hit_id, action="hide")
                sel2 = await select_block(
                    db, user_id="fullchain-user",
                    signals=MatchSignals(scene="打斗", emotion="燃"), genre="玄幻",
                )
                shown = {i.entry.id for i in (sel2.items if sel2 else [])}
                assert hit_id not in shown

        asyncio.run(_check())

        # 同版本二次同步：零下载（current）
        r2 = asyncio.run(bl.sync_baseline())
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
