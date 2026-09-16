from datetime import UTC, datetime

from ai_client import get_ai_client_for_novel
from filesystem.storage import get_storage
from settings.world_model import canonical_chapter_ref
from workflow.engine import load_chapter


def _validate_ref(ref: str) -> str:
    if ".." in ref or "/" in ref:
        raise ValueError("Invalid chapter reference")
    return ref


async def _record_ai_usage(
    novel_id: str, operation: str, usage: dict, *, force: bool = False
) -> None:
    """归档链 AI 调用记账（ai-client capability 需求 2）：自开 session，
    从 Novel 行取 user/模型口径；记账失败不影响归档主流程。"""
    try:
        from api_configs.usage import record_usage
        from db import async_session
        from models.project import Novel

        async with async_session() as session:
            novel = await session.get(Novel, novel_id)
            if novel is None:
                return
            await record_usage(
                session,
                user_id=novel.user_id,
                project_id=novel_id,
                api_config_id=novel.ai_config_id,
                operation=operation[:50],
                model=novel.ai_model or "haiku",
                tokens_in=usage.get("tokens_in", 0),
                tokens_out=usage.get("tokens_out", 0),
                force=force,
            )
    except Exception:  # noqa: BLE001, S110 — 记账失败不影响归档
        pass


async def archive_chapter(
    novel_id: str,
    root_path: str,
    chapter_ref: str,
    full_text: str,
    ai_summary: bool = True,
    lore: bool = True,
) -> dict:
    _validate_ref(chapter_ref)
    chapter = await load_chapter(root_path, chapter_ref)

    vol = chapter.get("volume", 1)
    ch = chapter.get("chapter", 1)
    title = chapter.get("title", "untitled")
    slug = title.replace(" ", "-").lower()[:50]
    archive_path = f"archives/vol-{vol}-ch-{ch}-{slug}.md"

    # Generate 200-char summary via AI; degrade to first 200 chars when unavailable
    # (ai_summary 由调用方按会员权益决定；本书模型未就绪/调用失败一律降级)。
    summary = full_text[:200]
    if ai_summary:
        summary_usage: dict = {}
        try:
            client = await get_ai_client_for_novel(novel_id)
        except Exception:  # noqa: BLE001 — 模型未就绪：调用未发生，不记账
            client = None
        if client is not None:
            try:
                summary_text = await client.chat(
                    model="haiku",
                    system="",
                    messages=[
                        {
                            "role": "user",
                            "content": f"用200字以内总结本章核心事件，只陈述事实不评论：\n\n{full_text[:3000]}",
                        }
                    ],
                    max_tokens=200,
                    usage=summary_usage,
                )
                await _record_ai_usage(novel_id, "archive_summary", summary_usage)
                if summary_text:
                    summary = summary_text[:200]
            except Exception:  # noqa: BLE001, S110 — AI 摘要可选，失败降级为正文前 200 字
                await _record_ai_usage(
                    novel_id, "archive_summary_fail", summary_usage, force=True
                )

    # archives 表（PR④）：一章一行，重归档即替换；随章行 FK CASCADE
    from sqlalchemy import select

    from chapters.store import _get_chapter_by_root
    from db import async_session
    from models.archive import Archive

    async with async_session() as session:
        ch_row = await _get_chapter_by_root(session, root_path, chapter_ref)
        if ch_row is not None:
            row = await session.scalar(
                select(Archive).where(Archive.chapter_id == ch_row.id)
            )
            if row is None:
                session.add(
                    Archive(
                        chapter_id=ch_row.id,
                        title=str(title)[:200],
                        summary=str(summary)[:300],
                        content=full_text,
                    )
                )
            else:
                row.title = str(title)[:200]
                row.summary = str(summary)[:300]
                row.content = full_text
            # 归档联动（write-archive-meta-sync）：本章引入的活跃伏笔 → 单条 UPDATE
            # mentioned_in_chapter_id。status 枚举不被归档修改；同值重写天然幂等。
            from settings.hooks_service import mark_hooks_mentioned

            await mark_hooks_mentioned(session, novel_id, ch_row.id)
            await session.commit()

    await update_thread_state(root_path, chapter, summary)
    await update_character_states(root_path, chapter, full_text)

    # lore-keeping（world-setting-v2 D1）：识别本章新出现/变化的世界要素，
    # 以建议形式随归档响应返回（stateless 不落库）；采纳走
    # POST /settings/world/lore-apply（(key, origin) 幂等）。与 ai_summary
    # 偏好解耦：各自独立开关；AI 不可用一律静默降级为空建议。
    lore_suggestions: list[dict] = []
    if lore:
        import json as _json

        from filesystem.storage import get_storage as _storage
        from prompts import load as _load_prompt
        from settings.world_model import world_summary_text

        lore_usage: dict = {}
        try:
            client = await get_ai_client_for_novel(novel_id)
        except Exception:  # noqa: BLE001 — 模型未就绪：调用未发生，不记账
            client = None
        if client is not None:
            try:
                world_raw = await _storage().read_yaml(
                    root_path, "settings/world-setting.yaml"
                ) or {}
                lore_prompt = _load_prompt("world_lore_suggest").format(
                    chapter=full_text[:3000],
                    world=world_summary_text(world_raw, 1200) or "（世界设定还空着）",
                )
                lore_text = await client.chat(
                    model="haiku",
                    system="你是小说世界设定管理员。只输出 JSON，不要任何其他文字。",
                    messages=[{"role": "user", "content": lore_prompt}],
                    max_tokens=800,
                    usage=lore_usage,
                )
            except Exception:  # noqa: BLE001 — lore 建议可选：调用失败降级为空并落 _fail
                await _record_ai_usage(
                    novel_id, "archive_lore_fail", lore_usage, force=True
                )
            else:
                # 记账先于解析：调用已完成（钱已花），JSON 不合法也要留痕
                await _record_ai_usage(novel_id, "archive_lore", lore_usage)
                try:
                    if "```" in lore_text:
                        lore_text = lore_text.split("```")[1]
                        lore_text = lore_text.removeprefix("json")
                    lore_data = _json.loads(lore_text.strip())
                    # 归一化与 ai_router.lore-suggest 同源（settings.world_model.parse_lore_suggestions）
                    from settings.world_model import parse_lore_suggestions

                    for item in parse_lore_suggestions(lore_data):
                        lore_suggestions.append({**item, "origin": canonical_chapter_ref(chapter_ref)})
                except Exception:  # noqa: BLE001, S110 — 解析失败静默降级（账已记）
                    lore_suggestions = []
    return {
        "archive_path": archive_path,
        "summary": summary,
        "lore_suggestions": lore_suggestions,
    }


