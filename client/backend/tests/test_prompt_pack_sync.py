"""c-prompt-pack-client 3.x：同步器全链测试。

本地假 CDN（http.server 线程）＋ Ed25519 测试钥对 ＋ AES-GCM bundle fixture；
SSRF 校验以 monkeypatch 放行（校验逻辑本身另由真实域断言覆盖）。
"""

import base64
import hashlib
import http.server
import importlib
import json
import os
import threading

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("PROMPT_PACK_MODE", raising=False)
    import prompt_pack
    import prompt_pack.sync as sync_mod
    import prompts

    importlib.reload(prompt_pack)
    importlib.reload(sync_mod)
    importlib.reload(prompts)
    yield tmp_path, prompt_pack, sync_mod, prompts
    importlib.reload(sync_mod)
    importlib.reload(prompt_pack)
    importlib.reload(prompts)


@pytest.fixture()
def cdn(tmp_path, monkeypatch):
    """假 CDN：tmp 目录作根 + http.server 线程；返回 (base_url, publish)。"""
    root = tmp_path / "cdn"
    root.mkdir()
    import functools

    class _Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):  # noqa: ANN002
            pass

    handler = functools.partial(_Quiet, directory=str(root))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setenv("CLIENT_PROMPT_PACK_URL", f"{base}/prompts/latest.json")
    monkeypatch.setenv("CLIENT_PROMPT_PACK_URL_FALLBACK", f"{base}/prompts/latest.json")
    yield base, root
    srv.shutdown()


# ── 加密/签名 fixture ────────────────────────────────────────────────────────

def _keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    pub = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return sk, base64.b64encode(pub).decode()


def _sign(manifest_without_sig: dict, sk) -> str:
    blob = json.dumps(manifest_without_sig, sort_keys=True, separators=(",", ":")).encode()
    return base64.b64encode(sk.sign(blob)).decode()


def _bundle(templates: dict, version: str, tier: str, cek: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    plain = json.dumps({"version": version, "tier": tier, "templates": templates}).encode()
    return nonce + AESGCM(cek).encrypt(nonce, plain, None)


def _publish(root, version, tier_map, templates_by_tier, sk, kid,
             min_client_version=None, min_pack_version=None):
    """tier_map: {tier: (key_id, cek_bytes)}；模板清单跨档相同（test 简化）。"""
    import pathlib

    vdir = pathlib.Path(root) / "prompts" / f"v{version}"
    vdir.mkdir(parents=True, exist_ok=True)
    tpl_hashes = {n: hashlib.sha256(t.encode()).hexdigest() for n, t in templates_by_tier.items()}
    tiers = {}
    for tier, (kid_, cek) in tier_map.items():
        blob = _bundle(templates_by_tier, version, tier, cek)
        (vdir / f"{tier}.bin").write_bytes(blob)
        tiers[tier] = {
            "key_id": kid_,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "size": len(blob),
            "template_count": len(templates_by_tier),
        }
    manifest = {
        "schema_version": 1,
        "version": version,
        "signer_key_id": kid,
        "tiers": tiers,
        "templates": tpl_hashes,
    }
    if min_client_version:
        manifest["min_client_version"] = min_client_version
    manifest["signature"] = _sign(manifest, sk)
    (vdir / "manifest.json").write_text(json.dumps(manifest))
    latest = {
        "schema_version": 1,
        "version": version,
        "min_client_version": min_client_version or "",
        "min_pack_version": min_pack_version or "",
        "published_at": "2026-10-05T00:00:00Z",
        "tiers": tiers,
        "signer_key_id": kid,
    }
    manifest_for_latest = dict(latest)
    latest["signature"] = _sign(manifest_for_latest, sk)
    (pathlib.Path(root) / "prompts").mkdir(exist_ok=True)
    (pathlib.Path(root) / "prompts" / "latest.json").write_text(json.dumps(latest))
    return manifest, latest


TPL = {"write_chapter": "<<system>>\n你是助手\n<<user>>\n写"}


def _wire(env, monkeypatch, sk, pub_b64, exchange):
    _, pp, sync_mod, _ = env
    monkeypatch.setattr(sync_mod, "_validate_outbound", lambda url: True)
    monkeypatch.setenv("CLIENT_PACK_PUBKEYS", json.dumps({"test-kid": pub_b64}))
    monkeypatch.setattr(sync_mod, "_exchange_cek", exchange)
    return pp, sync_mod


def test_sync_happy_path_installs(env, cdn, monkeypatch):
    root, _ = cdn if False else cdn  # base, root
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))

    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "ready"
    receipt = pp.read_receipt()
    assert receipt["version"] == "5" and receipt["tier"] == "free"
    assert pp.read_highwatermark() == "5"
    # loader 读包内版本
    _, _, _, prompts = env
    assert "你是助手" in prompts.load("write_chapter")


