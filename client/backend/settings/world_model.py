"""世界设定契约 v2——领域模型、不变量与纯函数服务（world-setting-v2）。

契约 v2 形状（零 DDL：存 project_settings KV，(root_path, "world") → JSON）：
    {
      "no_power": bool,
      "stage": str, "power": str, "cost": str,
      "history":     [{"key": str, "value": str, "origin"?: str}],
      "factions":    [{"name": str, "note": str}],
      "constraints": [{"key": str, "value": str}],
      "extra":       [{"key": str, "value": str, "origin"?: str}],
      "_legacy"?: Any,   # v1 原文（写边界落入，一个版本周期后清理）；GET 永远剥离
    }

分层：本模块属**领域层**——纯函数零 IO；存储读写归 settings/router.py，
写章注入消费方经 prompt/context.py → render_world_block / render_red_lines。
v1 旧十字段（geography/politics/rules）只在**读边界**经 normalize_world() 归一，
原值在**写边界**由 put_world_merged() 落入 `_legacy`（保留一个版本周期回滚）。
"""

import re

from pydantic import BaseModel, Field, field_validator, model_validator

# ── 上限基线（D3；产品可调，调整即改这里）───────────────────────────────
PARAGRAPH_MAX = 300
KEY_MAX = 20
VALUE_MAX = 200
FACTION_NAME_MAX = 20
FACTION_NOTE_MAX = 200
HISTORY_MAX = 100
FACTIONS_MAX = 6
CONSTRAINTS_MAX = 10
EXTRA_MAX = 50
ORIGIN_MAX = 40
WORLD_BLOCK_BUDGET = 600

SET_NAMES = ("history", "factions", "constraints", "extra")
_SET_LIMITS = {"history": HISTORY_MAX, "factions": FACTIONS_MAX,
               "constraints": CONSTRAINTS_MAX, "extra": EXTRA_MAX}

# 控制字符清洗：value 允许 \n \t（渲染层逐行缩进），key 一律不留
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

V2_KEYS = ("no_power", "stage", "power", "cost", "history", "factions", "constraints", "extra")

V2_EMPTY: dict = {
    "no_power": False,
    "stage": "",
    "power": "",
    "cost": "",
    "history": [],
    "factions": [],
    "constraints": [],
    "extra": [],
}

# 一致性体检检查项（白名单与模板/归一化同源，规格见 world-setting-backend-architecture.md §4.3）
# 现实向去掉力量两把尺，增「现实规则完备」
CHECK_ITEMS_POWER = (
    "简介 × 世界", "题材 × 世界",
    "力量与上限", "代价与边界",
    "铁律 × 简介", "势力立场", "历史自洽",
)
CHECK_ITEMS_REAL = (
    "简介 × 世界", "题材 × 世界",
    "铁律 × 简介", "势力立场", "历史自洽",
    "现实规则完备",
)
_CHECK_STATUS = ("ok", "warn", "miss")


def _clean_key(v) -> str:
    """名目清洗：去首尾空白与全部控制字符（含换行）。"""
    return _CONTROL_RE.sub("", str(v or "")).strip()


def _clean_value(v) -> str:
    """内容清洗：去首尾空白与控制字符（保留换行/制表）。"""
    return _CONTROL_RE.sub("", str(v or "")).strip()


def _is_v1(raw: dict) -> bool:
    """旧十字段形状判定：geography/politics/rules 任一存在且无 v2 段落键。"""
    if not isinstance(raw, dict):
        return False
    if "stage" in raw or "_legacy" in raw:
        return False
    return any(k in raw for k in ("geography", "politics", "rules"))


def _norm_entries(v, limit: int) -> list[dict]:
    """条目列表清洗：dict/异形项安全取 key+value(+origin)，超限截断。"""
    out: list[dict] = []
    if not isinstance(v, list):
        return out
    for item in v[:limit]:
        if isinstance(item, str):
            if item.strip():
                out.append({"key": _clean_key(item)[:KEY_MAX], "value": ""})
            continue
        if not isinstance(item, dict):
            continue
        entry: dict = {"key": _clean_key(item.get("key"))[:KEY_MAX],
                       "value": _clean_value(item.get("value"))[:VALUE_MAX]}
        if item.get("origin"):
            entry["origin"] = _clean_key(item.get("origin"))[:ORIGIN_MAX]
        if entry["key"]:
            out.append(entry)
    return out


