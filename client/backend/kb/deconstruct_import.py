"""拆书产物 → 知识库条目映射（c-kb-import 批4）。

从 deconstruct 产物的五类维度（手法/文风/文笔/世界/角色）
映射为知识库条目。幂等键 = (user_id, src_ref=task_id, src_key=维度:序号)。
"""

from __future__ import annotations

import json

from kb.concepts import normalize_scene, normalize_emotion
from kb.models import KbEntry


def _mk_entry(
    user_id: str, task_id: str, src_key: str, genre: str,
    concept: str, concept_id: str, title: str,
    payload: dict, instruction: str,
    example: str = "", negative_example: str = "",
    evidence: str = "", evidence_json: dict | None = None,
    when_json: dict | None = None,
) -> KbEntry:
    return KbEntry(
        user_id=user_id,
        genre=genre,
        concept=concept,
        concept_id=concept_id,
        title=title[:40],
        payload_json=json.dumps(payload, ensure_ascii=False),
        payload_version=1,
        instruction=instruction[:240],
        example=example[:500],
        negative_example=negative_example[:200],
        when_json=json.dumps(when_json or {}, ensure_ascii=False),
        evidence=evidence[:500],
        evidence_json=json.dumps(evidence_json or {}, ensure_ascii=False),
        src_kind="deconstruct",
        src_ref=task_id,
        src_key=src_key,
        src_novel_name="",
    )


def map_deconstruct_products(
    user_id: str,
    task_id: str,
    genre: str,
    products: dict,
) -> tuple[list[KbEntry], list[str]]:
    """拆书产物 → 知识条目列表。返回 (entries, warnings)。

    五类维度映射（对齐 settings_map.py）：
    - techniques/avoid/borrowable → 手法
    - style → 文风（slot=role/tone）+ 文笔（slot=rule/craft/banned/tic）
    - world → 世界设定（按分区）
    - characters → 角色设定（原型）
    - mainplot/structure → 不收（P1）
    """
    entries: list[KbEntry] = []
    warnings: list[str] = []
    seq = 0

    def _key(dim: str) -> str:
        return f"{dim}:{seq}"

    def _ev(chapter: str = "", quote: str = "") -> str:
        return f"{'第' + chapter + '章' if chapter else ''} {quote}".strip()

    # ─── 手法（techniques + avoid + borrowable）───
    for section in ("techniques", "avoid", "borrowable"):
        items = products.get(section) or []
        if isinstance(items, dict):
            items = items.get("items") or items.get("list") or []
        for item in items:
            if not isinstance(item, dict):
                continue
            seq += 1
            title = str(item.get("title") or item.get("name") or "")[:40]
            instruction = str(item.get("instruction") or item.get("description") or item.get("content") or "")[:240]
            example = str(item.get("example") or item.get("quote") or "")[:500]
            negative = str(item.get("negative") or item.get("avoid_description") or "") if section == "avoid" else ""
            scene_raw = str(item.get("scene") or item.get("type") or "")
            scene = normalize_scene(scene_raw)
            emotion = normalize_emotion(str(item.get("emotion") or ""))
            when = {}
            if scene:
                when["scene"] = scene
            if emotion:
                when["emotion"] = emotion
            payload = {
                "instruction": instruction,
                "scene": scene or "日常",
                **({"emotion": emotion} if emotion else {}),
                **({"negative": negative} if negative else {}),
            }
            ev_chapter = str(item.get("chapter") or "")
            ev_quote = str(item.get("quote") or item.get("example") or "")[:200]
            evidence = _ev(ev_chapter, ev_quote)
            ev_json = {"quotes": [{"loc": ev_chapter, "text": ev_quote}]} if ev_quote else {}
            entries.append(_mk_entry(
                user_id, task_id, _key("technique"), genre,
                "手法", f"{genre}:手法", title or f"手法 {seq}",
                payload, instruction, example, negative,
                evidence, ev_json, when,
            ))

    # ─── 文风 + 文笔 ───
    style = products.get("style")
    if isinstance(style, dict):
        data = style.get("data") or style
        role = str(data.get("role") or data.get("identity") or "")[:120]
        if role:
            seq += 1
            entries.append(_mk_entry(
                user_id, task_id, _key("style.role"), genre,
                "文风", f"{genre}:文风", "叙事身份",
                {"slot": "role", "role": role}, role,
                evidence="文风蒸馏·叙事身份",
            ))
        samples = data.get("samples") or data.get("style_samples") or []
        for i, s in enumerate(samples[:6]):
            seq += 1
            s_text = str(s)[:500] if isinstance(s, str) else ""
            if not s_text:
                continue
            entries.append(_mk_entry(
                user_id, task_id, _key("style.sample"), genre,
                "文风", f"{genre}:文风", f"示范段 {i+1}",
                {"slot": "sample", "sample": s_text}, s_text,
                evidence="文风蒸馏·示范段",
            ))
        # 文笔：rules + craft + banned
        rules = data.get("rules") or []
        if isinstance(rules, list):
            for i, r in enumerate(rules[:20]):
                seq += 1
                r_text = str(r)[:160]
                if not r_text:
                    continue
                entries.append(_mk_entry(
                    user_id, task_id, _key("craft.rule"), genre,
                    "文笔", f"{genre}:文笔", f"规则 {i+1}",
                    {"slot": "rule", "rule": r_text}, r_text,
                    evidence="拆书·文笔规则",
                ))

    # ─── 世界设定 ───
    world = products.get("world")
    if isinstance(world, dict):
        data = world.get("data") or world
        for part in ("stage", "power", "cost", "history", "factions", "constraints", "extra"):
            items = data.get(part) or []
            if isinstance(items, str):
                items = [{"content": items}]
            elif isinstance(items, list):
                pass
            else:
                items = []
            for i, item in enumerate(items):
                seq += 1
                content = str(item if isinstance(item, str) else item.get("content") or item.get("text") or "")[:300]
                if not content:
                    continue
                hard = part == "constraints"
                payload = {"part": part, "content": content, **({"hard": True} if hard else {})}
                entries.append(_mk_entry(
                    user_id, task_id, _key("world"), genre,
                    "世界设定", f"{genre}:世界设定",
                    f"{part} {i+1}",
                    payload, content[:240],
                    evidence=f"拆书·世界设定·{part}",
                ))

    # ─── 角色设定 ───
    characters = products.get("characters")
    if isinstance(characters, dict):
        data = characters.get("data") or characters.get("characters") or []
        for i, c in enumerate(data[:10]):
            if not isinstance(c, dict):
                continue
            seq += 1
            name = str(c.get("name") or c.get("title") or "")[:40]
            if not name:
                continue
            payload = {
                "archetype": name,
                **{k: str(v)[:200] for k, v in c.items()
                   if k in ("look", "background", "speech", "gender", "age", "race", "faction", "plot") and v},
                **{k: str(v)[:120] for k, v in c.items()
                   if k.startswith("w") or k.startswith("s") or k.startswith("v") or k.startswith("p") or k.startswith("b") or k.startswith("e")},
            }
            entries.append(_mk_entry(
                user_id, task_id, _key("character"), genre,
                "角色设定", f"{genre}:角色设定",
                name, payload, name[:240],
                evidence="拆书·角色设定",
            ))

    return entries, warnings
