"""Character agent — builds prompts, calls LLM, parses decisions."""

import asyncio
import json
import logging
import re
import time

from ai_client import get_ai_client_for_novel
from prompts import load as load_prompt
from story.models import CharacterState, Decision, DecisionLog, SensoryInput, StageState

logger = logging.getLogger(__name__)

# ── Timeout: single LLM call max wait ──────────────────────────────
_LLM_TIMEOUT = 10  # seconds

# ── Fallback when LLM fails ────────────────────────────────────────

_FALLBACK = DecisionLog(
    see="（无法获取）",
    hear="（无法获取）",
    sense="（无法获取）",
    understanding="（LLM返回异常）",
    values_checked="（无法判断）",
    ability_assessment="（无法评估）",
    emotion="（未知）",
    urgency="（未知）",
    decision_process="（LLM返回异常，使用默认行为）",
    action_type="等待",
    action_target="",
    action_description="（AI 决策异常，原地待命中）",
    inner_monologue="…",
    action_impact="（未知）",
)


def _build_decision_prompt(
    character: CharacterState,
    sensory: SensoryInput,
    stage: StageState,
) -> str:
    """Build the decision prompt for a single character."""
    cognition_lines = []
    cog = character.cognition_6 or {}
    for key, val in cog.items():
        if val:
            cognition_lines.append(f"- {key}：{val}")

    state_lines = [
        f"位置：{character.position}",
        f"体力：{character.stamina}%",
        f"情绪：{character.emotion}",
    ]
    if character.urgency:
        state_lines.insert(0, f"紧急：{character.urgency}")

    return load_prompt("story_character").format(
        character_cognition="\n".join(cognition_lines) or "（无特殊设定）",
        character_state="\n".join(state_lines),
        see=sensory.see or "（无特殊视觉信息）",
        hear=sensory.hear or "（无特殊听觉信息）",
        sense=sensory.smell or sensory.feel or "（无特殊感觉）",
        knowledge="; ".join(character.knowledge)
        if character.knowledge
        else "（无特殊信息）",
        relationships=json.dumps(character.relationships, ensure_ascii=False)
        if character.relationships
        else "（无特殊关系认知）",
    )


def _repair_json(text: str) -> str | None:
    """Repair common issues: Chinese punctuation, trailing commas, single quotes, Python/JS literals."""
    result = text.strip()

    # Chinese punctuation → English
    result = result.replace("：", ":").replace("，", ",")
    result = result.replace("（", "(").replace("）", ")")

    # Single-quoted keys/values → double-quoted
    result = re.sub(r"(?<=[{, ])'([^']+?)'(?=\s*[:,\]}])", r'"\1"', result)

    # Trailing commas before ] or }
    result = re.sub(r",\s*([}\]])", r"\1", result)

    # Python/JS → JSON literals
    result = result.replace("None", "null").replace("undefined", "null")
    result = result.replace("True", "true").replace("False", "false")

    try:
        json.loads(result)
        return result
    except json.JSONDecodeError:
        return None


