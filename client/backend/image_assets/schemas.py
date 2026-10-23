"""图像配置/资产请求体（阶段 1）。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImageConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider: str
    base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    models: list[str] = []
    declared_capabilities: dict = {}
    is_default: bool = False


class ImageConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None
    models: list[str] | None = None
    declared_capabilities: dict | None = None
    is_default: bool | None = None


class BookImageSettingsBody(BaseModel):
    style_key: str = "ink"
    cover_prompt: str = ""
    cover_seed: int | None = Field(default=None, ge=0, le=2**31 - 1)
    image_config_id: str | None = None
    image_model: str = ""


class CharacterImageSettingsBody(BaseModel):
    avatar_prompt: str | None = None
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class AdoptBody(BaseModel):
    variant: str = "full"
    token: str = ""
    undo_token: str = ""
