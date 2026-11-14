"""知识树 CDN 同步测试（c-kb-tree-cdn）。

镜像 test_kb_baseline_sync 的 fake-CDN 模式；指针签名用内容仓
``tree_publish.py`` 的 **legacy 三字段格式**（``json.dumps(sort_keys=True)``
默认分隔符——与 manifest_crypto 的 compact canonical 不同，这正是要钉的格式）。
网络面全注入；缓存走 {DATA_ROOT}/kb-tree（文件，不走 DB）。
"""

import base64
import hashlib
import json

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey as _K
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

_ed_key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
_TEST_PRIV = base64.b64encode(bytes(range(32))).decode()
_TEST_KID = "test-k"
_TEST_PUBKEYS = {_TEST_KID: _ed_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)}
_BASE = "http://127.0.0.1:1/knowledge/tree"

# 夹具树字节（与内容仓 taxonomy/taxonomy.json 同一份——conftest 播种同一文件）
from pathlib import Path

_FIXTURE_TREE = Path(__file__).resolve().parent / "fixtures" / "taxonomy" / "taxonomy.json"
_TREE_RAW = _FIXTURE_TREE.read_bytes()
_TREE_SHA = hashlib.sha256(_TREE_RAW).hexdigest()
_TREE_SIZE = len(_TREE_RAW)


def _sign_pointer(version: int, sha: str, size: int, *, bad_sig: bool = False) -> dict:
    """照 tree_publish.py:104-114 逐字：三字段子集 + 默认分隔符签名。"""
    latest = {
        "version": version,
        "taxonomy_sha256": sha,
        "size": size,
        "generated_at": "2026-11-11T00:00:00Z",
        "signer_key_id": _TEST_KID,
    }
    body = json.dumps(
        {k: latest[k] for k in ("version", "taxonomy_sha256", "size")}, sort_keys=True
    ).encode()
    key = _K.from_private_bytes(bytes(range(32)))
    sig = key.sign(body)
    latest["signature"] = base64.b64encode(
        bytes(range(32)) if bad_sig else sig
    ).decode()
    return latest


class _FakeCDN:
    def __init__(self):
        self.latest: dict | None = None
        self.tree_raw: bytes | None = None
        self.dead: set[str] = set()
        self.tree_fetches = 0

    async def get_json(self, client=None, url="", **kw):
        if any(d in url for d in self.dead):
            return None
        if url.endswith("latest.json"):
            return self.latest
        return None

    async def get_bytes(self, client=None, url="", **kw):
        if any(d in url for d in self.dead):
            return None
        if url.endswith("taxonomy.json"):
            self.tree_fetches += 1
            return self.tree_raw
        return None


_CDN = _FakeCDN()


def _publish(version: int, *, tree_raw: bytes | None = None, bad_sig: bool = False):
    raw = tree_raw if tree_raw is not None else _TREE_RAW
    _CDN.latest = _sign_pointer(version, hashlib.sha256(raw).hexdigest(), len(raw), bad_sig=bad_sig)
    _CDN.tree_raw = raw


def _run(coro):
    import asyncio

    return asyncio.run(coro)


async def _fetch_none(client, url):
    """探测必空桩：verdict 由 _validate_outbound 桩控制，fetch 恒 None。"""
    return None


import pytest  # noqa: E402

from kb import taxonomy as taxonomy_mod  # noqa: E402
from kb import tree_sync  # noqa: E402


@pytest.fixture
def tree_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setattr(tree_sync, "_TRUST_PUBKEYS", _TEST_PUBKEYS)
    monkeypatch.setattr(tree_sync, "_cdn_bases", lambda: [_BASE])
    monkeypatch.setattr(tree_sync, "_validate_outbound", lambda url: (True, "ok"))
    monkeypatch.setattr(tree_sync, "_fetch_json", _CDN.get_json)
    monkeypatch.setattr(tree_sync, "_fetch_bytes", _CDN.get_bytes)
    taxonomy_mod.reload()
    _CDN.dead = set()
    _CDN.tree_fetches = 0
    yield tmp_path
    _CDN.dead = set()
    _CDN.tree_fetches = 0
    taxonomy_mod.reload()


