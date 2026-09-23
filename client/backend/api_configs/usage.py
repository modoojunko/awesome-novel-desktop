"""TokenLog 写入助手 — AI 调用完成后记录用量（用量统计的数据源）。

所有有 db 上下文的 AI 端点在此收口记录；记录失败不影响主流程（仅 rollback）。
零 token 的调用不落库，避免噪音。
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from models.token_log import TokenLog

logger = logging.getLogger(__name__)


async def record_usage(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None = None,
    api_config_id: str | None = None,
    chapter_id: str | None = None,
    operation: str,
    model: str = "haiku",
    tokens_in: int = 0,
    tokens_out: int = 0,
    force: bool = False,
) -> None:
    # force=True 供失败记账用：调用真实发生但未返回用量（多为零 token）也要留痕；
    # 成功调用零 token 仍早退（防噪音）。
    if not tokens_in and not tokens_out and not force:
        return
    # c-ai-usage-correctness：记账走**独立会话**——实测 flush 失败会把调用方
    # 会话标记为 deactive（必须整体 rollback），SAVEPOINT 保不住主流程写入；
    # 独立会话让记账失败的事故半径严格为自身。`db` 参数保留仅为调用方兼容。
    from db import async_session

    try:
        async with async_session() as session:
            session.add(
                TokenLog(
                    user_id=user_id,
                    project_id=project_id,
                    api_config_id=api_config_id,
                    chapter_id=chapter_id,
                    operation=operation,
                    model=model or "haiku",
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — 记账失败不影响主流程，但必须可观测
        logger.warning(
            "event=usage.write_failed op=%s model=%s", operation, model, exc_info=True
        )
