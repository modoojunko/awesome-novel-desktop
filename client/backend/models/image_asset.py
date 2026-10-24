"""图像配置与资产表（c-cover-avatar 阶段 1）。

配置与写作 api_configs 物理隔离；资产字节与元数据分表，列表查询不背 BLOB。
阶段 1 不含生成/测试/试画，只做配置 CRUD、上传、采用、撤销、签名读取和每书绑定。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ImageConfig(Base):
    """图像模型配置 — 独立于写作 ApiConfig，Key 复用 api_configs/crypto 加密。"""

    __tablename__ = "image_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_image_configs_user_name"),
        Index(
            "uq_image_config_default",
            "user_id",
            unique=True,
            sqlite_where=text("is_default = 1 AND status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    api_key: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    default_model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    models: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    declared_capabilities: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    last_test_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_test_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ImageAsset(Base):
    """逻辑资产 — 一张图一条元数据；字节在 ImageAssetBlob 按 variant 存。"""

    __tablename__ = "image_assets"
    __table_args__ = (
        Index("ix_image_assets_novel_kind", "novel_id", "kind", "status"),
        Index("ix_image_assets_character_kind", "character_id", "kind", "status"),
        Index(
            "uq_image_asset_current_cover",
            "novel_id",
            unique=True,
            sqlite_where=text("kind = 'cover' AND status = 'current'"),
        ),
        Index(
            "uq_image_asset_current_avatar",
            "character_id",
            unique=True,
            sqlite_where=text("kind = 'avatar' AND status = 'current'"),
        ),
        Index(
            "uq_image_asset_previous_cover",
            "novel_id",
            unique=True,
            sqlite_where=text("kind = 'cover' AND status = 'previous'"),
        ),
        Index(
            "uq_image_asset_previous_avatar",
            "character_id",
            unique=True,
            sqlite_where=text("kind = 'avatar' AND status = 'previous'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    novel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    character_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # cover | avatar
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="candidate", server_default="candidate"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str] = mapped_column(String(40), nullable=False, default="image/webp")
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    style_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    undo_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    undo_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("image_jobs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    adopted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # candidate=24h 后清；previous=8s 撤销窗口后清；current 恒为 NULL
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ImageAssetBlob(Base):
    """资产字节 — (asset_id, variant) 复合主键；variant=full|thumb。"""

    __tablename__ = "image_asset_blobs"

    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("image_assets.id", ondelete="CASCADE"), primary_key=True
    )
    variant: Mapped[str] = mapped_column(String(10), primary_key=True)  # full | thumb
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class BookImageSettings(Base):
    """书级图像设置 — 画风/封面描述 + 本书绑定的图像配置与模型。"""

    __tablename__ = "book_image_settings"

    novel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("novels.id", ondelete="CASCADE"), primary_key=True
    )
    style_key: Mapped[str] = mapped_column(String(40), nullable=False, default="ink")
    cover_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_config_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("image_configs.id", ondelete="SET NULL"), nullable=True
    )
    image_model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CharacterImageSettings(Base):
    """角色级图像设置 — 头像描述；画风/封面描述仍在书级。"""

    __tablename__ = "character_image_settings"

    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    avatar_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ImageJob(Base):
    """图像生成任务 — 独立于写作 job_runner 单飞槽，状态落在库里可恢复。

    target_type/target_id 是幂等键的“同一目标”口径：book 封面、character 头像、
    batch 批量头像。部分唯一索引保证同一目标同时最多一个 queued/running。
    """

    __tablename__ = "image_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_image_job_idempotency"),
        Index("ix_image_jobs_status_created", "status", "created_at"),
        Index("ix_image_jobs_novel", "novel_id", "created_at"),
        Index(
            "uq_image_job_active_target",
            "target_type",
            "target_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    novel_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("novels.id", ondelete="CASCADE"), nullable=False
    )
    character_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # book|character|batch
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(20), nullable=False, default="generate"
    )  # generate|test|batch
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # cover|avatar
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", server_default="queued"
    )  # queued|running|completed|failed|cancelled
    image_config_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("image_configs.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    style_key: Mapped[str | None] = mapped_column(String(40), nullable=True)
    prompt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_n: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    produced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    billed_n: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancelled_billed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ImageBatchItem(Base):
    """批量头像逐项账 — 每角色一行；取消时已完成候选保留，未完成收敛终态。"""

    __tablename__ = "image_batches"
    __table_args__ = (
        UniqueConstraint("job_id", "item_index", name="uq_image_batch_item_index"),
        Index("ix_image_batches_job_status", "job_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("image_jobs.id", ondelete="CASCADE"), nullable=False
    )
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )  # pending|running|completed|failed|cancelled|cancelled_billed
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    produced_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    billed_n: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
