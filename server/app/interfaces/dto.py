"""Pydantic 请求/响应模型。"""
from __future__ import annotations

from pydantic import BaseModel

# ── 请求模型 ──

class AuthorizeRequest(BaseModel):
    username: str
    password: str
    pc_hash: str
    pc_name: str = ""
    device_profile: str = ""
    challenge: str = ""  # 本机配对密钥的 SHA-256（64 位小写 hex；缺失=客户端版本过旧）

class VerifyRequest(BaseModel):
    username: str
    token: str
    pc_hash: str

class PairExchangeRequest(BaseModel):
    """配对交换：pc_hash + 本机配对密钥（明文走 TLS 请求体，绝不入库/入日志）。"""
    pc_hash: str
    device_secret: str


class ResetPasswordRequest(BaseModel):
    username: str
    security_answer: str
    new_password: str

class WebLoginRequest(BaseModel):
    username: str
    password: str

class WebRegisterRequest(BaseModel):
    username: str
    password: str
    security_question: str = ""
    security_answer: str = ""

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class SecurityRequest(BaseModel):
    security_question: str
    security_answer: str

class PreferencesRequest(BaseModel):
    theme: str

class DeviceRemoveRequest(BaseModel):
    id: str = ""
    pc_hash: str = ""

class DeletionRequest(BaseModel):
    password: str
    waive_assets: bool = False  # 显式放弃未消耗权益（未勾选且有权益时受理被拒）

class AssetRefundRequest(BaseModel):
    code_id: str  # 权益级退款申请（每个未消耗权益独立入口）

class DeletionRevokeRequest(BaseModel):
    username: str  # 撤销期账号登录被拒、无 JWT——用户名+密码本身即身份证明（免 token）
    password: str

class AdminScanRequest(BaseModel):
    admin_token: str


# ── 通用响应包装 ──

def ok(data: dict | None = None) -> dict:
    return {"code": 0, "msg": "ok", "data": data or {}}

def fail(code: int = 1, msg: str = "") -> dict:
    return {"code": code, "msg": msg or "请求失败"}