def test_首装_落缓存_tax可读(tree_env, monkeypatch):
    _publish(2)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "synced" and r["version"] == 2, r
    receipt = tree_sync.read_receipt()
    assert receipt and receipt["version"] == 2 and receipt["taxonomy_sha256"] == _TREE_SHA
    vdir = tree_sync.version_dir(2)
    assert (vdir / "taxonomy.json").read_bytes() == _TREE_RAW  # 原始字节，零重序列化
    assert (vdir / "meta.json").is_file()
    path = tree_sync.cached_tree_path()
    assert path and Path(path).read_bytes() == _TREE_RAW
    # KB_TAXONOMY_PATH 是 conftest 播种的夹具——这里显式切到缓存验证真实链路
    # （monkeypatch 自动还原：不污染兄弟模块的加载器状态）
    monkeypatch.setenv("KB_TAXONOMY_PATH", path)
    taxonomy_mod.reload()
    assert taxonomy_mod.nodes(), "同步后 taxonomy 应可读出节点"
    assert taxonomy_mod.is_ready() is True


def test_同版本_零写_零下载(tree_env):
    _publish(2)
    assert _run(tree_sync.sync_tree())["status"] == "synced"
    _CDN.tree_fetches = 0
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "current" and r["version"] == 2
    assert _CDN.tree_fetches == 0, "同版本不得下载包体"
    assert tree_sync.read_receipt()["version"] == 2


def test_同版本缓存损坏_修复重下(tree_env):
    _publish(2)
    assert _run(tree_sync.sync_tree())["status"] == "synced"
    (tree_sync.version_dir(2) / "taxonomy.json").write_bytes(b"corrupted")
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "synced", r
    assert (tree_sync.version_dir(2) / "taxonomy.json").read_bytes() == _TREE_RAW


def test_签名坏_保旧层(tree_env):
    _publish(2)
    assert _run(tree_sync.sync_tree())["status"] == "synced"
    _CDN.latest = _sign_pointer(3, _TREE_SHA, _TREE_SIZE, bad_sig=True)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "failed" and r["reason"] == "latest_invalid"
    assert tree_sync.read_receipt()["version"] == 2  # 旧层未动


def test_sha不符_保旧层(tree_env):
    _publish(2)
    assert _run(tree_sync.sync_tree())["status"] == "synced"
    _CDN.latest = _sign_pointer(3, "0" * 64, _TREE_SIZE)
    _CDN.tree_raw = _TREE_RAW
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "failed" and r["reason"] == "tree_hash"
    assert tree_sync.read_receipt()["version"] == 2


def test_size不符_保旧层(tree_env):
    _publish(2)
    assert _run(tree_sync.sync_tree())["status"] == "synced"
    _CDN.latest = _sign_pointer(3, _TREE_SHA, _TREE_SIZE + 1)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "failed" and r["reason"] == "tree_size"
    assert tree_sync.read_receipt()["version"] == 2


def test_结构非法_双根拒收(tree_env):
    bad = json.loads(_TREE_RAW.decode("utf-8"))
    bad["nodes"]["ghost_root"] = {"concept": "", "title": "假根", "parent": ""}
    bad_raw = json.dumps(bad, ensure_ascii=False).encode()
    _publish(3, tree_raw=bad_raw)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "failed" and r["reason"] == "tree_root_not_single"
    assert tree_sync.read_receipt() is None


def test_结构非法_parent悬空拒收(tree_env):
    bad = json.loads(_TREE_RAW.decode("utf-8"))
    bad["nodes"]["orphan"] = {"concept": "文笔", "title": "孤儿", "parent": "no_such"}
    bad_raw = json.dumps(bad, ensure_ascii=False).encode()
    _publish(3, tree_raw=bad_raw)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "failed" and r["reason"] == "tree_parent_dangling"


def test_回退拒绝(tree_env):
    _publish(3)
    assert _run(tree_sync.sync_tree())["status"] == "synced"
    _publish(2)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "skipped" and r["reason"] == "older_than_installed"
    assert tree_sync.read_receipt()["version"] == 3


def test_主域死_兜底域可用(tree_env, monkeypatch):
    real_bases = [_BASE, "http://127.0.0.1:2/knowledge/tree"]
    monkeypatch.setattr(tree_sync, "_cdn_bases", lambda: real_bases)
    _CDN.dead.add("127.0.0.1:1")
    _publish(2)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "synced" and r["version"] == 2


def test_无信任钥_skipped(tree_env, monkeypatch):
    monkeypatch.setattr(tree_sync, "_trust_keys", dict)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "skipped" and r["reason"] == "not_configured"


