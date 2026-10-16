"""manifest_crypto 单元测试（签名链 2.2）＋ update_pubkeys 信任集合边界。"""
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import manifest_crypto as mc


@pytest.fixture()
def keys():
    key = Ed25519PrivateKey.generate()
    return {"priv": base64.b64encode(key.private_bytes_raw()).decode(),
            "pub": base64.b64encode(key.public_key().public_bytes_raw()).decode()}


def test_sign_verify_roundtrip(keys):
    m = {"version": "0.99.5", "auto_enabled": True, "platforms": {"win": {"url": "https://x"}}}
    signed = mc.sign_manifest(m, keys["priv"], "update-k1")
    assert signed["signer_key_id"] == "update-k1"
    assert mc.verify_manifest(signed, {"update-k1": base64.b64decode(keys["pub"])}) is True


def test_verify_rejects_tampered_payload(keys):
    m = {"version": "0.99.5", "auto_enabled": True}
    signed = mc.sign_manifest(m, keys["priv"], "update-k1")
    signed["auto_enabled"] = not signed["auto_enabled"]
    assert mc.verify_manifest(signed, {"update-k1": base64.b64decode(keys["pub"])}) is False


def test_verify_rejects_missing_or_unknown_kid(keys):
    m = {"version": "0.99.5"}
    signed = mc.sign_manifest(m, keys["priv"], "update-k1")
    assert mc.verify_manifest({k: v for k, v in signed.items() if k != "signature"},
                              {"update-k1": base64.b64decode(keys["pub"])}) is False
    assert mc.verify_manifest(signed, {"other-kid": base64.b64decode(keys["pub"])}) is False
    assert mc.verify_manifest(signed, {}) is False


def test_canonical_ignores_signature_key_ordering(keys):
    m = {"version": "0.99.5", "auto_enabled": True}
    signed = mc.sign_manifest(m, keys["priv"], "update-k1")
    reordered = {k: signed[k] for k in reversed(list(signed.keys()))}
    assert mc.verify_manifest(reordered, {"update-k1": base64.b64decode(keys["pub"])}) is True
