from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, func

from app.models.base import Base
from app.models.types import BigIntPK


class UserORM(Base):
    __tablename__ = "users"

    id                  = Column(BigIntPK, autoincrement=True, primary_key=True)
    username            = Column(String(128), nullable=False, unique=True, index=True)
    password_hash       = Column(String(256), nullable=False)
    security_question   = Column(Text, default="", server_default="")
    security_answer_hash= Column(String(256), default="", server_default="")
    status              = Column(String(32), default="active", server_default="active", index=True)
    theme               = Column(String(32), default="", server_default="")
    # 凭据版本（s-security-hardening R5）：改密/改密保/注销执行时自增或置哨兵，
    # 存量令牌（无 ver 声明）按 0 比对——升级不误伤
    token_version       = Column(Integer, nullable=False, default=0, server_default="0")
    created_at          = Column(DateTime, server_default=func.now())
    # 账号自助注销（account-deletion）：中文枚举沿 codes 风格（design D1）
    deletion_status     = Column(String(32), default="正常", server_default="正常", index=True)
    deletion_requested_at = Column(DateTime, nullable=True)
    deletion_deadline   = Column(DateTime, nullable=True)
    deletion_waive_assets = Column(Boolean, default=False, server_default="0")
    # 注册协议版本留痕（legal-four-docs）：注册时勾选的协议版本
    agreement_version = Column(String(32), default="", server_default="")
