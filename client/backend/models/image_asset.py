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
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
    cover_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_config_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("image_configs.id", ondelete="SET NULL"), nullable=True
    )
    image_model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CharacterImageSettings(Base):
    """角色级图像设置 — 头像描述与种子；画风/封面描述仍在书级。"""

    __tablename__ = "character_image_settings"

    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True
    )
    avatar_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
