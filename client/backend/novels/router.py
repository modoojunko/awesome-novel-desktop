import json
import os
import tempfile
import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import get_ai_client
from auth_local.deps import require_ai_access, require_project_limit
from auth_local.middleware import get_current_user
from db import get_db
from filesystem.storage import get_storage
from novels.importer import IMPORT_TEMPLATE_MD, parse_file
from novels.service import (
    build_project_tree,
    create_project,
    delete_project,
    get_novel,
    get_project_by_slug,
    list_projects,
    novel_to_dict,
    rename_project,
    slugify,
)
from workflow.readiness import compute_readiness

router = APIRouter(prefix="/api/novels", tags=["novels"])

ai_router = APIRouter(prefix="/api/ai", tags=["ai"])


class CreateProjectBody(BaseModel):
    name: str
    synopsis: str = ""
    genre_profile: str = ""
    genre: str = ""  # 展示名（书架卡片类型胶囊），写入 story.yaml.genre
    source: str = "manual"


class SuggestMetaBody(BaseModel):
    premise: str


class RenameProjectBody(BaseModel):
    name: str


class UpdateStoryBody(BaseModel):
    synopsis: str = ""


class ArcVolumeRow(BaseModel):
    title: str = ""
    conflict: str = ""
    chapters: str = ""  # 字符串：数字或「待定」/?


class ArcEndingBody(BaseModel):
    scene: str = ""  # 最后一幕画面
    hero: str = ""  # 主角最终怎样
    tone: str = ""  # 基调（悲/喜/开放）


class StoryArcBody(BaseModel):
    premise: str = ""  # 一句话主线：谁+想要什么+什么拦着
    ending: ArcEndingBody = ArcEndingBody()
    volumes: list[ArcVolumeRow] = []


def _arc_volume_effective(row: dict) -> bool:
    """分卷行有有效内容（非整行待定/空）。"""
    for f in ("title", "conflict", "chapters"):
        v = str(row.get(f, "")).strip()
        if v and v not in ("待定", "?", "？"):
            return True
    return False


def _arc_has_content(arc: dict) -> bool:
    """主线有有效内容：一句话主线非空，或任一分卷行非待定。"""
    if str(arc.get("premise", "")).strip():
        return True
    volumes = arc.get("volumes")
    if isinstance(volumes, list):
        return any(isinstance(v, dict) and _arc_volume_effective(v) for v in volumes)
    return False


def _arc_next_step(arc: dict) -> int:
    """向导续步推断（保守取第一个未完成步骤）：1 主线 / 2 结局 / 3 分卷 / 4 自查。"""
    if not str(arc.get("premise", "")).strip():
        return 1
    ending = arc.get("ending") or {}
    if not any(str(ending.get(f, "")).strip() for f in ("scene", "hero", "tone")):
        return 2
    volumes = arc.get("volumes") or []
    if not any(isinstance(v, dict) and _arc_volume_effective(v) for v in volumes):
        return 3
    return 4


GENRE_CORPUS_NAMES = {
    "suspense-crime": "悬疑刑侦",
    "urban-romance": "都市言情",
    "ancient-politics": "古风权谋",
    "scifi-apocalypse": "科幻末世",
    "xuanhuan": "传统玄幻",
    "xianxia": "东方仙侠",
    "western-fantasy": "西方奇幻",
    "urban-daily": "都市日常",
}


@router.post("", status_code=201)
async def create(
    body: CreateProjectBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _limit: bool = Depends(require_project_limit),
):
    project = await create_project(
        db,
        user["id"],
        body.name,
        synopsis=body.synopsis,
        genre_profile=body.genre_profile,
        genre=body.genre,
        source=body.source,
    )
    return novel_to_dict(project)


