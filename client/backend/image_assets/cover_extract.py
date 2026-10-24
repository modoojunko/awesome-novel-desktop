"""封面/头像 AI 提取草稿（c-cover-scene-extract、c-avatar-look-draft）。

封面：从书的选题/主线/世界观蒸馏「画面场景」草稿；头像：从角色卡白名单
（性别/年龄/种族、外貌、势力、一句话人设）蒸馏「外貌/服饰」草稿。落点永远是
前端对应输入框（用户可改、保存才生效）：不落库、不进生成自动链。名字脱敏
兜底在 prompt_builder（组装时书名→此地/角色名→人物），本模块不再重复。
模型门控走 ensure_novel_model_ready（路由路径是 novel_id，端点内直调）。
"""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AIClient, AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from api_configs.usage import record_usage
from filesystem.storage import get_storage
from genres.novel_genre_service import get_novel_genre
from models.character import Character
from models.project import Novel
from prompts import load_layers
from settings.world_model import normalize_world

SYNOPSIS_MAX = 240
FULLSTORY_MAX = 1200
STAGE_MAX = 300
# 与 prompt_builder 组装时的 cover_prompt 截断（180）对齐：守卫放更宽的话，
# 超限场景存库后会在「画面呈现{…}」句里被切尾，预览与实际下发不一致。
SCENE_MAX = 180
# 与 prompt_builder 组装时的 avatar_prompt 截断（140）同理对齐。
LOOK_MAX = 140

TEMPLATE_NAME = "image_cover_scene"
AVATAR_TEMPLATE_NAME = "image_avatar_look"


def _clamp(text, n: int) -> str:
    return " ".join(str(text or "").split())[:n]


def _parse_field(text: str, field: str, what: str, limit: int) -> str:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise HTTPException(502, f"AI 返回的{what}无法解析，可重试")
    if not isinstance(data, dict):
        raise HTTPException(502, f"AI 返回的{what}结构异常，可重试")
    value = _clamp(data.get(field), limit)
    if not value:
        raise HTTPException(502, f"AI 没给出可用的{what}，可重试")
    return value


def parse_scene(text: str) -> str:
    return _parse_field(text, "scene", "画面描述", SCENE_MAX)


def parse_look(text: str) -> str:
    return _parse_field(text, "look", "外貌描述", LOOK_MAX)


async def collect_material(db: AsyncSession, novel: Novel) -> dict:
    story = await get_storage().read_yaml(novel.root_path, "story.yaml") or {}
    world = await get_storage().read_yaml(novel.root_path, "settings/world-setting.yaml") or {}
    genre = await get_novel_genre(db, novel.id)
    arc = story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {}
    sub_genre = _clamp(story.get("sub_genre"), 40)
    theme = _clamp(story.get("genre"), 40) or "（未确认）"
    return {
        "theme": f"{theme}（{sub_genre}）" if sub_genre else theme,
        "promise_note": _clamp(genre.get("promise_note"), 120) or "（未填写）",
        "synopsis": _clamp(story.get("synopsis"), SYNOPSIS_MAX) or "（未填写）",
        "fullstory": _clamp(arc.get("fullstory"), FULLSTORY_MAX) or "（未填写）",
        "world_stage": _clamp(normalize_world(world).get("stage"), STAGE_MAX) or "（未填写）",
    }


async def collect_avatar_material(db: AsyncSession, novel: Novel, ch: Character) -> dict:
    story = await get_storage().read_yaml(novel.root_path, "story.yaml") or {}
    try:
        dossier = json.loads(ch.dossier or "{}")
        if not isinstance(dossier, dict):
            dossier = {}
    except (TypeError, ValueError):
        dossier = {}
    person = "，".join(x for x in (
        _clamp(dossier.get("age"), 20),
        _clamp(dossier.get("gender"), 20),
        _clamp(dossier.get("race"), 20),
    ) if x) or "（未填写）"
    return {
        "theme": _clamp(story.get("genre"), 40) or "（未确认）",
        "person": person,
        "look": _clamp(dossier.get("look"), 400) or "（未填写）",
        "faction": _clamp(dossier.get("faction"), 100) or "（未填写）",
        "persona": _clamp(ch.persona, 100) or "（未填写）",
    }


async def _chat_json(
    client: AIClient, system: str, prompt: str, operation: str,
    usage: dict, db: AsyncSession, novel: Novel, user_id: str,
) -> str:
    try:
        return await client.chat(
            model="haiku",
            system=system or "你是图书视觉策划。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            json_mode=True,
            usage=usage,
            operation=operation,
            max_tokens=500,
        )
    except AITimeoutError:
        await _record(db, novel, user_id, usage, operation=operation, failed=True)
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        await _record(db, novel, user_id, usage, operation=operation, failed=True)
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e


async def extract_cover_scene(db: AsyncSession, novel_id: str, user_id: str) -> str:
    novel = await db.get(Novel, novel_id)
    if novel is None or novel.status == "deleted" or novel.user_id != user_id:
        raise HTTPException(404, "Project not found")

    material = await collect_material(db, novel)
    system, prompt = load_layers(TEMPLATE_NAME)
    prompt = prompt.format(**material)

    client = await get_ai_client_for_novel(novel_id)
    usage: dict = {}
    text = await _chat_json(client, system, prompt, TEMPLATE_NAME, usage, db, novel, user_id)
    scene = parse_scene(text)
    await _record(db, novel, user_id, usage, operation=TEMPLATE_NAME)
    return scene


async def extract_avatar_look(
    db: AsyncSession, novel_id: str, character_id: str, user_id: str,
) -> str:
    novel = await db.get(Novel, novel_id)
    if novel is None or novel.status == "deleted" or novel.user_id != user_id:
        raise HTTPException(404, "Project not found")
    ch = await db.get(Character, character_id)
    if ch is None or ch.novel_id != novel.id:
        raise HTTPException(404, "Character not found")

    material = await collect_avatar_material(db, novel, ch)
    system, prompt = load_layers(AVATAR_TEMPLATE_NAME)
    prompt = prompt.format(**material)

    client = await get_ai_client_for_novel(novel_id)
    usage: dict = {}
    text = await _chat_json(
        client, system, prompt, AVATAR_TEMPLATE_NAME, usage, db, novel, user_id,
    )
    look = parse_look(text)
    await _record(db, novel, user_id, usage, operation=AVATAR_TEMPLATE_NAME)
    return look


async def _record(
    db: AsyncSession, novel: Novel, user_id: str, usage: dict,
    *, operation: str = TEMPLATE_NAME, failed: bool = False,
) -> None:
    await record_usage(
        db, user_id=user_id, project_id=novel.id,
        api_config_id=novel.ai_config_id,
        operation=f"{operation}{'_fail' if failed else ''}"[:50],
        model=effective_model(novel),
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
        force=failed,
    )
