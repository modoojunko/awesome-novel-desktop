"""备份导出（c-novel-export-roundtrip PR1）。

双包产物（用户拍板中文名自标识）：
- 资产包 爱小说-备份-{日期}.zip——全部活跃书，每书一目录（projects/{slug}/…）
- 配置包 爱小说-备份-配置-{日期}.zip——user 子集 + api_configs（密钥明文，导入端重加密）
- 单书 《书名》-作品包-{日期}.zip——交付场景，零配置零密钥

格式契约 v1（backup-restore capability）：
- 给代码读的一律 yaml（project.yaml 契约头 + settings 树 + 卷章全字段）
- versions/prompts/archives 为冻结原文，字节级直写
- archives/manifest.yaml 旁路补元数据（v0 导出曾丢 title/summary）
"""

import asyncio
import io
import re
import threading
import zipfile
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import select

import brand
from db import async_session
from filesystem.paths import CHARACTER_DIR, PATH_TO_KEY, THREADS_PATH
from filesystem.storage import get_storage

FORMAT_VERSION = 1


# ── 产物命名（中文自标识；书名清洗防 OS 非法字符） ────────────────────────────


def sanitize_book_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n]', "", (name or "").strip())
    cleaned = cleaned.rstrip(". ")
    if not cleaned:
        cleaned = "未命名"
    return cleaned[:60]


