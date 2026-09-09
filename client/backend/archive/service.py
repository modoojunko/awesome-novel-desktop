import re
from datetime import UTC, datetime

from ai_client import get_ai_client_for_novel
from filesystem.storage import get_storage
from workflow.engine import load_chapter


def _validate_ref(ref: str) -> str:
    if ".." in ref or "/" in ref:
        raise ValueError("Invalid chapter reference")
    return ref


def _canonical_chapter_ref(ref: str) -> str:
    """把伏笔引入章节归一为规范 vol-N-ch-M 格式（兼容模板短格式 '1-1'）。"""
    ref = (ref or "").strip()
    if re.match(r"^vol-\d+-ch-\d+$", ref):
        return ref
    m = re.match(r"^(\d+)-(\d+)$", ref)
    if m:
        return f"vol-{m.group(1)}-ch-{m.group(2)}"
    return ref


async def archive_chapter(
    novel_id: str,
    root_path: str,
    chapter_ref: str,
    full_text: str,
    ai_summary: bool = True,
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
        try:
            client = await get_ai_client_for_novel(novel_id)
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
            )
            if summary_text:
                summary = summary_text[:200]
        except Exception:  # noqa: BLE001, S110 — AI 摘要可选，失败降级为正文前 200 字
            pass

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
            await session.commit()

    await update_thread_state(root_path, chapter, summary)
    await update_character_states(root_path, chapter, full_text)

    return {
        "archive_path": archive_path,
        "summary": summary,
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

    hooks = await get_storage().read_yaml(root_path, "settings/hooks.yaml")
    for hook in hooks.get("active", []):
        # 前端 active 项无 status；introduced_in 兼容短格式 "1-1"
        if _canonical_chapter_ref(hook.get("introduced_in", "")) == t["last_chapter"]:
            hook["status"] = "mentioned"
    await get_storage().write_yaml(root_path, "settings/hooks.yaml", hooks)

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
