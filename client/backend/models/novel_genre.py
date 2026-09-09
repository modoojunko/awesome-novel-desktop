"""题材关系化模型（genre-signup-redesign D19，方案 A）。

四张表：
- `genre_vocab`         候选源字典（稳定 slug 主键，kind=promise/forbidden/battlefield）
- `novel_genre`         本书题材（1:1 novel，五字段）
- `novel_genre_forbidden` / `novel_genre_battlefield`  关联表（引用 vocab 或自定义文本）

对外 API 契约仍是五字段 JSON（`GET/PUT /settings/genre`），关系化只在存储层
（见 genres/novel_genre_service.py 的单事务组装/拆分）。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class GenreVocab(Base):
    """候选源字典（预置 + 用户自定义）。id 为稳定 slug，禁止用序号。"""

    __tablename__ = "genre_vocab"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 稳定 slug
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # promise|forbidden|battlefield
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_preset: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class NovelGenre(Base):
    """本书题材（1:1 novel）。cost_ratio 允许 NULL 或 1–10。"""

    __tablename__ = "novel_genre"
    __table_args__ = (
        CheckConstraint(
            "cost_ratio IS NULL OR (cost_ratio BETWEEN 1 AND 10)",
            name="ck_novel_genre_cost_ratio",
        ),
    )

    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    core_promise: Mapped[str | None] = mapped_column(String(60), nullable=True)
    promise_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cost_ratio: Mapped[int | None] = mapped_column(Integer, nullable=True)
    track: Mapped[str | None] = mapped_column(String(300), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class NovelGenreForbidden(Base):
    """禁项关联：vocab_id（预置/自定义词汇）或 custom_text，恰一非空。"""

    __tablename__ = "novel_genre_forbidden"
    __table_args__ = (
        CheckConstraint(
            "(vocab_id IS NULL) != (custom_text IS NULL)",
            name="ck_novel_genre_forbidden_one_of",
        ),
        UniqueConstraint("novel_id", "vocab_id", name="uq_novel_genre_forbidden_vocab"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novel_genre.novel_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vocab_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("genre_vocab.id", ondelete="RESTRICT"), nullable=True
    )
    custom_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class NovelGenreBattlefield(Base):
    """主线战场关联：vocab_id 或 custom_text，恰一非空。"""

    __tablename__ = "novel_genre_battlefield"
    __table_args__ = (
        CheckConstraint(
            "(vocab_id IS NULL) != (custom_text IS NULL)",
            name="ck_novel_genre_battlefield_one_of",
        ),
        UniqueConstraint("novel_id", "vocab_id", name="uq_novel_genre_battlefield_vocab"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    novel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("novel_genre.novel_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vocab_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("genre_vocab.id", ondelete="RESTRICT"), nullable=True
    )
    custom_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