@ai_router.post("/suggest-meta")
async def suggest_meta(
    body: SuggestMetaBody,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
    _limit: bool = Depends(require_project_limit),
):
    """Given a story premise, suggest titles, synopsis, genre, and pen name."""
    from prompts import load as load_prompt

    prompt = load_prompt("suggest_meta").format(premise=body.premise)

    # 新版 API Key 多配置：get_ai_client() 优先从 api_configs 表读取（解密），
    # config.json 仅作迁移期兜底；未配置 Key 时 AIClient 构造抛 ValueError。
    try:
        client = await get_ai_client()
    except ValueError as e:
        raise HTTPException(503, f"AI service not configured — {e}")

    try:
        usage: dict = {}
        text = await client.chat(
            model="haiku",
            system="",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            usage=usage,
        )
        # Extract JSON from response (handle ```json fences)
        if "```" in text:
            text = text.split("```")[1]
            text = text.removeprefix("json")
        from api_configs.usage import record_usage

        await record_usage(
            db,
            user_id=user["id"],
            project_id=None,
            operation="suggest_meta",
            # 建书期豁免路径（无 novel_id）：记客户端实际模型（降级链结果）
            model=client.model,
            tokens_in=usage.get("tokens_in", 0),
            tokens_out=usage.get("tokens_out", 0),
        )
        return json.loads(text.strip())
    except ValueError as e:
        raise HTTPException(500, f"AI suggestion failed: {e!s}")


