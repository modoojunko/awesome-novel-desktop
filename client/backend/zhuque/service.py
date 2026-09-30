"""朱雀检测配置与章节检测编排（c-zhuque-ai-detect）。

- Key 复用 ``api_configs`` 表，``vendor="zhuque"`` 单槽位：专用端点内部固定
  name/vendor/base_url（作者只粘贴 Key）；保存＝upsert（查重键 ``(user_id, name)``
  与表唯一约束一致，软删行复活；作者大模型配置撞固定名——active/deleted 一律 409）。
- ``check_chapter``：读落盘正文（由前端调用方保证 flush）→ 规范化 → classify →
  上游 order 对齐本地非空段；分段数不符 502；结果不落库（响应即弃，前端内存消费）。
- 同章在途拒绝：进程内 registry（键 user_id+chapter_ref），409
  ``zhuque_check_in_progress``；请求结束/异常时释放。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api_configs.crypto import decrypt_api_key, encrypt_api_key
from api_configs.schemas import mask_api_key
from models.api_config import ApiConfig
from zhuque import client as zhuque_client
from zhuque.segmentation import (
    MAX_PROSE_CHARS,
    canonical_text,
    fingerprint,
    split_paragraphs,
)

ZHUQUE_NAME = "朱雀 AI 检测"
ZHUQUE_VENDOR = "zhuque"
ZHUQUE_BASE_URL = zhuque_client.DEFAULT_BASE_URL

# 同章在途 registry：(user_id, project_id, chapter_ref) -> True
_inflight: set[tuple[str, str, str]] = set()
_inflight_lock = asyncio.Lock()

# 上游 label → 语义（spec 契约：0=人工 1=AI 2=疑似）
LABEL_HUMAN, LABEL_AI, LABEL_SUSPECT = 0, 1, 2


async def get_zhuque_config(
    db: AsyncSession, user_id: str
) -> ApiConfig | None:
    """取作者的朱雀配置行（active 或 deleted；单槽位至多一行）。"""
    result = await db.execute(
        select(ApiConfig).where(
            ApiConfig.user_id == user_id,
            ApiConfig.name == ZHUQUE_NAME,
            ApiConfig.vendor == ZHUQUE_VENDOR,
        )
    )
    return result.scalars().first()


async def get_config_status(db: AsyncSession, user_id: str) -> dict[str, Any]:
    """配置卡状态：configured/掩码/上次测试（前端就绪・引导分流的事实源）。"""
    cfg = await get_zhuque_config(db, user_id)
    if cfg is None or cfg.status == "deleted":
        return {"configured": False, "show": None}
    plain = decrypt_api_key(cfg.api_key)
    return {
        "configured": bool(plain),
        "api_key_masked": mask_api_key(plain) if plain else "",
        "last_test_status": cfg.last_test_status,
        "last_test_error": cfg.last_test_error,
        "last_tested_at": cfg.last_tested_at.isoformat() if cfg.last_tested_at else None,
    }


async def save_config(
    db: AsyncSession, user_id: str, api_key: str
) -> dict[str, Any]:
    """单槽 upsert：active 更新 / 软删复活 / 新建。返回配置卡状态。"""
    key_plain = (api_key or "").strip()
    if not key_plain:
        raise ValueError("API Key 不能为空")

    cfg = await get_zhuque_config(db, user_id)
    if cfg is not None and cfg.vendor != ZHUQUE_VENDOR:
        # 作者的大模型配置恰与固定名同名（active/deleted 一律 409，复活仅限 zhuque 行）
        raise ValueError("该名称已被其他配置使用，请先改名后再配置朱雀")
    # 同名但非朱雀 vendor 的行（含软删）：唯一约束 (user_id,name) 不含 vendor，insert 必撞
    result = await db.execute(
        select(ApiConfig).where(ApiConfig.user_id == user_id, ApiConfig.name == ZHUQUE_NAME)
    )
    other = result.scalars().first()
    if other is not None and other.vendor != ZHUQUE_VENDOR:
        raise ValueError("该名称已被其他配置使用，请先改名后再配置朱雀")

    enc = encrypt_api_key(key_plain)
    if cfg is None:
        cfg = ApiConfig(
            user_id=user_id,
            name=ZHUQUE_NAME,
            vendor=ZHUQUE_VENDOR,
            vendor_display_name="朱雀 AI 检测",
            vendor_override=None,
            base_url=ZHUQUE_BASE_URL,
            api_key=enc,
            status="active",
        )
        db.add(cfg)
    else:
        cfg.status = "active"
        cfg.api_key = enc
        cfg.base_url = ZHUQUE_BASE_URL
        cfg.last_test_status = None
        cfg.last_test_error = None
        cfg.last_tested_at = None
    try:
        await db.commit()
        await db.refresh(cfg)
    except IntegrityError as e:  # 并发双保存：约束兜底后重查转更新
        await db.rollback()
        cfg = await get_zhuque_config(db, user_id)
        if cfg is None or cfg.vendor != ZHUQUE_VENDOR:
            raise ValueError("保存冲突，请重试") from e
        cfg.status = "active"
        cfg.api_key = enc
        await db.commit()
        await db.refresh(cfg)
    return await get_config_status(db, user_id)


async def delete_config(db: AsyncSession, user_id: str) -> bool:
    """软删（可恢复路径沿用既有 restore 语义）；无配置返回 False。"""
    cfg = await get_zhuque_config(db, user_id)
    if cfg is None or cfg.status == "deleted":
        return False
    cfg.status = "deleted"
    await db.commit()
    return True


async def test_config(db: AsyncSession, user_id: str) -> dict[str, Any]:
    """最小 classify 连通性测试（消耗极少额度）；持久化 last_test_*。"""
    cfg = await get_zhuque_config(db, user_id)
    if cfg is None or cfg.status == "deleted":
        return {"ok": False, "status": "not_configured", "error": "尚未配置朱雀 Key"}
    plain = decrypt_api_key(cfg.api_key)
    try:
        await zhuque_client.classify("ping", plain)
        cfg.last_test_status = "ok"
        cfg.last_test_error = None
    except zhuque_client.ZhuqueUpstreamError as e:
        cfg.last_test_status = "auth_error" if e.status in (401, 403) else (
            "rate_limited" if e.status == 429 else ("timeout" if e.status == 0 else "network_error")
        )
        cfg.last_test_error = e.message
    cfg.last_tested_at = datetime.now(UTC)
    await db.commit()
    return {
        "ok": cfg.last_test_status == "ok",
        "status": cfg.last_test_status,
        "error": cfg.last_test_error,
    }


async def check_chapter(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str,
    chapter_ref: str,
    prose: str,
) -> dict[str, Any]:
    """整章检测：规范化 → classify → 段落对齐。结果不落库，响应即弃。"""
    cfg = await get_zhuque_config(db, user_id)
    if cfg is None or cfg.status == "deleted":
        raise ValueError("zhuque_not_configured")
    plain = decrypt_api_key(cfg.api_key)
    if not plain:
        raise ValueError("zhuque_not_configured")

    text = canonical_text(prose)
    if not text:
        raise ValueError("empty_prose")
    if len(text) > MAX_PROSE_CHARS:
        raise ValueError("prose_too_long")

    key = (user_id, project_id, chapter_ref)
    async with _inflight_lock:
        if key in _inflight:
            raise ValueError("zhuque_check_in_progress")
        _inflight.add(key)
    try:
        data = await zhuque_client.classify(text, plain)
    finally:
        async with _inflight_lock:
            _inflight.discard(key)

    seg_labels = data.get("segment_labels") or []
    paragraphs = split_paragraphs(prose)
    if len(seg_labels) != len(paragraphs):
        raise ValueError("segment_mismatch")

    usage = data.get("makers_models_usage") or data.get("usage") or {}
    usage_tokens = int(usage.get("total_tokens") or 0)
    if usage_tokens:
        # 本地留痕（独立 operation/model，用量汇总已排除；月度口径引导腾讯云控制台）
        from api_configs.usage import record_usage

        await record_usage(
            db,
            user_id=user_id,
            project_id=project_id,
            api_config_id=cfg.id,
            operation="zhuque-check",
            model="zhuque",
            tokens_out=usage_tokens,
        )
    ratios = data.get("labels_ratio") or {}
    return {
        "ok": True,
        "prose_hash": fingerprint(prose),
        "summary": {
            "human_ratio": float(ratios.get("0", 0) or 0),
            "suspect_ratio": float(ratios.get("2", 0) or 0),
            "ai_ratio": float(ratios.get("1", 0) or 0),
            "softmax_confidence": float(data.get("softmax_confidence") or 0),
        },
        "segments": [
            {
                "paragraph_index": i,
                "label": int(seg.get("label", 0)),
                "confidence": float(seg.get("conf", 0) or 0),
            }
            for i, seg in enumerate(seg_labels)
        ],
        "usage_tokens": usage_tokens,
    }
