"""Pydantic schemas for API Key Config management."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ── Helpers ────────────────────────────────────────────────────────────────

# 接口格式（wire format）：openai | anthropic。请求体里 None = 未传（旧前端），
# 服务层按 vendor/URL 推荐值兜底，与旧版运行时推断等价。
ApiFormat = Literal["openai", "anthropic"]

KNOWN_VENDORS = {
    "openai",
    "anthropic",
    "deepseek",
    "glm",
    "kimi",
    "qwen",
    "ollama",
    "openai-compat",
}


def mask_api_key(key: str) -> str:
    """Mask an API key: show first 8 and last 4 characters."""
    if len(key) <= 16:
        if len(key) <= 4:
            return "****"
        return key[:4] + "****" + key[-4:]
    return key[:8] + "****" + key[-4:]


# ── Request bodies ─────────────────────────────────────────────────────────


class CreateApiConfigBody(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    vendor_id: str
    base_url: str
    api_key: str = ""
    vendor_override: str | None = None
    api_format: ApiFormat | None = None

    @field_validator("vendor_id")
    @classmethod
    def _validate_vendor(cls, v: str) -> str:
        if v not in KNOWN_VENDORS:
            raise ValueError(
                f"Unknown vendor_id '{v}'. Must be one of: {', '.join(sorted(KNOWN_VENDORS))}"
            )
        return v


class UpdateApiConfigBody(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    vendor_override: str | None = None
    api_format: ApiFormat | None = None
    # 手动补模型清单（部分 Anthropic 兼容端点不提供 /models 列表）
    models: list[str] | None = None


class SetAiModelBody(BaseModel):
    api_config_id: str | None = None
    model: str | None = None


class ApplyModelToAllBody(BaseModel):
    api_config_id: str
    model: str


# ── Response schemas ───────────────────────────────────────────────────────


class ApiConfigResponse(BaseModel):
    id: str
    name: str
    vendor: str
    vendor_display_name: str
    vendor_override: str | None = None
    api_format: str = "openai"
    base_url: str
    api_key_masked: str
    status: str
    last_test_status: str | None = None
    last_test_error: str | None = None
    last_tested_at: str | None = None
    models: list[str] = []
    models_updated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_orm_row(cls, row: Any) -> ApiConfigResponse:
        """Build from a DB row or model instance."""
        models_list: list[str] = []
        if row.get("models"):
            try:
                parsed = json.loads(row["models"])
                if isinstance(parsed, list):
                    models_list = parsed
            except (json.JSONDecodeError, TypeError):
                pass

        raw_key = row.get("api_key", "")
        return cls(
            id=row["id"],
            name=row["name"],
            vendor=row["vendor"],
            vendor_display_name=row.get("vendor_display_name", ""),
            vendor_override=row.get("vendor_override"),
            api_format=row.get("api_format", "openai") or "openai",
            base_url=row.get("base_url", ""),
            api_key_masked=mask_api_key(raw_key),
            status=row.get("status", "active"),
            last_test_status=row.get("last_test_status"),
            last_test_error=row.get("last_test_error"),
            last_tested_at=_iso_or_none(row.get("last_tested_at")),
            models=models_list,
            models_updated_at=_iso_or_none(row.get("models_updated_at")),
            created_at=_iso_or_none(row.get("created_at")),
            updated_at=_iso_or_none(row.get("updated_at")),
        )


class StatusEntry(BaseModel):
    id: str
    status: str
    last_test_status: str | None = None
    last_test_error: str | None = None
    last_tested_at: str | None = None
    models: list[str] = []
    api_key_masked: str = ""
    vendor: str = ""
    api_format: str = "openai"


class DeleteConfigResponse(BaseModel):
    ok: bool = True
    affected_projects: int = 0
    affected_names: list[str] = []


class UsageSummaryResponse(BaseModel):
    total_all_time: int = 0
    total_this_month: int = 0
    total_today: int = 0
    by_config: list[dict] = []
    queried_at: str | None = None


class PerConfigUsageResponse(BaseModel):
    total_tokens: int = 0
    breakdown: list[dict] = []


class PerProjectUsageResponse(BaseModel):
    total_tokens: int = 0
    by_model: list[dict] = []
    by_operation: list[dict] = []


class ModelHistoryEntry(BaseModel):
    id: str
    changed_at: str
    old_config_name: str | None = None
    new_config_name: str | None = None
    old_model: str | None = None
    new_model: str | None = None
    change_type: str = "switch"


class ModelHistoryResponse(BaseModel):
    history: list[ModelHistoryEntry] = []


class ApplyModelResult(BaseModel):
    succeeded: list[str] = []
    failed: list[dict] = []


class AiModelResponse(BaseModel):
    api_config_id: str | None = None
    model: str | None = None
    config_name: str | None = None


class TestRawBody(BaseModel):
    vendor_id: str
    base_url: str
    api_key: str = ""
    api_format: ApiFormat = "openai"


class TestResultResponse(BaseModel):
    ok: bool
    status: str
    models: list[str] | None = None
    error: str | None = None


def _iso_or_none(val: Any) -> str | None:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)
