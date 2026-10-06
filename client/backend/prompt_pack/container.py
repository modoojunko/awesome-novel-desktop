"""提示词包本地容器（c-prompt-pack-hardening D1/D3）。

落盘形态：`{DATA_ROOT}/prompt-pack/v{N}/pack.bin` ＝ `nonce(12B) || AES-GCM 密文`，
明文负载 `{"schema":1,"templates":{名字:文本}}`；**AAD 绑版本号**，防容器被掉包到别的
版本目录（也防跨版本复用）。同目录另有 `manifest.json`（不含模板内容，只有版本/哈希/签名
/时间）与 receipt，供既有机制与本模块之外的排障复用。

钥匙来源：`prompt_pack.localkey`（绑机器+用户的 OS 级保护存储）。读路径**只在内存解密**、
不写任何中间文件；按需解密、不常驻缓存（D3）。

原生替换位（D4，任务 4）：若存在编译型模块 `prompt_pack._native`，`seal/open` 全程走它——
钥匙解封与解密都在原生侧完成，Python 侧只递交明文字节，字节码里因此既没有模板明文、
也没有钥匙材料与解密参数。开发/测试态没有该模块时走本文件的纯 Python 实现（打包流水线
侧另有断言把它钉成必需，见 tasks 4.3）。
"""

from __future__ import annotations

import json
import os

CONTAINER_NAME = "pack.bin"
SCHEMA = 1
_NONCE_LEN = 12


class ContainerInvalid(RuntimeError):
    """容器解不开/形态非法——调用方按「该版本不可用」处理（回落或按未装）。"""


def _native():
    """编译型实现（存在即优先）；不存在返回 None（开发/测试态）。"""
    try:
        from prompt_pack import _native as mod  # noqa: PLC0415 — 可选依赖，按需探测
    except ImportError:
        return None
    return mod


def backend_name() -> str:
    return "native" if _native() is not None else "python"


def _pack_root() -> str:
    from prompt_pack import pack_root  # noqa: PLC0415 — 避免与包 __init__ 循环导入

    return pack_root()

def _key() -> bytes:
    """本地包密钥（绑机器+用户）；不可用统一转 ContainerInvalid——对调用方来说
    「换机/换用户导致钥匙失效」与「容器损坏」是同一件事：该版本不可用（按未装处理）。"""
    from prompt_pack import localkey  # noqa: PLC0415

    try:
        return localkey.get_or_create_key(_pack_root())
    except localkey.LocalKeyUnavailable as e:
        raise ContainerInvalid(f"本地包密钥不可用: {e}") from e


def _encode(templates: dict[str, str]) -> bytes:
    return json.dumps({"schema": SCHEMA, "templates": dict(templates)}, ensure_ascii=False).encode("utf-8")


def _decode(payload: bytes) -> dict[str, str]:
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise ContainerInvalid("容器明文不是合法 JSON") from e
    if not isinstance(obj, dict) or obj.get("schema") != SCHEMA:
        raise ContainerInvalid("容器 schema 不符")
    templates = obj.get("templates")
    if not isinstance(templates, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in templates.items()
    ):
        raise ContainerInvalid("容器模板表形态非法")
    return dict(templates)


def seal(templates: dict[str, str], version: str) -> bytes:
    """把模板表封成容器字节（用于落盘）。"""
    payload = _encode(templates)
    mod = _native()
    if mod is not None:
        return bytes(mod.seal(payload, str(version)))
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

    key = _key()
    nonce = os.urandom(_NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, payload, str(version).encode("utf-8"))


def open_container(blob: bytes, version: str) -> dict[str, str]:
    """解容器 → 模板表（内存中）。解不开抛 ContainerInvalid。"""
    mod = _native()
    if mod is not None:
        try:
            payload = bytes(mod.open(blob, str(version)))
        except Exception as e:  # noqa: BLE001 — 原生侧统一转容器非法，调用方按不可用处理
            raise ContainerInvalid(f"原生解密失败: {e}") from e
        return _decode(payload)
    from cryptography.exceptions import InvalidTag  # noqa: PLC0415
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

    if len(blob) <= _NONCE_LEN:
        raise ContainerInvalid("容器过短")
    key = _key()
    nonce, ct = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    try:
        payload = AESGCM(key).decrypt(nonce, ct, str(version).encode("utf-8"))
    except InvalidTag as e:
        raise ContainerInvalid("容器解密失败（钥匙不符或内容被改）") from e
    return _decode(payload)