def _d(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%d")


def backup_zip_name(now: datetime | None = None) -> str:
    # 前缀取品牌单源（brand-name-single-source）；「爱小说-备份-」为 backup-restore 冻结契约现值
    return f"{brand.BRAND_NAME}-备份-{_d(now)}.zip"


def config_zip_name(now: datetime | None = None) -> str:
    return f"{brand.BRAND_NAME}-备份-配置-{_d(now)}.zip"


def single_zip_name(book_name: str, now: datetime | None = None) -> str:
    return (
        f"《{sanitize_book_filename(book_name)}》-作品包-{_d(now)}.zip"
    )


def _contract_header() -> dict:
    return {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }


def _yaml_str(data: dict) -> str:
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


# ── 每书导出（单书/多书共用：prefix 区分包内路径） ────────────────────────────


async def dump_book_into(zf, db, project, prefix: str = "") -> None:
    """把一本书的全部资产写进 zip（prefix 为空=单书包根，多书=projects/{slug}/）。"""
    from sqlalchemy import select

    from archive.router import _archive_filename
    from chapters.store import assemble_chapter
    from models.archive import Archive, ChapterPrompt
    from models.chapter import Chapter, ChapterVersion
    from models.volume import Volume
    from novels.service import novel_to_dict
    from volumes.service import get_volume

    def put(name: str, data: str) -> None:
        zf.writestr(prefix + name, data)

    def put_yaml(name: str, data: dict) -> None:
        put(name, _yaml_str({**_contract_header(), **data}) if name == "project.yaml" else _yaml_str(data))

    # 元数据（契约头 + novel_to_dict 原样）
    put(
        "project.yaml",
        _yaml_str({**_contract_header(), **novel_to_dict(project)}),
    )

    # 设定（KV 表）→ settings yaml 树；非空才写（沿用单书包口径）
    storage = get_storage()
    for relative_path in PATH_TO_KEY:
        data = await storage.read_yaml(project.root_path, relative_path)
        if data:
            put_yaml(relative_path, data)
    threads = await storage.read_yaml(project.root_path, THREADS_PATH)
    if threads:
        put_yaml(THREADS_PATH, threads)
    for fname in await storage.list_dir(project.root_path, CHARACTER_DIR):
        data = await storage.read_yaml(project.root_path, f"{CHARACTER_DIR}/{fname}")
        if data:
            put_yaml(f"{CHARACTER_DIR}/{fname}", data)

    # 卷纲 + 章纲/正文 + 版本快照 + 生成提示词
    volumes = (
        await db.scalars(
            select(Volume)
            .where(Volume.project_id == project.id)
            .order_by(Volume.volume_no)
        )
    ).all()
    manifest_archives = []
    for vol in volumes:
        vol_ref = f"vol-{vol.volume_no}"
        vol_data = await get_volume(db, project, vol_ref)
        if vol_data:
            put_yaml(f"volumes/{vol_ref}.yaml", vol_data)

        chapters = (
            await db.scalars(
                select(Chapter)
                .where(Chapter.volume_id == vol.id)
                .order_by(Chapter.chapter_no)
            )
        ).all()
        for ch in chapters:
            put_yaml(f"chapters/{ch.ref}.yaml", assemble_chapter(ch))
            for ver in (
                await db.scalars(
                    select(ChapterVersion)
                    .where(ChapterVersion.chapter_id == ch.id)
                    .order_by(ChapterVersion.version)
                )
            ).all():
                put(f"versions/{ch.ref}/v{ver.version}.json", ver.snapshot)
            for prompt in (
                await db.scalars(
                    select(ChapterPrompt).where(ChapterPrompt.chapter_id == ch.id)
                )
            ).all():
                put(f"prompts/{ch.ref}-{prompt.name}.md", prompt.content)

        # 归档（原文 + manifest 旁路元数据）
        archives = (
            await db.scalars(
                select(Archive).join(Chapter).where(Chapter.project_id == project.id)
            )
        ).all()
        for arch in archives:
            name = _archive_filename(arch.chapter.ref, arch.title)
            put(f"archives/{name}", arch.content)
            manifest_archives.append({
                "filename": name,
                "ref": arch.chapter.ref,
                "title": arch.title,
                "summary": arch.summary,
                "archived_at": arch.archived_at.isoformat()
                if arch.archived_at
                else None,
            })

    if manifest_archives:
        put_yaml("archives/manifest.yaml", {"archives": manifest_archives})


# ── 配置包（user 子集 + api_configs，密钥明文——导入端重加密） ────────────────


async def build_config_package_bytes(db, user_id: str) -> tuple[bytes, str]:
    from models.user import User

    user = await db.get(User, user_id)
    if user is None:
        raise ExportJobError("user_not_found", "用户不存在")
    from api_configs.crypto import decrypt_api_key
    from models.api_config import ApiConfig

    rows = (
        await db.scalars(select(ApiConfig).where(ApiConfig.user_id == user.id))
    ).all()
    configs = sorted(rows, key=lambda c: c.created_at or datetime.min)

    payload = {
        "format_version": FORMAT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "user": {
            "display_name": user.display_name or "",
            # legacy 默认 AI 三件套：仅非空时导出（导入端同口径只补空）
            "api_key": user.api_key or "",
            "api_base_url": user.api_base_url or "",
            "api_model": user.api_model or "",
        },
        "api_configs": [
            {
                "name": c.name,
                "vendor": c.vendor,
                "vendor_display_name": c.vendor_display_name,
                "vendor_override": c.vendor_override,
                # 加键兼容契约内（不升 format_version）；旧版导入端忽略未知键
                "api_format": getattr(c, "api_format", None) or "openai",
                "api_key": decrypt_api_key(c.api_key) if c.api_key else "",
                "base_url": c.base_url,
                "models": c.models,
                "models_updated_at": c.models_updated_at.isoformat()
                if c.models_updated_at
                else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in configs
        ],
    }
    raw = _yaml_str(payload)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("config.yaml", raw)
    return buf.getvalue(), config_zip_name()


async def config_preview(db, user_id: str) -> dict:
    from models.user import User

    user = await db.get(User, user_id)
    """下载前确认数据：掩码密钥（前 3 后 4），两步导出确认弹层用。"""
    from api_configs.crypto import decrypt_api_key
    from models.api_config import ApiConfig

    def _mask(key: str) -> str:
        if not key:
            return "未填"
        return f"{key[:3]}{'*' * 8}{key[-4:]}" if len(key) > 8 else "*" * len(key)

    rows = (await db.scalars(select(ApiConfig).where(ApiConfig.user_id == user.id))).all()
    return {
        "warning": "配置包含明文 API Key，请妥善保管与传输",
        "account": user.display_name or user.email,
        "configs": [
            {
                "name": c.name,
                "vendor_display_name": c.vendor_display_name or c.vendor,
                "base_url": c.base_url,
                "api_key_masked": _mask(
                    decrypt_api_key(c.api_key) if c.api_key else ""
                ),
            }
            for c in rows
        ],
    }


# ── 任务化导出：选目录 → 后台线程写双包 → status 轮询真进度 ───────────────────


class ExportJobError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


_job_lock = threading.Lock()
_job: dict | None = None


def _new_job(target_dir: str, include_config: bool, books: int) -> dict:
    return {
        "state": "running",
        "phase": "probe",
        "target_dir": target_dir,
        "include_config": include_config,
        "books_total": books,
        "books_done": 0,
        "current_book": "",
        "bytes_written": 0,
        "files": [],
        "error": None,
    }


def _set(**kw) -> None:
    with _job_lock:
        _job.update(kw)


def start_backup_job(target_dir: str, user_id: str, include_config: bool) -> dict | None:
    """单飞：已有任务在跑返回 None（路由层转 409）。"""
    return _start({"kind": "backup", "target_dir": target_dir, "include_config": include_config},
                  _run_backup_thread, user_id)


def start_single_job(target_file: str, user_id: str, book_id: str) -> dict | None:
    return _start({"kind": "single", "target_file": target_file, "book_id": book_id},
                  _run_single_thread, user_id)


def _start(payload: dict, runner, user_id: str) -> dict | None:
    global _job
    with _job_lock:
        if _job and _job["state"] == "running":
            return None
        _job = {
            "state": "running", "phase": "probe", "kind": payload["kind"],
            "target_dir": payload.get("target_dir") or "",
            "target_file": payload.get("target_file") or "",
            "include_config": payload.get("include_config", True),
            "books_total": 0, "books_done": 0, "current_book": "",
            "bytes_written": 0, "files": [], "error": None,
        }
    thread = threading.Thread(target=runner, args=(payload, user_id), daemon=True)
    thread.start()
    return job_status()


def job_status() -> dict:
    with _job_lock:
        return dict(_job) if _job else {"state": "idle"}


def _phase(name: str, current_book: str | None = None) -> None:
    kw = {"phase": name}
    if current_book is not None:
        kw["current_book"] = current_book
    _set(**kw)


def _run_backup_thread(payload: dict, user_id: str) -> None:
    try:
        asyncio.run(export_backup_to_dir(payload["target_dir"], user_id, payload["include_config"]))
        _set(state="done", phase="finalize")
    except ExportJobError as e:
        _set(state="error", error={"code": e.code, "message": e.message})
    except OSError as e:
        code = "disk_full" if getattr(e, "errno", None) == 28 else "permission_denied" if getattr(e, "errno", None) in (13, 30) else "io_error"
        _set(state="error", error={"code": code, "message": str(e)})
    except Exception as e:  # 兜底：任务线程错误必须落到 status
        _set(state="error", error={"code": "io_error", "message": str(e)})


async def export_backup_to_dir(target_dir: str, user_id: str, include_config: bool) -> None:
    from models.project import Novel
    from models.user import User

    target = Path(target_dir)
    _phase("probe")
    target.mkdir(parents=True, exist_ok=True)
    probe = target / ".ainovel-write-probe"
    probe.write_text("ok")
    probe.unlink()

    async with async_session() as db:
        user = await db.get(User, user_id)
        if user is None:
            raise ExportJobError("user_not_found", "用户不存在")
        books = (
            await db.scalars(
                select(Novel)
                .where(Novel.user_id == user_id, Novel.status != "deleted")
                .order_by(Novel.created_at)
            )
        ).all()
        _set(books_total=len(books))

        _phase("assets")
        assets_path = target / backup_zip_name()
        part = Path(str(assets_path) + ".part")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
            # 包级清单（契约文件：导入端形态探测的锚点）
            zf.writestr("backup.yaml", _yaml_str({
                **_contract_header(),
                "books": [
                    {"slug": b.slug, "name": b.name, "created_at": b.created_at.isoformat() if b.created_at else None}
                    for b in books
                ],
            }))
            for idx, project in enumerate(books, start=1):
                prefix = f"projects/{project.slug}/"
                _phase("assets", project.name)
                await dump_book_into(zf, db, project, prefix=prefix)
                _set(books_done=idx)
        part.replace(assets_path)

        config_name = None
        if include_config:
            _phase("config")
            data, config_name = await build_config_package_bytes(db, user_id)
            config_path = target / config_name
            config_part = Path(str(config_path) + ".part")
            config_part.write_bytes(data)
            config_part.replace(config_path)

        files = [assets_path.name] + ([config_name] if config_name else [])
        _set(files=files)


def _run_single_thread(payload: dict, user_id: str) -> None:
    try:
        asyncio.run(_single_async(payload["target_file"], user_id, payload["book_id"]))
        _set(state="done", phase="finalize")
    except ExportJobError as e:
        _set(state="error", error={"code": "not_found", "message": e.message})
    except OSError as e:
        _set(state="error", error={"code": "io_error", "message": str(e)})


async def _single_async(target_file: str, user_id: str, book_id: str) -> None:
    from models.project import Novel

    target = Path(target_file)
    _phase("assets")
    target.parent.mkdir(parents=True, exist_ok=True)
    async with async_session() as db:
        project = await db.get(Novel, book_id)
        if project is None or project.status == "deleted":
            raise ExportJobError("not_found", "作品不存在")
        part = Path(str(target) + ".part")
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as zf:
            await dump_book_into(zf, db, project, prefix="")
        part.replace(target)
        _set(files=[target.name])
