"""六概念 payload 校验——字段名＝消费端真实键；extra=forbid；槽位与字段一致。"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── 文风 ───────────────────────────────────────────────
class StylePayload(BaseModel):
    """一个声音侧面。消费端键：style.role / style_samples。"""

    model_config = {"extra": "forbid"}

    slot: Literal["role", "tone", "pov", "register", "sample"]
    role: Optional[str] = Field(None, max_length=120)
    text: Optional[str] = Field(None, max_length=500)
    sample: Optional[str] = Field(None, max_length=500)
    sample_note: Optional[str] = Field(None, max_length=80)

    @model_validator(mode="after")
    def check_slot_fields(self):
        if self.slot == "role" and not self.role:
            raise ValueError("slot=role 必填 role 字段")
        if self.slot in ("tone", "pov", "register") and not self.text:
            raise ValueError(f"slot={self.slot} 必填 text 字段")
        if self.slot == "sample" and not self.sample:
            raise ValueError("slot=sample 必填 sample 字段")
        return self


# ─── 文笔 ───────────────────────────────────────────────
class CraftPayload(BaseModel):
    """一条句法规则/手法/禁令。消费端键：style.rules / craft / banned_words / tic_patterns。"""

    model_config = {"extra": "forbid"}

    slot: Literal["rule", "craft", "banned_word", "tic"]
    rule: Optional[str] = Field(None, max_length=160)
    craft: Optional[str] = Field(None, max_length=160)
    banned: Optional[str] = Field(None, max_length=50)
    banned_alt: Optional[str] = Field(None, max_length=50)
    tic_pattern: Optional[str] = Field(None, max_length=200)
    tic_severity: Optional[Literal["high", "medium", "low"]] = None

    @model_validator(mode="after")
    def check_slot_fields(self):
        mapping = {"rule": "rule", "craft": "craft", "banned_word": "banned", "tic": "tic_pattern"}
        required_key = mapping.get(self.slot)
        if required_key and not getattr(self, required_key, None):
            raise ValueError(f"slot={self.slot} 必填 {required_key} 字段")
        return self


# ─── 世界设定 ────────────────────────────────────────────
class WorldPayload(BaseModel):
    """一个分区的一条事实。消费端键：world V2 8 键（no_power 不开放）。"""

    model_config = {"extra": "forbid"}

    part: Literal["stage", "power", "cost", "factions", "history", "extra", "constraint"]
    content: str = Field(..., max_length=300)
    hard: bool = False


# ─── 角色设定 ────────────────────────────────────────────
class CharacterPayload(BaseModel):
    """一个可复用的原型/造法。渲染：逐格复制进角色卡表单。"""

    model_config = {"extra": "forbid"}

    archetype: str = Field(..., max_length=40)
    look: Optional[str] = Field(None, max_length=200)
    background: Optional[str] = Field(None, max_length=200)
    speech: Optional[str] = Field(None, max_length=200)
    w1: Optional[str] = Field(None, max_length=120)
    s1: Optional[str] = Field(None, max_length=120)
    v1: Optional[str] = Field(None, max_length=120)
    relation_slot: Optional[str] = Field(None, max_length=80)
    arc: Optional[str] = Field(None, max_length=160)


# ─── 手法 ────────────────────────────────────────────────
class TechniquePayload(BaseModel):
    """一个可挑选的打法。消费端：build_technique_block() → user 提示词。"""

    model_config = {"extra": "forbid"}

    instruction: str = Field(..., max_length=240)
    negative: Optional[str] = Field(None, max_length=200)
    scene: str = Field(..., max_length=20)
    emotion: Optional[str] = Field(None, max_length=20)
    steps: Optional[list[str]] = Field(None, max_length=5)


# ─── 情节（P1 占位，本期拒收） ──────────────────────────
class PlotPayload(BaseModel):
    """P1 占位。本期只保留概念分类与派生位。"""

    model_config = {"extra": "forbid"}


# ─── 概念 → payload 模型映射 ────────────────────────────
_PAYLOAD_MODELS = {
    "文风": StylePayload,
    "文笔": CraftPayload,
    "世界设定": WorldPayload,
    "角色设定": CharacterPayload,
    "手法": TechniquePayload,
    "情节": PlotPayload,
}


def validate_payload(concept: str, payload: dict) -> dict:
    """按概念校验 payload 并返回清洗后的 dict。校验失败抛 ValueError。"""
    model_cls = _PAYLOAD_MODELS.get(concept)
    if model_cls is None:
        raise ValueError(f"未知概念：{concept}")
    validated = model_cls(**payload)
    return validated.model_dump(exclude_none=True)
