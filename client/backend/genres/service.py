"""Genre library service — CRUD, seed, and writing-pipeline injection.

题材定义全局共享（C端 SQLite genres 表）。嵌套结构以 JSON 字符串存入 Text 列，
camelCase（前端 GenreDefinition 形状）↔ 模型列之间的转换集中在这里。

resolve_genre_context / build_genre_section 供写作链路
（write/chapter_writer.py）复用：项目 settings/genre.yaml 里的 genre_id → 全局定义 →
合并项目 overrides → 渲染「## 题材设定」块。genre_id 为空或定义缺失时优雅降级
返回 None（不强制 genre_id 必须存在于库，存量项目/测试不破）。
"""

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import async_session
from filesystem.storage import get_storage
from models.genre import Genre
from novels.service import list_projects

from .presets import PRESET_GENRES

GENRE_CATEGORIES = {"urban", "historical", "xianhuan", "suspense", "scifi", "independent"}
_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")


# ── Serialization ──────────────────────────────────────────────────────────


def _json_loads(s: str | None, default):
    try:
        return json.loads(s) if s else default
    except (TypeError, ValueError):
        return default


def _model_to_def(row: Genre) -> dict:
    """Genre ORM row → camelCase GenreDefinition dict (frontend shape)."""
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "category": row.category,
        "narratorRole": row.narrator_role,
        "typicalArc": row.typical_arc,
        "toneBlueprint": _json_loads(row.tone_blueprint, {}),
        "taboos": _json_loads(row.taboos, []),
        "promptInjection": row.prompt_injection,
        "genreConfig": _json_loads(row.genre_config, {}),
        "storyArcTemplates": _json_loads(row.story_arc_templates, []),
        "isPreset": bool(row.is_preset),
    }


def _def_to_model(data: dict) -> dict:
    """camelCase GenreDefinition dict → ORM column kwargs."""
    return {
        "id": data["id"],
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "category": data.get("category", ""),
        "narrator_role": data.get("narratorRole", ""),
        "typical_arc": data.get("typicalArc", ""),
        "tone_blueprint": json.dumps(data.get("toneBlueprint", {}), ensure_ascii=False),
        "taboos": json.dumps(data.get("taboos", []), ensure_ascii=False),
        "prompt_injection": data.get("promptInjection", ""),
        "genre_config": json.dumps(data.get("genreConfig", {}), ensure_ascii=False),
        "story_arc_templates": json.dumps(
            data.get("storyArcTemplates", []), ensure_ascii=False
        ),
    }


# ── Validation ─────────────────────────────────────────────────────────────


def validate_id(genre_id: str) -> str | None:
    """Return an error message, or None when the id is valid."""
    if not genre_id or not _ID_RE.match(genre_id):
        return "题材 id 只能由小写字母开头的小写字母/数字/短横线组成"
    return None


# ── Seed ───────────────────────────────────────────────────────────────────


async def ensure_seed_genres() -> None:
    """Insert preset genres that are missing (idempotent).

    只插缺失、绝不覆盖已存在的行——用户对预置题材的编辑被保留。启动时调用。
    """
    async with async_session() as session:
        for preset in PRESET_GENRES:
            existing = await session.get(Genre, preset["id"])
            if existing is None:
                session.add(Genre(**_def_to_model(preset), is_preset=True))
        await session.commit()


# ── CRUD ──────────────────────────────────────────────────────────────────


async def list_genres(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Genre).order_by(Genre.category, Genre.name))
    return [_model_to_def(r) for r in result.scalars().all()]


async def get_genre(db: AsyncSession, genre_id: str) -> dict | None:
    row = await db.get(Genre, genre_id)
    return _model_to_def(row) if row else None


async def create_genre(db: AsyncSession, data: dict) -> dict:
    """Create a custom genre. Raises ValueError on invalid id / duplicate id."""
    err = validate_id(data.get("id", ""))
    if err:
        raise ValueError(err)
    existing = await db.get(Genre, data["id"])
    if existing:
        raise ValueError("该题材 id 已存在")
    row = Genre(**_def_to_model(data), is_preset=False)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _model_to_def(row)


async def update_genre(db: AsyncSession, genre_id: str, data: dict) -> dict | None:
    """Update a custom genre. Returns None if not found; presets are read-only."""
    row = await db.get(Genre, genre_id)
    if not row:
        return None
    if row.is_preset:
        raise ValueError("预置题材只读，可新建自定义题材替代")
    for k, v in _def_to_model({**data, "id": genre_id}).items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return _model_to_def(row)