def _extract_fallback_text(text: str) -> dict | None:
    """Last resort: extract whatever useful info we can from plain text."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    for line in lines[:5]:
        if any(kw in line for kw in ["分析", "评估", "考虑", "因为", "所以", "决定"]):
            continue
        if len(line) > 8:
            return {
                "see": "",
                "hear": "",
                "sense": "",
                "understanding": "",
                "values_checked": "",
                "ability_assessment": "",
                "emotion": "",
                "urgency": "",
                "decision_process": "",
                "action_type": "动作",
                "action_target": "",
                "action_description": line[:200],
                "inner_monologue": "",
                "action_impact": "",
            }
    return None


def _extract_json(text: str) -> dict | None:
    """Extract JSON from LLM response. Tries multiple formats + repair. Never crashes."""
    cleaned = text.strip()

    # 1. Direct parse (try raw, then repaired)
    for src in [cleaned, _repair_json(cleaned)]:
        if not src:
            continue
        try:
            return json.loads(src)
        except json.JSONDecodeError:
            pass

    # 2. Markdown code fence (```json ... ```)
    if "```" in cleaned:
        for part in cleaned.split("```"):
            part = part.strip()
            if not part:
                continue
            if part.startswith("json"):
                part = part[4:].strip()
            for src in [part, _repair_json(part)]:
                if not src:
                    continue
                try:
                    return json.loads(src)
                except json.JSONDecodeError:
                    pass

    # 3. First { ... } or [ ... ] block
    for left, right in [("{", "}"), ("[", "]")]:
        start = cleaned.find(left)
        if start >= 0:
            end = cleaned.rfind(right)
            if end > start:
                block = cleaned[start : end + 1]
                for src in [block, _repair_json(block)]:
                    if not src:
                        continue
                    try:
                        return json.loads(src)
                    except json.JSONDecodeError:
                        pass

    # 4. Desperate: extract action-like sentence
    return _extract_fallback_text(cleaned)


# ── Field validation ───────────────────────────────────────────────
# Ensure critical fields have valid types, not None or wrong type

_STRING_FIELDS = {
    "see",
    "hear",
    "sense",
    "understanding",
    "values_checked",
    "ability_assessment",
    "emotion",
    "urgency",
    "decision_process",
    "action_type",
    "action_target",
    "action_description",
    "inner_monologue",
    "action_impact",
}


def _validate_decision_data(data: dict) -> dict:
    """Ensure all fields exist with correct types. Fills missing with empty string."""
    validated = {}
    for field in _STRING_FIELDS:
        val = data.get(field)
        if not isinstance(val, str):
            val = str(val) if val is not None else ""
        validated[field] = val
    return validated


def _parse_decision(
    text: str, character_id: str, sensory: SensoryInput, round_num: int
) -> Decision:
    """Parse LLM response into Decision. Never crashes — uses fallback on failure."""
    data = _extract_json(text)
    if data is None:
        logger.warning(
            "Non-JSON from %s round %d: %.150s", character_id, round_num, text
        )
        return Decision(
            character_id=character_id,
            sensory_input=sensory,
            log=_FALLBACK,
            round=round_num,
            timestamp=int(time.time()),
        )

    data = _validate_decision_data(data)
    return Decision(
        character_id=character_id,
        sensory_input=sensory,
        log=DecisionLog(**data),
        round=round_num,
        timestamp=int(time.time()),
    )


# ── Retry: stronger prompt to force pure JSON ──────────────────────

_STRICT_SYSTEM = (
    "你是一位小说角色扮演者。"
    "只输出纯 JSON，不要任何其他文字。"
    "禁止markdown代码块、禁止注释、禁止中文标点。"
    "字段名和类型不可修改。"
    "输出非法 JSON 会导致系统故障。"
)


async def run_character_decision(
    character: CharacterState,
    sensory: SensoryInput,
    stage: StageState,
    round_num: int,
    novel_id: str = "",
) -> Decision:
    """Run one character's decision. Retries once with stricter prompt on failure."""
    prompt = _build_decision_prompt(character, sensory, stage)
    client = await get_ai_client_for_novel(novel_id)

    for attempt in range(2):
        try:
            text = await asyncio.wait_for(
                client.chat(
                    model="haiku",
                    system=_STRICT_SYSTEM
                    if attempt == 1
                    else "你是一位小说角色扮演者。只输出 JSON，不要任何其他文字。",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                ),
                timeout=_LLM_TIMEOUT,
            )
            if _extract_json(text) is not None:
                return _parse_decision(text, character.character_id, sensory, round_num)
            logger.warning(
                "Bad JSON from %s (attempt %d)", character.character_id, attempt
            )
        except TimeoutError:
            logger.warning("Timeout %s (attempt %d)", character.character_id, attempt)
        except Exception as e:
            logger.warning(
                "LLM fail %s (attempt %d): %s", character.character_id, attempt, e
            )

    logger.error(
        "All LLM attempts failed for %s round %d — using fallback",
        character.character_id,
        round_num,
    )
    return Decision(
        character_id=character.character_id,
        sensory_input=sensory,
        log=_FALLBACK,
        round=round_num,
        timestamp=int(time.time()),
    )


async def run_all_decisions(
    characters: dict[str, CharacterState],
    sensory_inputs: dict[str, SensoryInput],
    stage: StageState,
    round_num: int,
    novel_id: str = "",
) -> list[Decision]:
    """Run decisions for all characters in parallel. Never crashes."""
    tasks = [
        run_character_decision(
            char, sensory_inputs.get(cid, SensoryInput()), stage, round_num, novel_id
        )
        for cid, char in characters.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in results if isinstance(r, Decision)]
