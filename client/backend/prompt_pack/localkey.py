"""本地包密钥（LWK）——绑机器与用户账户的 OS 级保护存储封装（c-prompt-pack-hardening D2）。

威胁模型见 change `c-prompt-pack-hardening`（spec「本机提取防护强度与不承诺项」）：
目标是把**本机主人**提取提示词的成本抬到高于提示词本身价值；不承诺防内存 dump、
自建代理抓出口流量、定向逆向。本模块只做一件事——保管一把 32B 随机钥匙（LWK），
让「把包目录整拷到别的机器/别的用户」解不开：

    Windows  DPAPI 用户作用域（ctypes 调 CryptProtectData，零新依赖）→ 封装体落
             {pack_root}/key.bin（DPAPI blob，换机器/换用户解不开）
    macOS    Keychain 通用口令项（security CLI，零新依赖）——钥匙本身不进文件
    其余     机器指纹派生（弱保护档：Linux 开发/CI 用；不随包分发）

失败语义（重要）：解封失败/钥匙缺失 → `LocalKeyUnavailable`，调用方按「未装包」处理
（联网重下），**绝不**回退到明文可用态。弱保护档会在日志与状态里标注，不静默降级。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import getpass
import hashlib
import os
import platform
import subprocess

KEY_NAME = "key.bin"
KEY_BYTES = 32

PROTECTION_DPAPI = "dpapi"
PROTECTION_KEYCHAIN = "keychain"
PROTECTION_WEAK = "weak"

# DPAPI 的额外熵：不是密钥，只是让 blob 与「本应用」绑定（同机同用户的别的程序
# 拿着 blob 也解不开，除非它知道这个常量——它就在代码里，所以别把它当防线）
_ENTROPY = b"awesomenovel.prompt-pack.v1"
_KEYCHAIN_SERVICE = "awesomenovel-prompt-pack"


class LocalKeyUnavailable(RuntimeError):
    """本地包密钥不可用（换机/换用户/系统重装/封装损坏）——调用方按未装包处理。"""


KEYSTORE_ENV = "AINOVEL_PACK_KEYSTORE"


def protection_level() -> str:
    """当前保护档（写进状态与日志；弱档要显式可见，不静默）。

    `AINOVEL_PACK_KEYSTORE` 可显式指定（仅测试/排障用）：指到 weak 只会**换一把
    派生钥匙**，解不开已装容器（不是绕过），所以它不是攻击面。
    """
    override = (os.environ.get(KEYSTORE_ENV) or "").strip().lower()
    if override in (PROTECTION_DPAPI, PROTECTION_KEYCHAIN, PROTECTION_WEAK):
        return override
    if platform.system() == "Windows":
        return PROTECTION_DPAPI
    if platform.system() == "Darwin":
        return PROTECTION_KEYCHAIN
    return PROTECTION_WEAK


def key_path(pack_root: str) -> str:
    return os.path.join(pack_root, KEY_NAME)


def drop_key(pack_root: str) -> None:
    """丢弃钥匙（换机/损坏自愈用）：删文件＋尽力删 Keychain 项。"""
    try:
        os.remove(key_path(pack_root))
    except FileNotFoundError:
        pass
    if protection_level() == PROTECTION_KEYCHAIN:
        _keychain_delete()


def get_or_create_key(pack_root: str) -> bytes:
    """取钥匙；不存在则生成并封装落盘。任何异常一律转 LocalKeyUnavailable。"""
    existing = unwrap_key(pack_root)
    if existing is not None:
        return existing
    key = os.urandom(KEY_BYTES)
    wrap_key(pack_root, key)
    return key


def wrap_key(pack_root: str, key: bytes) -> None:
    if len(key) != KEY_BYTES:
        raise ValueError("LWK 必须是 32 字节")
    level = protection_level()
    if level == PROTECTION_DPAPI:
        blob = _dpapi_protect(key)
        os.makedirs(pack_root, exist_ok=True)
        tmp = key_path(pack_root) + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, key_path(pack_root))
        return
    if level == PROTECTION_KEYCHAIN:
        _keychain_store(key.hex())
        return
    # 弱档：派生式，无落盘物（换机即失效，够开发/CI 用）
    return


def unwrap_key(pack_root: str) -> bytes | None:
    """解封钥匙；不存在返回 None，解不开抛 LocalKeyUnavailable。"""
    level = protection_level()
    if level == PROTECTION_DPAPI:
        try:
            with open(key_path(pack_root), "rb") as f:
                blob = f.read()
        except FileNotFoundError:
            return None
        except OSError as e:  # noqa: BLE001 — 读不动＝不可用，交给调用方按未装处理
            raise LocalKeyUnavailable(f"key.bin 读取失败: {e}") from e
        try:
            return _dpapi_unprotect(blob)
        except OSError as e:
            raise LocalKeyUnavailable("DPAPI 解封失败（换了机器或用户账户）") from e
    if level == PROTECTION_KEYCHAIN:
        raw = _keychain_fetch()
        if raw is None:
            return None
        try:
            key = bytes.fromhex(raw.strip())
        except ValueError as e:
            raise LocalKeyUnavailable("Keychain 内钥匙形态非法") from e
        if len(key) != KEY_BYTES:
            raise LocalKeyUnavailable("Keychain 内钥匙长度非法")
        return key
    # 弱档：机器指纹派生（同机同用户稳定；换机器即变）
    return _derive_weak_key()


# ── Windows DPAPI（用户作用域；不解锁 UI，后台静默可用）─────────────────────


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_protect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    blob_in = _DataBlob(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))
    entropy = _DataBlob(len(_ENTROPY), ctypes.cast(ctypes.create_string_buffer(_ENTROPY), ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN：无 UI 静默失败，不弹系统对话框
    ok = crypt32.CryptProtectData(ctypes.byref(blob_in), "AwesomeNovel prompt-pack key", ctypes.byref(entropy), None, None, flags, ctypes.byref(blob_out))
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptProtectData failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def _dpapi_unprotect(blob: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    buf = ctypes.create_string_buffer(blob, len(blob))
    blob_in = _DataBlob(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    entropy = _DataBlob(len(_ENTROPY), ctypes.cast(ctypes.create_string_buffer(_ENTROPY), ctypes.POINTER(ctypes.c_char)))
    blob_out = _DataBlob()
    flags = 0x1
    ok = crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, ctypes.byref(entropy), None, None, flags, ctypes.byref(blob_out))
    if not ok:
        raise OSError(ctypes.get_last_error(), "CryptUnprotectData failed")
    try:
        key = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)
    if len(key) != KEY_BYTES:
        raise OSError("解出的钥匙长度非法")
    return key


# ── macOS Keychain（security CLI；钥匙不进文件系统）─────────────────────────


def _keychain_account() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — 取不到用户名也不该让整条链挂掉
        return "default"


def _run_security(args: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(["security", *args], capture_output=True, text=True, check=False, **kw)


def _keychain_store(hex_key: str) -> None:
    r = _run_security(
        ["add-generic-password", "-U", "-s", _KEYCHAIN_SERVICE, "-a", _keychain_account(), "-w", hex_key]
    )
    if r.returncode != 0:
        raise LocalKeyUnavailable(f"Keychain 写入失败：{r.stderr.strip() or r.returncode}")


def _keychain_fetch() -> str | None:
    r = _run_security(["find-generic-password", "-s", _KEYCHAIN_SERVICE, "-a", _keychain_account(), "-w"])
    if r.returncode != 0:
        # errSecItemNotFound(-25300) 与「未授权」都落这里：前者＝未装钥匙，后者＝不可用。
        # 两者都以 stderr 文本区分太脆，统一按「取不到」返回 None，由调用方决定重装。
        return None
    return r.stdout.strip() or None


def _keychain_delete() -> None:
    _run_security(["delete-generic-password", "-s", _KEYCHAIN_SERVICE, "-a", _keychain_account()])


# ── 弱保护档（仅开发/CI：机器指纹派生）──────────────────────────────────────


def machine_id() -> str:
    system = platform.system()
    if system == "Windows":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                return str(winreg.QueryValueEx(k, "MachineGuid")[0])
        except OSError:
            return ""
    if system == "Darwin":
        r = subprocess.run(
            ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], capture_output=True, text=True, check=False
        )
        for line in r.stdout.splitlines():
            if "IOPlatformUUID" in line:
                return line.split("=")[-1].strip().strip('"')
        return ""
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(p, encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            continue
    return ""


def _derive_weak_key() -> bytes:
    salt = b"awesomenovel.prompt-pack.weak.v1"
    seed = f"{machine_id()}|{_keychain_account()}|{os.environ.get('DATA_ROOT', '')}".encode()
    return hashlib.sha256(salt + seed).digest()
