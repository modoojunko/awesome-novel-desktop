"""发布清单 Ed25519 签名/验签公共件（c-silent-upgrade tasks 2.2）。

canonical 规则与 prompt_pack/sync.py 逐字同源：对「去掉 signature 键后的清单 dict」
做 json.dumps(sort_keys=True, separators=(",", ":"))（ensure_ascii 取默认 True），
Ed25519 over UTF-8 bytes。私钥只在发布侧（CI Secrets：UPDATE_SIGNING_PRIVATE_KEY，
base64(32B raw)）；客户端只持公钥集合（{kid: base64(32B raw)}，打包期烘焙）。

设计依据：docs/design-c/drafts/ai-novel-c端-无感知自动升级-设计草案.md §5——
自动链把攻击面升级为「存储空间写权限＝零交互前置 RCE」，sha256 对攻击者无认证
价值，签名是自动链的强制前提（tasks 4b.1 硬闸）。
"""
from __future__ import annotations

import base64
import json

SIGNATURE_KEY = "signature"
SIGNER_KEY_ID_KEY = "signer_key_id"


def canonical_payload(manifest: dict) -> bytes:
    """签名/验签共用的 canonical 字节流：去 signature 键后紧凑 JSON（键排序）。"""
    payload = {k: v for k, v in manifest.items() if k != SIGNATURE_KEY}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_manifest(manifest: dict, private_b64: str, kid: str) -> dict:
    """发布侧：返回带 signature/signer_key_id 的新清单（不改传入）。私钥 b64(32B raw)。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_b64))
    out = {k: v for k, v in manifest.items() if k != SIGNATURE_KEY}
    out[SIGNER_KEY_ID_KEY] = kid
    out[SIGNATURE_KEY] = base64.b64encode(key.sign(canonical_payload(out))).decode("ascii")
    return out


def verify_manifest(manifest: dict, pubkeys: dict[str, bytes]) -> bool:
    """客户端：kid 命中信任集合且签名有效 → True；任何缺失/不符 → False（永不抛）。"""
    sig_b64 = manifest.get(SIGNATURE_KEY)
    kid = manifest.get(SIGNER_KEY_ID_KEY, "")
    if not isinstance(sig_b64, str) or not sig_b64 or kid not in pubkeys:
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        Ed25519PublicKey.from_public_bytes(pubkeys[kid]).verify(
            base64.b64decode(sig_b64), canonical_payload(manifest))
        return True
    except (InvalidSignature, ValueError, TypeError, OSError):
        # 签名不符/钥或签名 base64 损坏/钥长非法——一律视为验签失败（永不抛）
        return False
