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


class ImageConfigTestBody(BaseModel):
    """连接测试（c-image-config-ux-fix）：全部可省，带 config_id 时缺省用存量值。"""

    config_id: str | None = None
    provider: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    default_model: str | None = None


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


class ImageJobCreate(BaseModel):
    kind: str = Field(pattern="^(cover|avatar)$")
    character_id: str | None = None
    n: int = Field(default=2, ge=1, le=4)
    purpose: str = Field(default="generate", pattern="^(generate|test)$")


class AvatarBatchCreate(BaseModel):
    character_ids: list[str] = Field(min_length=1, max_length=100)