async def delete_genre(db: AsyncSession, genre_id: str) -> bool | None:
    """Delete a custom genre. Returns True if deleted, None if not found."""
    row = await db.get(Genre, genre_id)
    if not row:
        return None
    if row.is_preset:
        raise ValueError("预置题材不可删除")
    await db.delete(row)
    await db.commit()
    return True


async def _find_referencing_projects(
    db: AsyncSession, user_id: str, genre_id: str
) -> list[str]:
    """Return names of projects whose settings/genre.yaml references genre_id."""
    projects = await list_projects(db, user_id)
    out = []
    for p in projects:
        cfg = await get_storage().read_yaml(p.root_path, "settings/genre.yaml") or {}
        if cfg.get("genre_id") == genre_id:
            out.append(p.name)
    return out


# ── Writing-pipeline injection ─────────────────────────────────────────────


async def resolve_genre_context(
    root_path: str, novel_id: str | None = None
) -> dict | None:
    """本书题材 → 写作注入用的扁平 dict（D19 关系化唯一来源）。

    `project_settings('genre')` KV 行已废弃（不再读写）；无 novel_id 或五字段
    全空 → None（优雅降级，不注入空块）。
    """
    if not novel_id:
        return None

    from genres.novel_genre_service import get_novel_genre
    from models.novel_genre import GenreVocab

    async with async_session() as session:
        g = await get_novel_genre(session, novel_id)
        # 关联项的 tagId → 词汇 label（注入用可读文本；裸 slug 等于没注入）
        ids = [
            item["tagId"] for item in g["forbidden_list"] if item.get("tagId")
        ] + [b for b in g["battlefield"] if isinstance(b, str) and ":" in b]
        labels: dict[str, str] = {}
        if ids:
            rows = (
                await session.execute(select(GenreVocab).where(GenreVocab.id.in_(ids)))
            ).scalars().all()
            labels = {r.id: r.label for r in rows}

    forbidden = [
        labels.get(item["tagId"], item["tagId"])
        if item.get("tagId")
        else item.get("text", "")
        for item in g["forbidden_list"]
    ]
    battlefield = [labels.get(b, b) for b in g["battlefield"]]

    # 题材目录（01 格「什么题材」）落 story.yaml（与简介同族），注入时一并带上：
    # 它是「定了就不跑偏」的类型锁，模型必须知道这本书是什么题材。
    theme = sub_genre = ""
    try:
        story = await get_storage().read_yaml(root_path, "story.yaml") or {}
        theme = (story.get("genre") or "").strip()
        sub_genre = (story.get("sub_genre") or "").strip()
    except Exception:
        pass  # story.yaml 缺失/损坏不阻断注入

    if not any(
        [
            theme,
            g["core_promise"],
            g["promise_note"],
            g["cost_ratio"],
            forbidden,
            battlefield,
        ]
    ):
        return None
    return {
        "theme": theme,
        "sub_genre": sub_genre,
        "core_promise": g["core_promise"],
        "promise_note": g["promise_note"],
        "cost_ratio": g["cost_ratio"],
        "forbidden": [x for x in forbidden if x],
        "battlefield": [x for x in battlefield if x],
    }


def _fmt(v) -> str:
    """Format a string or list into a single string."""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "、".join(str(x) for x in v if str(x).strip())
    return ""


def build_genre_section(ctx: dict | None) -> str:
    """Render the '## 题材设定' markdown block for prompt injection.

    Returns "" when ctx is None. Consumed by chapter_writer.py.
    只认五字段契约（D19）；旧契约键已随 KV 路径退役。
    """
    if not ctx:
        return ""
    lines = ["## 题材设定"]
    if ctx.get("theme"):
        label = ctx["theme"]
        if ctx.get("sub_genre"):
            label = f"{label}（{ctx['sub_genre']}）"
        lines.append(f"题材：{label}")
    if ctx.get("core_promise"):
        lines.append(f"核心承诺：{ctx['core_promise']}")
    if ctx.get("promise_note"):
        lines.append(f"读者预期：{ctx['promise_note']}")
    if ctx.get("cost_ratio") is not None:
        lines.append(f"吃苦指数：{ctx['cost_ratio']}（1=轻，10=极重）")
    if ctx.get("forbidden"):
        lines.append("绝对禁止：" + "；".join(str(x) for x in ctx["forbidden"]))
    if ctx.get("battlefield"):
        lines.append("主线战场：" + _fmt(ctx["battlefield"]))

    return "\n".join(lines)