def _norm_factions(v, limit: int) -> list[dict]:
    out: list[dict] = []
    if not isinstance(v, list):
        return out
    for item in v[:limit]:
        if isinstance(item, str):
            out.append({"name": _clean_key(item)[:FACTION_NAME_MAX], "note": ""})
            continue
        if not isinstance(item, dict):
            continue
        name = _clean_key(item.get("name", item.get("key")))[:FACTION_NAME_MAX]
        note = _clean_value(item.get("note", item.get("value", item.get("goal"))))[:FACTION_NOTE_MAX]
        if name or note:
            out.append({"name": name, "note": note})
    return out


def _from_v1(raw: dict) -> dict:
    """旧十字段 → v2（映射表见 openspec/changes/world-setting-v2）。纯函数不丢字。"""
    geo = raw.get("geography") if isinstance(raw.get("geography"), dict) else {}
    pol = raw.get("politics") if isinstance(raw.get("politics"), dict) else {}
    rules = raw.get("rules") if isinstance(raw.get("rules"), dict) else {}

    stage = _clean_value(geo.get("scenes"))[:PARAGRAPH_MAX]
    power = _clean_value(rules.get("world"))[:PARAGRAPH_MAX]
    cost = _clean_value(rules.get("personal"))[:PARAGRAPH_MAX]

    geo_bits = "；".join(
        _clean_value(geo.get(k)) for k in ("climate", "limits") if _clean_value(geo.get(k))
    )
    law_bits = "；".join(
        _clean_value(src.get(k))
        for src, keys in ((pol, ("rule", "cost")), (rules, ("society",)))
        for k in keys
        if _clean_value(src.get(k))
    )

    extra: list[dict] = []
    if geo_bits:
        extra.append({"key": "地理与风物", "value": geo_bits})
    if law_bits:
        extra.append({"key": "律法与刑罚", "value": law_bits})
    if _clean_value(pol.get("social")):
        extra.append({"key": "社会与信仰", "value": _clean_value(pol.get("social"))})

    factions: list[dict] = []
    fac_text = _clean_value(pol.get("factions"))
    if fac_text:
        factions.append({"name": "", "note": fac_text[:FACTION_NOTE_MAX]})

    return {
        "no_power": False,
        "stage": stage,
        "power": power,
        "cost": cost,
        "history": [],
        "factions": factions,
        "constraints": [],
        "extra": extra[:EXTRA_MAX],
    }


def normalize_world(raw) -> dict:
    """任意形状 → 契约 v2（**不含 _legacy**）。GET/写章注入/AI 输入组装共用。"""
    if not isinstance(raw, dict) or not raw:
        return dict(V2_EMPTY)
    if _is_v1(raw):
        return _from_v1(raw)
    out = dict(V2_EMPTY)
    for k in V2_KEYS:
        if k in raw:
            out[k] = raw[k]
    out["no_power"] = bool(out.get("no_power"))
    for k in ("stage", "power", "cost"):
        out[k] = _clean_value(out.get(k))[:PARAGRAPH_MAX]
    out["history"] = _norm_entries(out.get("history"), HISTORY_MAX)
    out["factions"] = _norm_factions(out.get("factions"), FACTIONS_MAX)
    out["constraints"] = _norm_entries(out.get("constraints"), CONSTRAINTS_MAX)
    out["extra"] = _norm_entries(out.get("extra"), EXTRA_MAX)
    return out


def read_world(raw) -> dict:
    """GET 口径：归一化 v2 且剥离 `_legacy`。"""
    out = normalize_world(raw)
    out.pop("_legacy", None)
    return out


