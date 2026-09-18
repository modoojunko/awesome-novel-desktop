from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class User:
    """用户实体。不包含密码哈希方法，只做状态判断。"""
    username: str
    password_hash: str
    status: str                # "active" | "locked"
    security_question: str
    security_answer_hash: str
    created_at: datetime | None = None
    theme: str = ""            # 界面主题 key（空 = 默认 teal，见 identity/theme.py）
    # 账号自助注销状态（design D1）：空值视为 正常（存量行兼容）
    deletion_status: str = "正常"     # 正常 | 注销撤销期 | 已注销
    deletion_requested_at: datetime | None = None
    deletion_deadline: datetime | None = None
    deletion_waive_assets: bool = False
    agreement_version: str = ""  # 注册时勾选的法律文件版本（legal-four-docs）
    token_version: int = 0       # 凭据版本（R5）：签发进令牌，鉴权比对；改密/改密保/注销时前进

    def is_active(self) -> bool:
        return self.status == "active"

    def is_locked(self) -> bool:
        return self.status == "locked"

    # ── 注销状态（account-deletion）──
    @property
    def effective_deletion_status(self) -> str:
        return self.deletion_status or "正常"

    def is_deletion_pending(self) -> bool:
        """处于 15 天撤销期（已申请、未执行）。"""
        return self.effective_deletion_status == "注销撤销期"

    def is_deleted(self) -> bool:
        """注销已执行（去标识化完成）。"""
        return self.effective_deletion_status == "已注销"
