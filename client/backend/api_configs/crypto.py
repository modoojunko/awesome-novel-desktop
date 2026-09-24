"""API key encryption using Fernet (symmetric AES-128-CBC with HMAC).

The encryption key lives **in the database** (row ``fernet_key`` of the
``app_meta`` KV table) so that the database file is a self-contained unit:
any whole-database move/backup/restore carries its key and ciphertext stays
readable. The legacy on-disk ``{DATA_ROOT}/.fernet_key`` file is retired; on
first boot with a keyless database its content is migrated verbatim into the
row (zero re-encryption) when present and well-formed, and the file is kept
as a read-only leftover so older builds on the same machine keep working
against the same data directory.

Trade-off (explicit, spec: model-api-config): with the key in the database,
a database file that leaks on its own carries its key with it — the previous
"db alone is not enough" property is gone. It was already illusory (key file
and database shared one data directory).

If key initialization has not run (startup order bug), crypto calls fail
fast with RuntimeError instead of silently degrading.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from config import DATA_ROOT

_FERNET_KEY_FILE = os.path.join(DATA_ROOT, ".fernet_key")
FERNET_KEY_ROW_ID = "fernet_key"

_fernet: Fernet | None = None
_key_value: str | None = None  # 库行/迁入文件中的 key 原文（一致性观测用）

logger = logging.getLogger("uvicorn.error")


def _load_fernet(raw) -> Fernet:
    """构造 Fernet 实例；内容非法抛 ValueError（调用方决定分支）。"""
    return Fernet(raw)


def _get_fernet() -> Fernet:
    """返回已初始化的 Fernet；未初始化＝启动顺序 bug，快速失败。"""
    if _fernet is None:
        raise RuntimeError(
            "crypto 未初始化：init_crypto() 须在 lifespan 建表/打戳之后、"
            "任何加解密调用之前运行（测试环境由 conftest 夹具负责）。"
        )
    return _fernet


async def init_crypto(session) -> str:
    """启动期钥匙初始化（lifespan 与测试夹具调用；幂等）。

    顺序（spec：model-api-config「Key 静态加密与钥匙同库自包含」）：
    1. 库内有钥匙行 → 装载（行内容非法＝库被手改，异常即快速失败）。
    2. 库内无钥匙行：
       a. 旧钥匙文件存在且内容合法 → 原样迁入库（零重加密，"migrated"）；
       b. 文件不存在或内容非法（空/截断/非 Fernet）→ 生成新钥匙入库
          （"generated"；文件原样保留，不删）。
    并发首启同时 INSERT 撞 PK → 以先落库者为准，重读装载（迁移来源相同
    则内容一致，零分叉）。

    返回启动结果："ready" / "migrated" / "generated"。
    初始化失败抛 RuntimeError（调用方不捕获即快速失败，不静默降级）。
    """
    global _fernet, _key_value
    if _fernet is not None:
        return "ready"

    from models.app_meta import AppMeta

    def _read_legacy_file():
        if not os.path.isfile(_FERNET_KEY_FILE):
            return None
        try:
            return Path(_FERNET_KEY_FILE).read_bytes().strip()
        except OSError as e:
            logger.warning("crypto: 旧钥匙文件不可读（%s），忽略：%s", _FERNET_KEY_FILE, e)
            return None

    async def _load_row():
        row = (
            await session.execute(
                select(AppMeta).where(AppMeta.key == FERNET_KEY_ROW_ID)
            )
        ).scalar_one()
        return row

    async def _insert_key(value: str) -> bool:
        session.add(AppMeta(key=FERNET_KEY_ROW_ID, value=value))
        try:
            await session.commit()
            return True
        except IntegrityError:
            # 并发首启：先到者已落库——丢弃本地值，重读装载
            await session.rollback()
            return False

    try:
        row = (
            await session.execute(
                select(AppMeta).where(AppMeta.key == FERNET_KEY_ROW_ID)
            )
        ).scalar_one_or_none()

        if row is not None:
            outcome = "ready"
            key_value = row.value
        else:
            legacy = _read_legacy_file()
            if legacy is not None:
                try:
                    _load_fernet(legacy)  # 合法性校验；非法 → ValueError → 按不存在处理
                except ValueError:
                    logger.warning(
                        "crypto: 旧钥匙文件内容非法（原样保留），改用新钥匙：%s",
                        _FERNET_KEY_FILE,
                    )
                    legacy = None
            if legacy is not None:
                key_value = legacy.decode("ascii")
                if await _insert_key(key_value):
                    outcome = "migrated"
                else:
                    key_value = (await _load_row()).value  # 并发首启：装载先到者
            else:
                key_value = Fernet.generate_key().decode("ascii")
                if await _insert_key(key_value):
                    outcome = "generated"
                else:
                    key_value = (await _load_row()).value

        _key_value = key_value
        _fernet = _load_fernet(_key_value)

        # 双源一致性观测（只报事实，不碰钥匙内容）：文件在＋行在＋内容不等
        legacy_now = _read_legacy_file()
        if legacy_now is not None and legacy_now.decode("ascii", "replace") != _key_value:
            logger.warning(
                "crypto: 数据目录钥匙文件与库内钥匙行不一致（以库内为准）——"
                "该数据目录可能被新旧版本混用，旧版本构建可能无法解密库内密文"
            )

        logger.info("crypto: key %s (db row=%s)", outcome, FERNET_KEY_ROW_ID)

        # 死文配置计数（判定层之外的补偿面）：enc: 密文解不出明文的配置数。
        try:
            from models.api_config import ApiConfig

            rows = (
                (
                    await session.execute(
                        select(ApiConfig).where(
                            ApiConfig.status == "active",
                            ApiConfig.api_key.like("enc:%"),
                        )
                    )
                )
                .scalars()
                .all()
            )
            dead = sum(1 for c in rows if not decrypt_api_key(c.api_key))
            if dead:
                logger.warning(
                    "crypto: %d 条配置的 API Key 无法解密（加密钥匙已更换/丢失）"
                    "——请在「模型配置」重新粘贴保存",
                    dead,
                )
        except SQLAlchemyError:
            pass

        return outcome
    except SQLAlchemyError as e:
        _fernet = None
        _key_value = None
        raise RuntimeError(f"crypto 钥匙初始化失败（库读写异常）：{e}") from e


def _reset_for_tests() -> None:
    """清空模块级钥匙（死文态/迁移态用例的钥匙轮转依赖；仅测试使用）。"""
    global _fernet, _key_value
    _fernet = None
    _key_value = None


def encrypt_api_key(plaintext: str) -> str:
    """Encrypt an API key for storage (``enc:``-prefixed Fernet token)."""
    if not plaintext:
        return ""
    f = _get_fernet()
    token = f.encrypt(plaintext.encode("utf-8"))
    return "enc:" + token.decode("utf-8")


def decrypt_api_key(stored: str) -> str:
    """Decrypt an API key retrieved from storage.

    Expects a string prefixed with ``enc:`` (produced by ``encrypt_api_key``).
    Unprefixed values are returned as-is (plaintext fallback).
    Undecryptable ciphertext (key rotated/lost) returns "" — callers treat it
    as "no usable key" and the gating layer guides re-entry.
    """
    if not stored:
        return ""
    if not stored.startswith("enc:"):
        return stored  # Plaintext fallback
    f = _get_fernet()
    try:
        return f.decrypt(stored[4:].encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""
