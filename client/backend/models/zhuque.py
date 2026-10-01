"""朱雀检测结果存档（c-zhuque-persist）。

每行＝某章最近一次朱雀检测的完整结果（重检覆盖，同章至多一行）。
检测结论为作者资产：随章持久化、进备份完整迁移（用户拍板 2026-10-01，
翻转 c-zhuque-ai-detect 的「不落库」）；陈旧判定不在此表——载入方按
prose_hash 与当前正文指纹比对（一致彩色恢复、不一致置灰＋重检）。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class ZhuqueResultArchive(Base):
    """章粒度朱雀检测存档——同章一行（chapter_id 主键），重检 upsert 覆盖。"""

    __tablename__ = "zhuque_results"

    chapter_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("chapters.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # 送检时正文指纹（规范化管道 sha256）：载入方与实时指纹比对定彩色/置灰
    prose_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # 完整检测响应 JSON（ok/prose_hash/summary/segments/usage_tokens 原样）
    result: Mapped[str] = mapped_column(Text, nullable=False)
    # ISO-8601 UTC 字符串（带 +00:00）：SQLite DateTime 不存时区，字符串保真
    checked_at: Mapped[str] = mapped_column(String(40), nullable=False)
