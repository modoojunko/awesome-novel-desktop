import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import DATA_ROOT
from filesystem.storage import get_storage
from models.project import Novel


def slugify(name: str) -> str:
    # 保留中文（一-鿿）与 word 字符，其余替换为 '-'。
    # 若不含中文，全中文名会 slug 成 "untitled"，导致不同项目共享同一 root_path 目录、数据串。
    slug = re.sub(r"[^\w一-鿿\-]", "-", name.lower()).strip("-")
    return slug or "untitled"


def count_chars(text: str | None) -> int:
    """去空白中文字符数（B5 同口径）—— 与前端 countChars（text.replace(/\\s/g, "").length）一致。

    供幂等回填 word_count 使用；change 006 起 save_prose/树/novel_to_dict 共用。
    """
    return len(re.sub(r"\s+", "", text or ""))


async def create_project(
    db: AsyncSession,
    user_id: str,
    name: str,
    synopsis: str = "",
    genre_profile: str = "",
    genre: str = "",
    source: str = "ai",
) -> Novel:
    slug = slugify(name)
    existing = await db.execute(
        select(Novel).where(Novel.user_id == user_id, Novel.slug == slug)
    )
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    root_path = f"{DATA_ROOT}/{slug}"

    # "import" 来源：只创建数据库记录，不初始化文件系统骨架
    # 导入后文件系统会由 /import/persist 写入完整内容
    if source != "import":
        await get_storage().init_skeleton(root_path)

        # Write AI-suggested metadata into project files
        # genre 为展示名（书架卡片类型胶囊；与 AI 流程的 genre_profile slug 无关）
        if synopsis or genre_profile or genre:
            story = await get_storage().read_yaml(root_path, "story.yaml")
            if synopsis:
                story["synopsis"] = synopsis
            if genre:
                story["genre"] = genre
            await get_storage().write_yaml(root_path, "story.yaml", story)

        if genre_profile:
            style = await get_storage().read_yaml(root_path, "settings/writing-style.yaml")
            style["genre_profile"] = genre_profile
            await get_storage().write_yaml(root_path, "settings/writing-style.yaml", style)


    project = Novel(
        user_id=user_id,
        name=name,
        slug=slug,
        root_path=root_path,
        source=source,
        # 创建即进入 settings 阶段（六阶段第二阶段）：创建后可直接补设定/建卷建章。
        # 若不设，phase 保持 init，create_volume/chapter 的 update_phase("outline")
        # 会被 engine 拒绝（init→outline 非法）→ 500（PRD 3.4 AC-4.3「仍然继续」场景）。
        current_phase="settings",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def list_projects(db: AsyncSession, user_id: str) -> list[Novel]:
    stmt = select(Novel).where(Novel.status != "deleted", Novel.user_id == user_id)
    result = await db.execute(stmt.order_by(Novel.updated_at.desc()))
    return list(result.scalars().all())


async def get_novel(
    db: AsyncSession, project_id: str, user_id: str
) -> Novel | None:
    stmt = select(Novel).where(Novel.id == project_id, Novel.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_project_by_slug(
    db: AsyncSession, user_id: str, slug: str
) -> Novel | None:
    stmt = select(Novel).where(
        Novel.slug == slug,
        Novel.status != "deleted",
        Novel.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_project(db: AsyncSession, project: Novel):
    project.status = "deleted"
    await db.commit()


async def rename_project(db: AsyncSession, project: Novel, new_name: str) -> Novel:
    """Rename a novel (display name only — slug/root_path intentionally unchanged).

    The slug stays fixed so the project directory, file keys and any
    (user_id, slug) uniqueness constraints are untouched.
    """
    project.name = new_name
    await db.commit()
    await db.refresh(project)
    return project


# ── Serialization ─────────────────────────────────────────────────────────


def novel_to_dict(p) -> dict:
    """Convert a Novel ORM instance to a serializable dict."""
    return {
        "id": str(p.id),
        "name": p.name,
        "slug": p.slug,
        "current_phase": p.current_phase,
        "status": p.status,
        "total_volumes": p.total_volumes,
        "total_chapters": p.total_chapters,
        "total_archives": p.total_archives,
        "source": p.source,
        "ai_config_id": str(p.ai_config_id) if p.ai_config_id else None,
        "ai_model": p.ai_model,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


# ── Project Tree ────────────────────────────────────────────────────────────


async def build_project_tree(db, project) -> dict:
    """Build the full project tree: settings + volumes + chapters with status.

    全量入库后 DB 是唯一存储（无文件降级路径）；响应形状与 list_volumes 一致。
    """
    from volumes.service import list_volumes

    return {
        "project_id": str(project.id),
        "volumes": await list_volumes(db, project),
    }
