"""封面画面描述 AI 提取（c-cover-scene-extract）。

从书的选题/主线/世界观蒸馏一个「画面场景」草稿，落点永远是前端「画面描述」
输入框（用户可改、保存才生效）：不落库、不进生成自动链。名字脱敏兜底在
prompt_builder（cover_prompt 组装时书名→此地/角色名→人物），本模块不再重复。
模型门控走 ensure_novel_model_ready（路由路径是 novel_id，端点内直调）。
"""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from api_configs.usage import record_usage
from filesystem.storage import get_storage
from genres.novel_genre_service import get_novel_genre
from models.project import Novel
from prompts import load_layers
from settings.world_model import normalize_world

SYNOPSIS_MAX = 240
FULLSTORY_MAX = 1200
STAGE_MAX = 300
# 与 prompt_builder 组装时的 cover_prompt 截断（180）对齐：守卫放更宽的话，
# 超限场景存库后会在「画面呈现{…}」句里被切尾，预览与实际下发不一致。
SCENE_MAX = 180

TEMPLATE_NAME = "image_cover_scene"


def _clamp(text, n: int) -> str:
    return " ".join(str(text or "").split())[:n]


def parse_scene(text: str) -> str:
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        raise HTTPException(502, "AI 返回的画面描述无法解析，可重试")
    if not isinstance(data, dict):
        raise HTTPException(502, "AI 返回的画面描述结构异常，可重试")
    scene = _clamp(data.get("scene"), SCENE_MAX)
    if not scene:
        raise HTTPException(502, "AI 没给出可用的画面描述，可重试")
    return scene


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


async def extract_cover_scene(db: AsyncSession, novel_id: str, user_id: str) -> str:
    novel = await db.get(Novel, novel_id)
    if novel is None or novel.status == "deleted" or novel.user_id != user_id:
        raise HTTPException(404, "Project not found")

    material = await collect_material(db, novel)
    system, prompt = load_layers(TEMPLATE_NAME)
    prompt = prompt.format(**material)

    client = await get_ai_client_for_novel(novel_id)
    usage: dict = {}
    try:
        text = await client.chat(
            model="haiku",
            system=system or "你是图书封面视觉策划。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            json_mode=True,
            usage=usage,
            operation=TEMPLATE_NAME,
            max_tokens=500,
        )
    except AITimeoutError:
        await _record(db, novel, user_id, usage, failed=True)
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        await _record(db, novel, user_id, usage, failed=True)
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    scene = parse_scene(text)
    await _record(db, novel, user_id, usage)
    return scene


async def _record(
    db: AsyncSession, novel: Novel, user_id: str, usage: dict, *, failed: bool = False,
) -> None:
    await record_usage(
        db, user_id=user_id, project_id=novel.id,
        api_config_id=novel.ai_config_id,
        operation=f"{TEMPLATE_NAME}{'_fail' if failed else ''}"[:50],
        model=effective_model(novel),
        tokens_in=usage.get("tokens_in", 0), tokens_out=usage.get("tokens_out", 0),
        force=failed,
    )
