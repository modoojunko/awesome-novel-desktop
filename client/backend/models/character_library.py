"""角色库族表 — 跨书角色库（c-character-library）。

**DEPRECATED（c-kb-character-migration 批6）**：数据源已迁知识库
（kb_entries concept=角色设定，见 kb/migrate_library.py）；本表原样保留作
迁移源与头像字节存储（CharacterLibraryBlob），UI 数据源切换（6.4）后只读，
删除属后续版本。新代码不要再写本表。

账号级内容资产：不挂 novel_id、不随书级联；uuid 主键 + user_id（全查询按它过滤）。
字段与书内 characters 卡同构（dossier 八格 / cog 三十格 JSON 列，键名冻结）；
库专属分类格：genre 题材 / role 定位（与书内 ROLES 同源四档）/ kind 小类。
头像字节独立表（照 image_asset_blobs 先例，列表查询不背 BLOB）。

带回口径：注册进 models/__init__ 即被迁移引擎列交集搬运覆盖（版本升级存活）；
后续加列一律 nullable 或带 server_default（否则目标 NOT NULL 无默认列触发整表跳过）。
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class CharacterLibrary(Base):
    """库卡 — 与书内角色卡同构的账号级副本；复制语义（收录/导出均复制，不回写）。"""

    __tablename__ = "character_library"
    __table_args__ = (
        # 收录幂等：同一来源（书卡/拆书任务产物卡）只入库一次；
        # 空 src_character_id（手建）不参与唯一——先例：characters 主角部分唯一索引。
        Index(
            "uq_char_lib_src",
            "user_id",
            "src_ref",
            "src_character_id",
            unique=True,
            sqlite_where=text("src_character_id <> ''"),
        ),
        Index("ix_char_lib_user_genre", "user_id", "genre"),
        Index("ix_char_lib_user_role", "user_id", "role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    # JSON array[string]
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # 定位：主角 | 配角 | 反派 | 路人（与书内 ROLES 同源，白名单在服务层）
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="配角")
    # 库专属分类：题材 / 小类（亲人·朋友·挚友·小弟·下人·长辈·敌人·其他）
    genre: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    persona: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # JSON object：dossier 八格 / cog 三十格（键名冻结，同书内 characters）
    dossier: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    cog: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # 来源：book（书内收录）/ deconstruct（拆书收录）/ manual（手建）
    src_kind: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    # 书 id / 拆书任务 id；src_character_id 为来源角色身份键
    src_ref: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    src_character_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    src_novel_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    rev: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CharacterLibraryBlob(Base):
    """库卡头像字节 — (library_id, variant) 复合主键；variant=full|thumb。

    档位：full 512px / thumb 96px（复用 normalize_image("avatar") 的既有档位），
    WebP q85；列表接口只回引用，字节走 GET /{id}/avatar。
    """

    __tablename__ = "character_library_blobs"

    library_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("character_library.id", ondelete="CASCADE"),
        primary_key=True,
    )
    variant: Mapped[str] = mapped_column(String(10), primary_key=True)  # full | thumb
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