async def update_thread_state(root_path: str, chapter: dict, summary: str):
    threads = await get_storage().read_yaml(root_path, "threads.yaml")
    thread_name = chapter.get("thread", "主线")

    if "threads" not in threads:
        threads["threads"] = {}
    if thread_name not in threads["threads"]:
        threads["threads"][thread_name] = {}

    t = threads["threads"][thread_name]
    t["pov"] = chapter.get("pov_character", t.get("pov", "未知"))
    t["last_chapter"] = f"vol-{chapter.get('volume')}-ch-{chapter.get('chapter')}"
    t["current_state"] = summary
    t["emotional_temperature"] = chapter.get("memo", {}).get("emotion_curve", "medium")

    # 伏笔 mentioned 留痕已迁真表单条 UPDATE（archive_chapter → mark_hooks_mentioned，
    # write-archive-meta-sync）；旧「整文件读改写 status:mentioned」的 KV 通道退役。

    await get_storage().write_yaml(root_path, "threads.yaml", threads)


async def update_character_states(root_path: str, chapter: dict, full_text: str):
    seg_chars = (
        chapter.get("outline", {}).get("segments", [{}])[0].get("characters", [])
    )
    for name in seg_chars:
        char = await get_storage().read_yaml(
            root_path, f"settings/character-setting/{name}.yaml"
        )
        if not char:
            continue
        if "state_history" not in char:
            char["state_history"] = []
        state_change = chapter.get("memo", {}).get("character_state_change", "")
        char["state_history"].append(
            {
                "chapter": f"vol-{chapter.get('volume')}-ch-{chapter.get('chapter')}",
                "change": state_change,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        await get_storage().write_yaml(
            root_path, f"settings/character-setting/{name}.yaml", char
        )
