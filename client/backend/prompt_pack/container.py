"""提示词包本地容器（c-prompt-pack-hardening D1/D3）。

落盘形态：`{DATA_ROOT}/prompt-pack/v{N}/pack.bin` ＝ `nonce(12B) || AES-GCM 密文`，
明文负载 `{"schema":1,"templates":{名字:文本}}`；**AAD 绑版本号**，防容器被掉包到别的
版本目录（也防跨版本复用）。同目录另有 `manifest.json`（不含模板内容，只有版本/哈希/签名
/时间）与 receipt，供既有机制与本模块之外的排障复用。

钥匙来源：`prompt_pack.localkey`（绑机器+用户的 OS 级保护存储）。读路径**只在内存解密**、
不写任何中间文件；按需解密、不常驻缓存（D3）。

发布态形态（D4/阶段二）：本模块与 `localkey`、`sync` 在打包时被**编译成原生扩展**
（`client/packaging/build/compile_native.py`；导入时扩展优先于 .py），因此交付包里的
字节码中既没有模板明文，也没有钥匙材料与解密参数——开发/测试态照常是 .py（同一份语义，
测试两态都跑）。打包产物侧另有闸门：产物必须含这三块的原生扩展、且不得含它们的
.py/.pyc（`compile_native.py --scan`，CI 与本地打包各跑一次）。
"""

from __future__ import annotations

import json
import os

CONTAINER_NAME = "pack.bin"
SCHEMA = 1
_NONCE_LEN = 12


class ContainerInvalid(RuntimeError):
    """容器解不开/形态非法——调用方按「该版本不可用」处理（回落或按未装）。"""


def backend_name() -> str:
    """当前进程里本模块是原生扩展还是 Python 源码（诊断/状态用，不改变行为）。"""
    import importlib.machinery  # noqa: PLC0415

    return "native" if any(__file__.endswith(suf) for suf in importlib.machinery.EXTENSION_SUFFIXES) else "python"


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
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: PLC0415

    key = _key()
    nonce = os.urandom(_NONCE_LEN)
    return nonce + AESGCM(key).encrypt(nonce, payload, str(version).encode("utf-8"))


def open_container(blob: bytes, version: str) -> dict[str, str]:
    """解容器 → 模板表（内存中）。解不开抛 ContainerInvalid。"""
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