@router.get("")
async def list_all(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    projects = await list_projects(db, user["id"])

    # 书架卡片富化（只读、附加字段，数据模型不动）：
    #   word_count — 章表 word_count 聚合
    #   synopsis   — story.yaml（创建/导入时写入）
    #   genre      — 题材展示名：新契约核心承诺优先，老书回退 story.yaml.genre / KV 题材；
    #                空值＝题材未设定，前端以「待定题材」占位（用户 2026-09-10 拍板）
    words: dict[str, int] = {}
    ch_count: dict[str, int] = {}
    arch_count: dict[str, int] = {}
    if projects:
        from collections import Counter

        from sqlalchemy.orm import load_only

        from models.chapter import Chapter

        ch_rows = (
            await db.scalars(
                select(Chapter)
                .where(Chapter.project_id.in_([p.id for p in projects]))
                .options(
                    load_only(Chapter.project_id, Chapter.word_count, Chapter.status)
                )
            )
        ).all()
        counter = Counter()
        counts = Counter()
        archived = Counter()
        for ch in ch_rows:
            key = str(ch.project_id)
            counter[key] += ch.word_count or 0
            counts[key] += 1
            if ch.status == "archived":
                archived[key] += 1
        words = dict(counter)
        ch_count = dict(counts)
        arch_count = dict(archived)

    kv_genres = await _batch_kv_genre_names(db, projects)
    core_promises = await _batch_core_promises(db, projects)
    storage = get_storage()
    out = []
    for p in projects:
        d = novel_to_dict(p)
        d["word_count"] = words.get(str(p.id), 0)
        # 章数/已归档章数按章表聚合覆盖（章表＝唯一事实源，novel 上的列只是缓存）：
        # 书架卡片阶段（stageFromChapters）与「打开书的落点」必须同结论，任何一处读旧缓存
        # 都会自相矛盾（如「卡片已归档 / 落点写作」）；同时自愈历史库里的漂移计数。
        d["total_chapters"] = ch_count.get(str(p.id), 0)
        d["total_archives"] = arch_count.get(str(p.id), 0)
        try:
            story = await storage.read_yaml(p.root_path, "story.yaml") or {}
        except Exception:
            story = {}
        d["synopsis"] = story.get("synopsis") or ""
        # 题材展示名：题材目录（story.yaml.genre/sub_genre，01 格选的「什么题材」）→
        # 老书核心承诺 → 老书 KV 题材名 → None（前端以「待定题材」占位）
        d["genre"] = (
            _compose_theme_label(story.get("genre"), story.get("sub_genre"))
            or core_promises.get(str(p.id))
            or kv_genres.get(str(p.id))
        )
        out.append(d)
    return out


def _compose_theme_label(theme: str | None, sub_type: str | None) -> str:
    """题材展示名：大类 · 子类（子类可空）。与前端 `themeLabel` 同口径。"""
    t = (theme or "").strip()
    s = (sub_type or "").strip()
    if t and s:
        return f"{t} · {s}"
    return t or s


async def _batch_core_promises(db: AsyncSession, projects) -> dict[str, str]:
    """新契约「题材」的核心承诺（novel_genre.core_promise），按 novel_id 批量取。

    题材自 D19 关系化后住 novel_genre 表；`core_promise` 是其中唯一可作短展示名的字段，
    且是题材面板第一格——空值即「题材未设定」，由前端以「待定题材」占位。
    """
    if not projects:
        return {}
    try:
        from models.novel_genre import NovelGenre

        rows = (
            await db.scalars(
                select(NovelGenre).where(
                    NovelGenre.novel_id.in_([p.id for p in projects])
                )
            )
        ).all()
        return {
            str(r.novel_id): (r.core_promise or "").strip()
            for r in rows
            if (r.core_promise or "").strip()
        }
    except Exception:
        return {}  # 表缺失/异常不 500，退化到历史来源


async def _batch_kv_genre_names(db: AsyncSession, projects) -> dict[str, str]:
    """project_settings KV key=genre → genres.name，按 root_path 批量对齐。"""
    if not projects:
        return {}
    try:
        from models.genre import Genre
        from models.project_setting import ProjectSetting

        settings = (
            await db.scalars(
                select(ProjectSetting).where(
                    ProjectSetting.root_path.in_([p.root_path for p in projects]),
                    ProjectSetting.key == "genre",
                )
            )
        ).all()
        gid_by_root: dict[str, str | None] = {}
        for row in settings:
            try:
                gid_by_root[row.root_path] = json.loads(row.content).get("genre_id")
            except Exception:
                gid_by_root[row.root_path] = None
        gids = {g for g in gid_by_root.values() if g}
        names = {}
        if gids:
            for g in (await db.scalars(select(Genre).where(Genre.id.in_(gids)))).all():
                names[g.id] = g.name
        return {
            str(p.id): names.get(gid_by_root[p.root_path])
            for p in projects
            if gid_by_root.get(p.root_path)
        }
    except Exception:
        return {}  # KV 缺失/损坏不 500，卡片少一个类型胶囊而已


@router.get("/by-slug/{slug}")
async def get_one_by_slug(
    slug: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project_by_slug(db, user["id"], slug)
    if not project:
        raise HTTPException(404, "Novel not found")
    return novel_to_dict(project)


@router.get("/{project_id}")
async def get_one(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    data = novel_to_dict(project)
    # BE-04：详情端点合并题材（project_settings KV + 全局 genres 表）；
    # KV 缺失/损坏 → genre/genre_name None，不 500（NovelBar 以 genre 优先于 type 展示）
    data["genre"] = None
    data["genre_name"] = None
    # 题材展示名（书内标签与书架卡片胶囊同源）：题材目录（01 大类/子类）→ 老书核心承诺
    # → 老书 story.yaml.genre / KV 题材名；空值＝题材未设定，前端以「待定题材」占位
    data["genre_label"] = None
    data["theme"] = ""
    data["sub_genre"] = ""
    try:
        from models.genre import Genre
        from models.novel_genre import NovelGenre
        from models.project_setting import ProjectSetting

        ng = await db.get(NovelGenre, project.id)
        if ng is not None and (ng.core_promise or "").strip():
            data["genre_label"] = ng.core_promise.strip()

        row = (
            await db.execute(
                select(ProjectSetting).where(
                    ProjectSetting.root_path == project.root_path,
                    ProjectSetting.key == "genre",
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            cfg = json.loads(row.content)
            genre_id = cfg.get("genre_id")
            data["genre"] = genre_id
            if genre_id:
                g = (
                    await db.execute(select(Genre).where(Genre.id == genre_id))
                ).scalar_one_or_none()
                if g is not None:
                    data["genre_name"] = g.name
    except Exception:
        pass  # KV 缺失/损坏不 500

    try:
        story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    except Exception:
        story = {}
    data["theme"] = story.get("genre") or ""
    data["sub_genre"] = story.get("sub_genre") or ""
    # 题材目录是展示名主来源（子类拼「大类 · 子类」）；无选题材时回落到核心承诺/KV 题材名
    data["genre_label"] = (
        _compose_theme_label(story.get("genre"), story.get("sub_genre"))
        or data["genre_label"]
        or data["genre_name"]
    )
    return data


@router.patch("/{project_id}")
async def rename(
    project_id: str,
    body: RenameProjectBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Rename a novel (display name only — slug/root_path unchanged)."""
    new_name = body.name.strip()
    if not new_name:
        raise HTTPException(422, "书名不能为空")
    if len(new_name) > 200:
        raise HTTPException(422, "书名过长")
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    if new_name == project.name:
        return novel_to_dict(project)  # idempotent same-name save
    renamed = await rename_project(db, project, new_name)
    return novel_to_dict(renamed)


@router.get("/{project_id}/story")
async def get_story(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Read story.yaml (synopsis etc.) for the synopsis card."""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    return {"synopsis": story.get("synopsis", "")}


@router.put("/{project_id}/story")
async def update_story(
    project_id: str,
    body: UpdateStoryBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Write story.yaml.synopsis (manual backfill — never triggers AI prefill)."""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    story["synopsis"] = body.synopsis.strip()
    await get_storage().write_yaml(project.root_path, "story.yaml", story)
    return {"ok": True, "synopsis": body.synopsis.strip()}


@router.get("/{project_id}/story/arc")
async def get_story_arc(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读主线卡（story.yaml.story_arc，整存整取；空卡返回空结构）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    arc = story.get("story_arc") or {}
    if not isinstance(arc, dict):
        arc = {}
    ending = arc.get("ending") or {}
    volumes = arc.get("volumes") if isinstance(arc.get("volumes"), list) else []
    data = {
        "premise": str(arc.get("premise", "") or ""),
        "ending": {f: str(ending.get(f, "") or "") for f in ("scene", "hero", "tone")},
        "volumes": [
            {f: str(v.get(f, "") or "") for f in ("title", "conflict", "chapters")}
            for v in volumes
            if isinstance(v, dict)
        ],
    }
    return {**data, "next_step": _arc_next_step(data), "has_content": _arc_has_content(data)}


@router.put("/{project_id}/story/arc")
async def update_story_arc(
    project_id: str,
    body: StoryArcBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写主线卡（整份覆盖；空/待定均合法，不触发 AI）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    arc = {
        "premise": body.premise.strip(),
        "ending": {
            "scene": body.ending.scene.strip(),
            "hero": body.ending.hero.strip(),
            "tone": body.ending.tone.strip(),
        },
        "volumes": [
            {
                "title": v.title.strip(),
                "conflict": v.conflict.strip(),
                "chapters": v.chapters.strip(),
            }
            for v in body.volumes
        ],
    }
    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    story["story_arc"] = arc
    await get_storage().write_yaml(project.root_path, "story.yaml", story)
    return {"ok": True, **arc, "next_step": _arc_next_step(arc)}


@router.delete("/{project_id}")
async def delete(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    await delete_project(db, project)
    return {"ok": True}


@router.get("/{project_id}/tree")
async def get_project_tree(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    tree = await build_project_tree(db, project)
    return tree


@router.get("/{project_id}/readiness")
async def get_readiness(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """7 项内容就绪判定（PRD 3.4）：complete / missing[{key,label,jump}] / warning 中文。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    return await compute_readiness(project.root_path, project.id)


async def _dump_project_snapshot(zf, db, project) -> None:
    """全量入库后的导出：zip 内容全部由 DB 组装（盘上不再有业务文件）。

    目录布局沿用旧文件树（settings/*.yaml、volumes/、chapters/、versions/、
    archives/、prompts/），外加 project.json 元数据。
    """
    import yaml

    from archive.router import _archive_filename
    from chapters.store import assemble_chapter
    from filesystem.paths import CHARACTER_DIR, PATH_TO_KEY, THREADS_PATH
    from models.archive import Archive, ChapterPrompt
    from models.chapter import Chapter, ChapterVersion
    from models.volume import Volume
    from volumes.service import get_volume

    def _yaml(name: str, data: dict) -> None:
        zf.writestr(name, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))

    zf.writestr(
        "project.json",
        json.dumps(novel_to_dict(project), ensure_ascii=False, indent=2),
    )

    # 设定（KV 表）→ settings yaml 树
    storage = get_storage()
    for relative_path in PATH_TO_KEY:
        data = await storage.read_yaml(project.root_path, relative_path)
        if data:
            _yaml(relative_path, data)
    threads = await storage.read_yaml(project.root_path, THREADS_PATH)
    if threads:
        _yaml(THREADS_PATH, threads)
    for fname in await storage.list_dir(project.root_path, CHARACTER_DIR):
        data = await storage.read_yaml(project.root_path, f"{CHARACTER_DIR}/{fname}")
        if data:
            _yaml(f"{CHARACTER_DIR}/{fname}", data)

    # 卷纲 + 章纲/正文 + 版本快照 + 生成提示词
    volumes = (
        await db.scalars(
            select(Volume)
            .where(Volume.project_id == project.id)
            .order_by(Volume.volume_no)
        )
    ).all()
    for vol in volumes:
        vol_ref = f"vol-{vol.volume_no}"
        vol_data = await get_volume(db, project, vol_ref)
        if vol_data:
            _yaml(f"volumes/{vol_ref}.yaml", vol_data)

        chapters = (
            await db.scalars(
                select(Chapter)
                .where(Chapter.volume_id == vol.id)
                .order_by(Chapter.chapter_no)
            )
        ).all()
        for ch in chapters:
            _yaml(f"chapters/{ch.ref}.yaml", assemble_chapter(ch))
            for ver in (
                await db.scalars(
                    select(ChapterVersion)
                    .where(ChapterVersion.chapter_id == ch.id)
                    .order_by(ChapterVersion.version)
                )
            ).all():
                zf.writestr(f"versions/{ch.ref}/v{ver.version}.json", ver.snapshot)
            for prompt in (
                await db.scalars(
                    select(ChapterPrompt).where(ChapterPrompt.chapter_id == ch.id)
                )
            ).all():
                zf.writestr(f"prompts/{ch.ref}-{prompt.name}.md", prompt.content)

    # 归档
    archives = (
        await db.scalars(
            select(Archive).join(Chapter).where(Chapter.project_id == project.id)
        )
    ).all()
    for arch in archives:
        name = _archive_filename(arch.chapter.ref, arch.title)
        zf.writestr(f"archives/{name}", arch.content)


@router.get("/{project_id}/export")
async def export_project(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """从 DB 打包项目全量（元数据/设定/卷章正文/版本/归档/提示词）为 zip。"""
    project = await get_novel(db, project_id, user["id"])
    if not project or project.status == "deleted":
        raise HTTPException(404, "Novel not found")

    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        await _dump_project_snapshot(zf, db, project)
    buffer.seek(0)

    # RFC 5987 编码中文文件名（slug 保留汉字，latin-1 header 会 UnicodeEncodeError）
    from urllib.parse import quote

    filename = f"{project.slug}.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f"attachment; filename=export.zip; filename*=UTF-8''{quote(filename)}"
            )
        },
    )


# ── Import endpoints ───────────────────────────────────────────────────────────


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


class ChapterItem(BaseModel):
    title: str
    content: str


class VolumeItem(BaseModel):
    title: str
    chapters: list[ChapterItem]


class ImportPersistBody(BaseModel):
    name: str
    volumes: list[VolumeItem]


@router.post("/import/parse", status_code=200)
async def import_parse(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Parse an uploaded file and return structured volume/chapter data."""
    # Read content and enforce 10 MB limit
    raw = await file.read()
    if len(raw) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, "文件大小超过 10MB 限制")

    filename = file.filename or "upload.txt"
    ext = os.path.splitext(filename)[1].lower() or ".txt"

    # Write to temp file for parsing
    fd, tmp_path = tempfile.mkstemp(suffix=ext)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)

    try:
        result = parse_file(tmp_path, filename)
    finally:
        os.unlink(tmp_path)

    return {
        "volumes": [asdict(v) for v in result.volumes],
        "warnings": [asdict(w) for w in result.warnings],
        "title": result.title,
    }


@router.post("/import/persist", status_code=201)
async def import_persist(
    body: ImportPersistBody,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_project_limit),
):
    """Persist parsed volumes/chapters as a new novel project."""
    from config import DATA_ROOT
    from models.project import Novel

    # ── Generate unique slug & root_path ──────────────────────────────
    slug = slugify(body.name)
    existing = await db.execute(
        select(Novel).where(Novel.user_id == user["id"], Novel.slug == slug)
    )
    if existing.scalar_one_or_none():
        slug = f"{slug}-{uuid.uuid4().hex[:6]}"

    root_path = os.path.join(DATA_ROOT, slug)

    try:
        # ── 1. Create project root only（数据全量入库，盘上无骨架）────
        os.makedirs(root_path, exist_ok=True)

        # ── 2. Create DB project row first（章族入库：卷/章直写 DB）────
        project = Novel(
            user_id=user["id"],
            name=body.name,
            slug=slug,
            root_path=root_path,
            source="import",
            total_volumes=len(body.volumes),
            total_chapters=sum(len(v.chapters) for v in body.volumes),
            # 同 create_project：导入即进入 settings 阶段，避免 init 下建卷 500
            current_phase="settings",
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)

        # ── 3. Write volumes & chapters to DB ────────────────────────
        from chapters import store as chapter_store
        from repositories import chapter_repo, volume_repo

        for vi, vol in enumerate(body.volumes, start=1):
            vol_row = await volume_repo.upsert(
                db, project.id, vi, title=vol.title, summary=""
            )
            vol_row.chapter_count = len(vol.chapters)
            await db.commit()
            for ci, ch in enumerate(vol.chapters, start=1):
                ch_ref = f"vol-{vi}-ch-{ci}"
                await chapter_repo.upsert(
                    db, project.id, vol_row.id, chapter_no=ci, ref=ch_ref,
                    title=ch.title, status="draft",
                )
                await db.commit()
                # 统一写入口：章纲/正文落库 + 元数据派生 + 导入初始快照
                await chapter_store.save_chapter(
                    root_path, ch_ref,
                    {
                        "volume": vi, "chapter": ci, "title": ch.title,
                        "status": "draft", "prose": ch.content,
                    },
                )

        # ── 4. Genre detection & synopsis extraction (free-tier) ─────
        try:
            # 从第一章正文匹配类型（story.yaml 属 settings 族，仍走文件）
            first_ch = body.volumes[0].chapters[0] if body.volumes else None
            if first_ch and first_ch.content:
                from novels.genre_matcher import extract_synopsis, match_genre

                synopsis = extract_synopsis(first_ch.content)
                genre, confidence = match_genre(first_ch.content)
                if genre:
                    storage = get_storage()
                    await storage.write_yaml(
                        root_path,
                        "story.yaml",
                        {
                            "synopsis": synopsis,
                            "genre": genre,
                            "genre_confidence": confidence,
                            "genre_source": "auto_detect",
                        },
                    )
        except Exception:
            pass  # 非关键，失败不中断导入

        return {"id": str(project.id), "name": body.name}

    except Exception as e:
        # Clean up on failure
        import shutil

        if os.path.exists(root_path):
            shutil.rmtree(root_path)
        raise HTTPException(500, f"导入持久化失败: {e!s}")


@router.get("/import/template")
async def import_template():
    """Return the import template markdown for the "下载导入模板" link."""
    return Response(
        content=IMPORT_TEMPLATE_MD,
        media_type="text/markdown; charset=utf-8",
    )