def put_world_merged(raw, payload: dict) -> dict:
    """写边界：新 v2 payload + 旧原文落 `_legacy`（已在 `_legacy` 的保持不变）。"""
    out = dict(payload)
    if isinstance(raw, dict):
        if "_legacy" in raw:
            out["_legacy"] = raw["_legacy"]
        elif _is_v1(raw):
            out["_legacy"] = raw
    return out


def world_is_filled(raw) -> bool:
    """readiness 新判据：stage/power/cost 任一非空，或任一条目 value 非空。"""
    v2 = normalize_world(raw)
    if any(str(v2.get(k, "")).strip() for k in ("stage", "power", "cost")):
        return True
    return any(
        str(e.get("value", "")).strip()
        for s in SET_NAMES
        for e in (v2.get(s) or [])
        if isinstance(e, dict)
    )


def lore_apply_entries(v2: dict, entries: list[dict]) -> dict:
    """lore-apply：确认条目按 (key, origin) 幂等合并进 v2（factions 按 name）。

    entries：[{key, value, origin?, set}]，set ∈ SET_NAMES。
    条目集满员 → ValueError（router 转 400）；非法 set → ValueError。
    """
    out = dict(v2)
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        set_name = str(e.get("set", "")).strip()
        if set_name not in SET_NAMES:
            raise ValueError(f"未知的条目归属：{set_name}")
        origin = _clean_key(e.get("origin"))[:ORIGIN_MAX] or None
        if set_name == "factions":
            key, value = _clean_key(e.get("key"))[:FACTION_NAME_MAX], _clean_value(e.get("value"))[:FACTION_NOTE_MAX]
        else:
            key, value = _clean_key(e.get("key"))[:KEY_MAX], _clean_value(e.get("value"))[:VALUE_MAX]
        if not key:
            raise ValueError("条目缺少名目")
        target = [dict(x) for x in (out.get(set_name) or [])]
        dup = next(
            (x for x in target
             if (x.get("origin") or None) == origin
             and (x.get("name", x.get("key", "")) == key if set_name == "factions" else x.get("key") == key)),
            None,
        )
        if dup is not None:
            if set_name == "factions":
                dup["note"] = value
            else:
                dup["value"] = value
        else:
            if len(target) >= _SET_LIMITS[set_name]:
                raise ValueError(f"「{set_name}」条目已满（{_SET_LIMITS[set_name]} 条），请先清理")
            if set_name == "factions":
                target.append({"name": key, "note": value})
            else:
                entry: dict = {"key": key, "value": value}
                if origin:
                    entry["origin"] = origin
                target.append(entry)
        out[set_name] = target
    return out


# ── 注入渲染（写章消费方）────────────────────────────────────────────────


def _entry_line(e: dict) -> str:
    """条目 → 单行文本：factions 用 name+note，其余 key+value。"""
    if "name" in e:
        note = _clean_value(e.get("note"))
        name = _clean_key(e.get("name"))
        return f"{name}：{note}" if note else name
    key = _clean_key(e.get("key"))
    value = _clean_value(e.get("value"))
    return f"{key}：{value}" if value else key


def render_world_block(raw) -> str:
    """世界设定 → 「世界观」注入块（预算 600 字，整条为单元截断 + 显式从略）。

    结构：三段骨架（舞台/力量/代价，no_power 跳过力量与代价）永远注入；
    条目区（势力/历史/细节）按整条顺序装箱，放不下的整条跳过并计数显式声明。
    铁律 SHALL NOT 出现在本块（走红线区，见 render_red_lines）。
    """
    v2 = normalize_world(raw)
    no_power = bool(v2.get("no_power"))
    lines: list[str] = []
    for label, key in (("世界舞台", "stage"), ("力量体系", "power"), ("力量的代价", "cost")):
        if no_power and key in ("power", "cost"):
            continue
        val = str(v2.get(key, "")).strip()
        if val:
            lines.append(f"- {label}：{val}")
    paragraphs_len = sum(len(x) for x in lines) + len(lines) * 2 + len("世界观：\n")

    pooled: list[str] = []
    for title, set_key in (("势力", "factions"), ("历史与旧账", "history"), ("世界细节", "extra")):
        entries = v2.get(set_key) or []
        rendered = [_entry_line(e) for e in entries if _entry_line(e)]
        if rendered:
            pooled.append((title, rendered))

    if not pooled and not lines:
        return ""
    header = "世界观：\n"
    budget = WORLD_BLOCK_BUDGET - len(header) - paragraphs_len
    skipped = 0
    for title, rendered in pooled:
        block = f"- {title}：\n" + "\n".join(f"  - {x}" for x in rendered)
        if len(block) <= budget:
            lines.append(block)
            budget -= len(block) + 1
        else:
            skipped += len(rendered)
            budget -= len(title) + 8
    if skipped:
        lines.append(f"（另有 {skipped} 条世界细节从略）")
    if not lines:
        return ""
    return header + "\n".join(lines)


