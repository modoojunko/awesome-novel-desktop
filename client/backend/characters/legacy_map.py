"""角色段导出/导入映射（character-settings-v2 tasks 3.2/3.3）。

v2 布局：characters/characters.yaml（角色数组，含 legacy 原文）+
characters/relations.yaml（单向关系数组）。不再写 settings/character-setting/。

v1→v2 映射（tasks 3.3，逐字段）：
  name→name；role 枚举映射（protagonist→主角/antagonist→反派/supporting→配角）；
  appearance→dossier.look；background→dossier.background；speech→dossier.speech；
  world_view→cog.w3；self_image→cog.s2；values→cog.v2；abilities→cog.p2；
  skills→cog.p6；environment→cog.e1；
  possessions/experiences/relationships/state_history/personality→legacy（原文，
  不上界面不进 AI）。
"""

from __future__ import annotations

import json

# 老字段 → 新格（内容格 9 个）
LEGACY_FIELD_MAP: dict[str, tuple[str, str]] = {
    # 老键: (新容器, 新键)
    "appearance": ("dossier", "look"),
    "background": ("dossier", "background"),
    "speech": ("dossier", "speech"),
    "world_view": ("cog", "w3"),
    "self_image": ("cog", "s2"),
    "values": ("cog", "v2"),
    "abilities": ("cog", "p2"),
    "skills": ("cog", "p6"),
    "environment": ("cog", "e1"),
}
# 无归宿字段（只留原文）
LEGACY_KEEP_KEYS = (
    "possessions",
    "experiences",
    "relationships",
    "state_history",
    "personality",
)
# 老库 role（3 值）→ 新 role（4 值；"路人"无老值）
LEGACY_ROLE_MAP = {
    "protagonist": "主角",
    "antagonist": "反派",
    "supporting": "配角",
}


def map_legacy_character(raw: dict) -> dict:
    """v1 角色 yaml → v2 角色形状（纯函数；导入器调用）。

    新形状：{name, aliases[], role, persona, dossier{}, cog{}, legacy{}}。
    有歧义的老键原文同时进 legacy（回滚基准）。
    """
    raw = raw or {}
    out: dict = {
        "name": str(raw.get("name") or "").strip(),
        "aliases": [],
        "role": LEGACY_ROLE_MAP.get(str(raw.get("role") or ""), "配角"),
        "persona": "",
        "dossier": {},
        "cog": {},
        "legacy": {},
    }
    legacy = out["legacy"]
    for old_key, (bucket, new_key) in LEGACY_FIELD_MAP.items():
        value = raw.get(old_key)
        if isinstance(value, str) and value.strip():
            out[bucket][new_key] = value
            legacy[old_key] = value  # 双写原文作回滚基准（歧义键）
    for keep in LEGACY_KEEP_KEYS:
        value = raw.get(keep)
        if value not in (None, "", [], {}):
            legacy[keep] = value
    return out


def character_to_export(card_row, relations: list | None = None) -> dict:
    """Character ORM 行 → v2 导出 dict（显式白名单；legacy 保真带上）。"""
    return {
        "id": card_row.id,
        "seq": card_row.seq,
        "name": card_row.name,
        "aliases": json.loads(card_row.aliases or "[]"),
        "role": card_row.role,
        "persona": card_row.persona,
        "dossier": json.loads(card_row.dossier or "{}"),
        "cog": json.loads(card_row.cog or "{}"),
        "legacy": json.loads(card_row.legacy or "{}"),
        "relations": [
            {
                "owner_id": r.owner_id,
                "other_id": r.other_id,
                "rel_type": r.rel_type,
                "stance": r.stance,
                "note": r.note,
                "ch_ref": r.ch_ref,
            }
            for r in (relations or [])
        ],
    }


def export_has_legacy_characters(names: list[str]) -> bool:
    """包内是否存在 v1 角色目录（走 legacy 映射分支的判据）。"""
    return any(n.startswith("settings/character-setting/") and n.endswith(".yaml") for n in names)