def test_sync_tampered_bundle_rejected_keeps_old(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    # 先装 v5 成功
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    # 再发 v6 且篡改 bin（hash 不匹配）
    _publish(cdn_root, "6", {"free": ("k-free-6", cek)}, TPL, sk, "test-kid")
    bin_path = cdn_root / "prompts" / "v6" / "free.bin"
    bin_path.write_bytes(bin_path.read_bytes() + b"x")
    st = sync_mod.sync_once(local_tier="free")
    # 失败矩阵：旧包可用即 ready（全静默）；失败原因保留为诊断字段
    assert st["phase"] == "ready" and st["reason"] == "bundle_hash"
    assert pp.read_receipt()["version"] == "5"  # 旧包保留


def test_sync_bad_signature_rejected(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    man, latest = _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    # 篡改 manifest（保留原签名）→ 验签失败
    man["templates"]["write_chapter"] = "0" * 64
    (cdn_root / "prompts" / "v5" / "manifest.json").write_text(json.dumps(man))
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: (None, -1))
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "failed" and st["reason"] == "signature"


def test_sync_highwatermark_blocks_replay(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "7", {"free": ("k-free-7", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    # 攻击者重放 v6（签名合法）→ 高水位挡
    _publish(cdn_root, "6", {"free": ("k-free-6", cek)}, TPL, sk, "test-kid")
    st = sync_mod.sync_once(local_tier="free")
    assert pp.read_receipt()["version"] == "7"
    assert st.get("version") == "7"


def test_sync_403_downgrades_tier(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"pro": ("k-pro-5", cek), "free": ("k-free-5", cek)}, TPL, sk, "test-kid")

    def exchange(kid, ver):
        if kid == "k-pro-5":
            return None, 403  # 本地以为 pro，S端 说不够
        return {"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0

    pp, sync_mod = _wire(env, monkeypatch, sk, pub, exchange)
    st = sync_mod.sync_once(local_tier="pro")
    assert st["phase"] == "ready" and st["tier"] == "free"


def test_sync_all_tiers_403_tier_denied(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: (None, 403))
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "tier_denied"


def test_sync_404_reports_key_retired(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: (None, 404))
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "failed" and st["reason"] == "key_retired"


def test_sync_min_pack_version_retires_installed(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "3", {"free": ("k-free-3", cek)}, TPL, sk, "test-kid")
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    # v4 召回底线=4：已装 v3 被召回，装 v4
    _publish(cdn_root, "4", {"free": ("k-free-4", cek)}, TPL, sk, "test-kid", min_pack_version="4")
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "ready" and pp.read_receipt()["version"] == "4"


def test_sync_already_latest_is_ready(env, cdn, monkeypatch):
    base, cdn_root = cdn
    sk, pub = _keypair()
    cek = os.urandom(32)
    _publish(cdn_root, "5", {"free": ("k-free-5", cek)}, TPL, sk, "test-kid")
    calls = []
    pp, sync_mod = _wire(env, monkeypatch, sk, pub, lambda kid, ver: (calls.append(1), ({"cek": base64.b64encode(cek).decode(), "key_id": kid, "tier": "free", "version": ver}, 0))[1])
    assert sync_mod.sync_once(local_tier="free")["phase"] == "ready"
    n = len(calls)
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] == "ready" and len(calls) == n  # 已最新：不再换钥


def test_sync_no_keys_skips(env, cdn, monkeypatch):
    base, cdn_root = cdn
    _, pp, sync_mod, _ = env
    monkeypatch.setattr(sync_mod, "_validate_outbound", lambda url: True)
    monkeypatch.delenv("CLIENT_PACK_PUBKEYS", raising=False)
    st = sync_mod.sync_once(local_tier="free")
    assert st["phase"] in ("missing", "failed")  # 不假装成功