def test_KB_TREE_SYNC_0_schedule不跑(tree_env, monkeypatch):
    monkeypatch.setenv("KB_TREE_SYNC", "0")
    called = {"n": 0}

    class _Loop:
        def create_task(self, coro):
            called["n"] += 1
            coro.close()  # 不真跑，只计数

    import asyncio

    orig = asyncio.get_running_loop
    asyncio.get_running_loop = lambda: _Loop()
    try:
        tree_sync.schedule_sync()
    finally:
        asyncio.get_running_loop = orig
    assert called["n"] == 0, "KB_TREE_SYNC=0 时 schedule_sync 必须是 no-op"


def test_probe_无写(tree_env):
    _publish(2)
    r = _run(tree_sync.probe_latest())
    assert r["latest"] == 2 and r["installed"] == 0 and r["update_available"] is True
    assert tree_sync.read_receipt() is None, "probe 不得安装"
    _run(tree_sync.sync_tree())
    r = _run(tree_sync.probe_latest())
    assert r["installed"] == 2 and r["update_available"] is False


def test_verify_tree_pointer_格式钉(tree_env):
    latest = _sign_pointer(2, _TREE_SHA, _TREE_SIZE)
    assert tree_sync.verify_tree_pointer(latest, _TEST_PUBKEYS) is True
    # manifest_crypto 的 compact canonical 对同一指针必须验不过——两套格式不通用
    from manifest_crypto import verify_manifest

    assert verify_manifest(latest, _TEST_PUBKEYS) is False
    # 篡改 version 后 legacy 验签必须失败
    tampered = {**latest, "version": 3}
    assert tree_sync.verify_tree_pointer(tampered, _TEST_PUBKEYS) is False


def test_taxonomy_空树安全(tree_env, monkeypatch):
    monkeypatch.setenv("KB_TAXONOMY_PATH", str(tree_env / "no-such-file.json"))
    taxonomy_mod.reload()
    assert taxonomy_mod.nodes() == {}
    assert taxonomy_mod.is_ready() is False
    assert taxonomy_mod.node_for("文风", "tone") is None
    assert taxonomy_mod.parent_chain("craft_root") == []
    assert taxonomy_mod.parent_chain("no-such-key") == []


def test_taxonomy_脏结构归一_不炸消费端(tree_env, tmp_path, monkeypatch):
    bad = tmp_path / "bad-tree.json"
    bad.write_text(json.dumps({
        "nodes": {"k1": {"concept": "文笔", "title": "笔法", "parent": ""}},
        "slot_map": {"文笔|rule": "missing-key", "文笔|x": "k1"},
        "extra": 1,
    }), encoding="utf-8")
    monkeypatch.setenv("KB_TAXONOMY_PATH", str(bad))
    taxonomy_mod.reload()
    nodes = taxonomy_mod.nodes()
    assert set(nodes) == {"k1"}  # dangling slot_map 被剥
    assert taxonomy_mod.node_for("文笔", "x") == ("k1", nodes["k1"])
    assert taxonomy_mod.node_for("文笔", "rule") is None


def test_validate_环拒收():
    data = {
        "nodes": {
            "a": {"concept": "文笔", "title": "A", "parent": "b"},
            "b": {"concept": "文笔", "title": "B", "parent": "a"},
        },
        "slot_map": {},
    }
    raw = json.dumps(data, ensure_ascii=False).encode()
    ok, reason = tree_sync.validate_tree_payload(raw)
    assert not ok and reason == "tree_cycle"


def test_receipt缺_可从meta恢复(tree_env):
    _publish(2)
    assert _run(tree_sync.sync_tree())["status"] == "synced"
    tree_sync.receipt_path().unlink()
    path = tree_sync.cached_tree_path()
    assert path and Path(path).read_bytes() == _TREE_RAW, "receipt 缺失应从 v*/meta.json 恢复"


# ── fake-ip 代理环境失败细分（c-proxy-fakeip-compat）────────────────────────


def test_fakeip环境同步失败记proxy_fake_ip(tree_env, monkeypatch):
    """TUN fake-ip（解析全落 198.18.0.0/15，放行但代理节点不通）→ 失败原因
    proxy_fake_ip，与 latest_invalid 可区分。"""
    monkeypatch.setattr(tree_sync, "_validate_outbound", lambda url: (True, "fakeip"))
    monkeypatch.setattr(tree_sync, "_fetch_json", _fetch_none)
    r = _run(tree_sync.sync_tree())
    assert r["status"] == "failed" and r["reason"] == "proxy_fake_ip"
