"""六概念 payload 校验——字段名＝消费端真实键；extra=forbid；槽位与字段一致。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


# ─── 文风 ───────────────────────────────────────────────
class StylePayload(BaseModel):
    """一个声音侧面。消费端键：style.role / style_samples。"""

    model_config = {"extra": "forbid"}

    # rule＝拆书场景规则（boss 2026-11-07 承接表：一条场景规则一条文风实例，
    # 如「战斗短句」），text 承载「名字：怎么写」
    slot: Literal["role", "tone", "pov", "register", "sample", "rule"]
    role: str | None = Field(None, max_length=120)
    text: str | None = Field(None, max_length=500)
    sample: str | None = Field(None, max_length=500)
    sample_note: str | None = Field(None, max_length=80)
    # rule 槽结构化（2026-11-08 与世界同拍板：名字/内容/章证据/可信度分立，不挤一团）
    name: str | None = Field(None, max_length=60)
    how: str | None = Field(None, max_length=300)
    evidence_ch: str | None = Field(None, max_length=60)
    confidence: Literal["high", "mid", "low"] | None = None

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
    rule: str | None = Field(None, max_length=160)
    craft: str | None = Field(None, max_length=160)
    banned: str | None = Field(None, max_length=50)
    banned_alt: str | None = Field(None, max_length=50)
    tic_pattern: str | None = Field(None, max_length=200)
    tic_severity: Literal["high", "medium", "low"] | None = None
    # 结构化（2026-11-08 与世界同拍板：名字/内容/章证据/可信度分立）
    name: str | None = Field(None, max_length=60)
    how: str | None = Field(None, max_length=300)
    evidence_ch: str | None = Field(None, max_length=60)
    confidence: Literal["high", "mid", "low"] | None = None

    @model_validator(mode="after")
    def check_slot_fields(self):
        mapping = {"rule": "rule", "craft": "craft", "banned_word": "banned", "tic": "tic_pattern"}
        required_key = mapping.get(self.slot)
        if required_key and not getattr(self, required_key, None):
            raise ValueError(f"slot={self.slot} 必填 {required_key} 字段")
        return self


# ─── 世界设定 ────────────────────────────────────────────
class WorldPayload(BaseModel):
    """一个分区的一条事实。消费端键：world V2 8 键（no_power 不开放）。

    2026-11-08 结构化扩展（boss「内容=实际案例、字段分立」拍板）：name＝条目名
    （势力名/事件名/规则名），evidence_ch＝章证据，confidence＝拆书可信度——
    此前这三样粘在 content 正文尾（「（第41章；confidence:mid）」）。
    """

    model_config = {"extra": "forbid"}

    part: Literal["stage", "power", "cost", "factions", "history", "extra", "constraint"]
    content: str = Field(..., max_length=300)
    hard: bool = False
    name: str | None = Field(None, max_length=60)
    evidence_ch: str | None = Field(None, max_length=60)
    confidence: Literal["high", "mid", "low"] | None = None


# ─── 角色设定 ────────────────────────────────────────────
class CharacterPayload(BaseModel):
    """一个可复用的原型/造法。渲染：逐格复制进角色卡表单。

    扁平形态＝角色库全量（c-kb-character-migration 6.1）：
    - archetype＝卡名；persona 一句人设
    - 档案八格（DOSSIER_KEYS 同源）：gender/age/race/faction/look/speech/background/plot
    - 认知十一格（COG_KEYS 同源）：w1/w5/s1/s5/v1/p2/p6/p3/p4/b1/e3
    - relation_slot（关系槽位）/arc（成长弧线）为知识侧标注，不进建卡预填
    """

    model_config = {"extra": "forbid"}

    archetype: str = Field(..., max_length=50)
    persona: str | None = Field(None, max_length=300)
    # 卡级分类（角色库 UI 数据源切换 6.4：与库卡同构；aliases 逐条 clamp 50）
    aliases: list[str] | None = Field(None, max_length=20)
    role: str | None = Field(None, max_length=10)
    kind: str | None = Field(None, max_length=20)

    @field_validator("aliases")
    @classmethod
    def _clamp_aliases(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [a.strip()[:50] for a in v if str(a).strip()]
    # 档案八格（逐格 300，与 character_service 白名单 clamp 同口径）
    gender: str | None = Field(None, max_length=300)
    age: str | None = Field(None, max_length=300)
    race: str | None = Field(None, max_length=300)
    faction: str | None = Field(None, max_length=300)
    look: str | None = Field(None, max_length=300)
    speech: str | None = Field(None, max_length=300)
    background: str | None = Field(None, max_length=300)
    plot: str | None = Field(None, max_length=300)
    # 认知十一格
    w1: str | None = Field(None, max_length=300)
    w5: str | None = Field(None, max_length=300)
    s1: str | None = Field(None, max_length=300)
    s5: str | None = Field(None, max_length=300)
    v1: str | None = Field(None, max_length=300)
    p2: str | None = Field(None, max_length=300)
    p6: str | None = Field(None, max_length=300)
    p3: str | None = Field(None, max_length=300)
    p4: str | None = Field(None, max_length=300)
    b1: str | None = Field(None, max_length=300)
    e3: str | None = Field(None, max_length=300)
    # 知识侧标注
    relation_slot: str | None = Field(None, max_length=80)
    arc: str | None = Field(None, max_length=160)


# ─── 手法 ────────────────────────────────────────────────
class TechniquePayload(BaseModel):
    """一个可挑选的打法。消费端：build_technique_block() → user 提示词。"""

    model_config = {"extra": "forbid"}

    instruction: str = Field(..., max_length=240)
    negative: str | None = Field(None, max_length=200)
    scene: str = Field(..., max_length=20)
    emotion: str | None = Field(None, max_length=20)
    steps: list[str] | None = Field(None, max_length=5)


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
