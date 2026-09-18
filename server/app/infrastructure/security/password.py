"""口令与密保答案哈希（s-security-hardening）。

现行算法 = bcrypt（自带随机盐，标准 $2b$ 格式，恒定时间校验由库保证）；
历史算法 = PBKDF2-HMAC-SHA256 + 全局固定盐（仅用于校验存量哈希，验证成功时由
调用方惰性升级改写，用户零感知）。fail-closed：哈希为空/格式非法一律验证失败。

bcrypt 语义上限 72 字节（超出静默截断）——入口必须显式拒绝超长（password_too_long），
不得静默按 72 字节截断后存哈希。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re

import bcrypt

# cost 默认 12（单次校验 ≈ 250ms，登录限流 30/min/IP 恰好约束总算力）；
# 测试栈经 BCRYPT_ROUNDS 注入低值提速（与 RATE_LIMIT_LOGIN_PER_MIN 同范式，import 期求值）
_BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12")) or 12

# 历史 PBKDF2 参数（与旧系统保持相同 salt，保证存量哈希兼容）
_LEGACY_SALT = "ainovel_local_test"
_LEGACY_ITERATIONS = 100_000

MAX_PASSWORD_BYTES = 72  # bcrypt 语义上限：超出部分被静默忽略，必须显式拒绝

# 标准格式预检：$2<variant>$<cost>$<53 位 base64 摘要>。pyo3 的 bcrypt 绑定对畸形哈希
# 会 panic（PanicException 非 ValueError），必须先拦——畸形一律 fail-closed。
_BCRYPT_RE = re.compile(r"^\$2[abxy]\$\d{2}\$[./A-Za-z0-9]{53}$")


def password_too_long(password: str) -> bool:
    """明文口令超 bcrypt 72 字节上限（UTF-8 字节数）。"""
    return len((password or "").encode("utf-8")) > MAX_PASSWORD_BYTES


def normalize_security_answer(answer: str) -> str:
    """密保答案归一化：去首尾空白 + casefold（设置与验证走同一通道）。"""
    return (answer or "").strip().casefold()


def hash_password(password: str) -> str:
    """口令 → bcrypt 哈希（$2b$ 前缀，含随机盐与 cost）。"""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    ).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """口令校验：bcrypt（现行）/ PBKDF2-hex（存量）自动分派；fail-closed。"""
    if not plain or not hashed:
        return False
    if hashed.startswith("$2"):
        if not _BCRYPT_RE.fullmatch(hashed):
            return False  # 非法/截断哈希（如注销置空后的脏数据）
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
        except ValueError:
            return False
    # 存量 PBKDF2-hex（全局固定盐）——恒定时间比较
    computed = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), _LEGACY_SALT.encode("utf-8"), _LEGACY_ITERATIONS
    ).hex()
    return hmac.compare_digest(computed, hashed)


def needs_rehash(hashed: str) -> bool:
    """存量哈希是否需要升级到现行算法（验证成功后由调用方改写）。"""
    return bool(hashed) and not hashed.startswith("$2")