def render_red_lines(raw) -> list[str]:
    """世界铁律 → 红线区逐条文本（最高优先级、不截断；constraints ≤10×200 源头已限）。"""
    v2 = normalize_world(raw)
    out: list[str] = []
    for e in v2.get("constraints") or []:
        if not isinstance(e, dict):
            continue
        key = _clean_key(e.get("key"))
        value = _clean_value(e.get("value"))
        if key and value:
            out.append(f"世界铁律·{key}：{value}")
        elif value:
            out.append(f"世界铁律：{value}")
    return out


def world_summary_text(raw, char_budget: int = 1200) -> str:
    """世界设定 → 紧凑文本（AI 一致性体检/lore-suggest 的世界侧输入）。"""
    block = render_world_block(raw) + "\n" + "\n".join(render_red_lines(raw))
    return block.strip()[:char_budget]


# ── 契约校验（PUT /settings/world 入参）─────────────────────────────────


class WorldEntryIn(BaseModel):
    key: str = Field(max_length=KEY_MAX)
    value: str = Field(default="", max_length=VALUE_MAX)
    origin: str | None = Field(default=None, max_length=ORIGIN_MAX)

    @field_validator("key")
    @classmethod
    def _key_rules(cls, v: str) -> str:
        v = _clean_key(v)
        if not v:
            raise ValueError("条目缺少名目")
        return v

    @field_validator("value")
    @classmethod
    def _value_rules(cls, v: str) -> str:
        return _clean_value(v)

    @field_validator("origin")
    @classmethod
    def _origin_rules(cls, v: str | None) -> str | None:
        return _clean_key(v) or None


class FactionIn(BaseModel):
    name: str = Field(max_length=FACTION_NAME_MAX)
    note: str = Field(default="", max_length=FACTION_NOTE_MAX)

    @field_validator("name")
    @classmethod
    def _name_rules(cls, v: str) -> str:
        v = _clean_key(v)
        if not v:
            raise ValueError("势力缺少名称")
        return v


class WorldIn(BaseModel):
    no_power: bool = False
    stage: str = Field(default="", max_length=PARAGRAPH_MAX)
    power: str = Field(default="", max_length=PARAGRAPH_MAX)
    cost: str = Field(default="", max_length=PARAGRAPH_MAX)
    history: list[WorldEntryIn] = Field(default_factory=list, max_length=HISTORY_MAX)
    factions: list[FactionIn] = Field(default_factory=list, max_length=FACTIONS_MAX)
    constraints: list[WorldEntryIn] = Field(default_factory=list, max_length=CONSTRAINTS_MAX)
    extra: list[WorldEntryIn] = Field(default_factory=list, max_length=EXTRA_MAX)

    @field_validator("stage", "power", "cost")
    @classmethod
    def _para_rules(cls, v: str) -> str:
        return _clean_value(v)

    @model_validator(mode="after")
    def _dup_rules(self) -> "WorldIn":
        for set_name in ("history", "constraints", "extra"):
            keys = [e.key for e in getattr(self, set_name)]
            if len(keys) != len(set(keys)):
                dup = next(k for k in keys if keys.count(k) > 1)
                raise ValueError(f"{set_name} 存在重复名目：{dup}")
        names = [f.name for f in self.factions]
        if len(names) != len(set(names)):
            raise ValueError("factions 存在重复势力名")
        return self
