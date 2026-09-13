"""包导入引擎（c-novel-export-roundtrip PR2）。

单轨升级恢复路径：备份包 → 形态探测+校验 → 逐书单事务落库+智能挂回。
零迁移零召回（旧库留档零接触）。
"""

import json
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import select

FORMAT_VERSION = 1


def detect_kind(zf: zipfile.ZipFile) -> str:
    names = set(zf.namelist())
    if "backup.yaml" in names:
        return "assets"
    if "config.yaml" in names:
        return "config"
    if "project.yaml" in names or "project.json" in names:
        return "single"
    return "unknown"


def validate_paths(zf: zipfile.ZipFile) -> None:
    for name in zf.namelist():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts or (len(name) > 1 and name[1] == ":"):
            raise ValueError(f"非法路径: {name}")


def parse_package(paths: list[str]) -> dict:
    books = []
    config_data = None
    warnings = []
    schema_version = None

    for ps in paths:
        p = Path(ps)
        if not p.exists():
            warnings.append(f"文件不存在: {p.name}")
            continue
        try:
            zf = zipfile.ZipFile(p)
        except zipfile.BadZipFile:
            warnings.append(f"不是有效的 zip 文件: {p.name}")
            continue
        validate_paths(zf)
        kind = detect_kind(zf)
        names = set(zf.namelist())

        if kind == "assets":
            meta = yaml.safe_load(zf.read("backup.yaml"))
            sv = meta.get("format_version", 0) if meta else 0
            schema_version = max(schema_version or 0, sv)
            for entry in meta.get("books", []):
                slug = entry.get("slug", "")
                book_dir = f"projects/{slug}/"
                proj_data = yaml.safe_load(zf.read(f"{book_dir}project.yaml"))
                books.append({"name": proj_data.get("name", ""), "path": book_dir, "source_zip": ps})
        elif kind == "single":
            pn = "project.yaml" if "project.yaml" in names else "project.json"
            proj_data = yaml.safe_load(zf.read(pn))
            books.append({"name": proj_data.get("name", ""), "path": "", "source_zip": ps})
        elif kind == "config":
            config_data = yaml.safe_load(zf.read("config.yaml"))

    # 格式契约演进规则（backup-restore spec）：高于本应用支持的格式版本一律拒绝，
    # 防止新格式包被旧应用静默半恢复。v0（无版本号）按兼容模式全量回吃。
    if schema_version and schema_version > 1:
        raise ValueError(
            f"备份包格式版本较高（v{int(schema_version)}），请先升级应用到最新版本再恢复"
        )

    return {"books": books, "config": config_data, "warnings": warnings, "schema_version": schema_version}


async def persist_package(db, user_id: str, paths: list[str], include_config: bool = True) -> dict:
    """逐书落库+可选配置恢复；书为原子单元（单书 SAVEPOINT），失败可单独重试。

    书全部落库后执行智能挂回（backup-restore spec）：active 配置唯一→全挂；
    书内模型名命中恰一个配置→挂之；否则置空待选。
    """
    results = []
    info = parse_package(paths)

    if info["config"] and include_config:
        await _restore_config(db, user_id, info["config"])

    novel_ids: list[str] = []
    for ps in paths:
        p = Path(ps)
        if not p.exists():
            continue
        try:
            zf = zipfile.ZipFile(p)
        except zipfile.BadZipFile:
            continue
        kind = detect_kind(zf)
        validate_paths(zf)

        if kind == "assets":
            meta = yaml.safe_load(zf.read("backup.yaml"))
            for entry in meta.get("books", []):
                slug = entry.get("slug", "")
                book_dir = f"projects/{slug}/"
                try:
                    async with db.begin_nested():
                        novel_id = await _import_single_book(db, zf, book_dir, user_id)
                    novel_ids.append(novel_id)
                    results.append({"book_id": book_dir, "status": "ok", "novel_id": novel_id})
                except Exception:
                    results.append({"book_id": book_dir, "status": "failed"})
        elif kind == "single":
            pn = "project.yaml" if "project.yaml" in set(zf.namelist()) else "project.json"
            try:
                async with db.begin_nested():
                    novel_id = await _import_single_book(db, zf, "", user_id)
                novel_ids.append(novel_id)
                results.append({"book_id": pn, "status": "ok", "novel_id": novel_id})
            except Exception:
                results.append({"book_id": pn, "status": "failed"})

    reattach = (
        await _reattach_configs(db, user_id, novel_ids)
        if novel_ids
        else {"mode": "none", "attached": 0}
    )
    return {"results": results, "warnings": info.get("warnings", []), "reattach": reattach}


async def _import_single_book(db, zf: zipfile.ZipFile, book_dir: str, user_id: str) -> str:
    """从 zip 内目录恢复一本书的全部资产。"""
    from chapters.store import (
        _disassemble_scalars,
        _replace_children,
    )
    from filesystem.paths import THREADS_PATH, route_relative_path
    from models.archive import Archive, ChapterPrompt
    from models.chapter import Chapter, ChapterVersion
    from models.project import Novel
    from models.project_setting import ProjectSetting
    from models.volume import (
        Volume,
        VolumeChapterPlan,
        VolumeCharacterVoice,
        VolumeConflictLadder,
        VolumeStage,
    )

    names = set(zf.namelist())
    pn = "project.yaml" if f"{book_dir}project.yaml" in names else "project.json"
    proj_data = yaml.safe_load(zf.read(f"{book_dir}{pn}"))

    slug = proj_data.get("slug", f"imp-{uuid.uuid4().hex[:6]}")
    # 同名书恢复为《书名（备份）》递增命名；slug 冲突同样递增（user+slug 唯一约束）
    base_name = proj_data.get("name", "导入书")
    name = await _unique_book_name(db, user_id, base_name)
    n = 0
    while await _slug_taken(db, user_id, slug):
        n += 1
        slug = f"{slug}-backup{n}"
    root_path = f"./data/{slug}"

    novel = Novel(
        user_id=user_id, name=name,
        slug=slug, root_path=root_path, source="import",
        current_phase=proj_data.get("current_phase", "write"),
        ai_model=proj_data.get("ai_model", ""),
        created_at=datetime.fromisoformat(proj_data["created_at"]) if proj_data.get("created_at") else None,
    )
    db.add(novel)
    await db.flush()

    # story.yaml / threads.yaml 恢复（与导出侧 dump_book_into 对称；
    # 往返测试发现缺口：此前这两个文件只导出不导入，恢复后简介/线索静默丢失）
    for rel, key in (("story.yaml", "story"), (THREADS_PATH, "threads")):
        arc_name = f"{book_dir}{rel}"
        if arc_name not in set(names):
            continue
        data = yaml.safe_load(zf.read(arc_name))
        if data:
            db.add(ProjectSetting(
                root_path=root_path, key=key,
                content=json.dumps(data, ensure_ascii=False),
            ))

    # 设定恢复
    for name in sorted(names):
        if not name.startswith(f"{book_dir}settings/") or not name.endswith((".yaml", ".yml")):
            continue
        rel = name[len(book_dir):]
        data = yaml.safe_load(zf.read(name))
        if data:
            key = route_relative_path(rel)
            db.add(ProjectSetting(
                root_path=root_path, key=key,
                content=json.dumps(data, ensure_ascii=False),
            ))

    # 卷 + 卷纲四子表
    for name in sorted(names):
        if not name.startswith(f"{book_dir}volumes/") or not name.endswith(".yaml"):
            continue
        vol_data = yaml.safe_load(zf.read(name))
        vol = Volume(
            project_id=novel.id, volume_no=vol_data.get("volume", 1),
            title=vol_data.get("title", ""), summary=vol_data.get("summary", ""),
            direction_method=vol_data.get("direction_method"),
            template_name=vol_data.get("template_name"),
            core_conflict=vol_data.get("core_conflict"),
            emotional_arc=vol_data.get("emotional_arc"),
            arc_mode=vol_data.get("arc_mode"),
            primary_drive=vol_data.get("primary_drive"),
            info_gap_start=vol_data.get("info_gap_start"),
            info_gap_end=vol_data.get("info_gap_end"),
            chapter_target=vol_data.get("chapter_target"),
        )
        db.add(vol)
        await db.flush()

        for i, s in enumerate(vol_data.get("stages") or []):
            db.add(VolumeStage(volume_id=vol.id, sort_order=i, **{
                k: s.get(k) for k in ("stage_name", "stage_function", "chapter_count")
            }))
        for i, c in enumerate(vol_data.get("conflict_ladders") or []):
            db.add(VolumeConflictLadder(volume_id=vol.id, sort_order=i, **{
                k: c.get(k) for k in ("layer_no", "chapters_range", "obstacle", "turning_type", "turning_point")
            }))
        for i, p in enumerate(vol_data.get("chapter_plans") or []):
            db.add(VolumeChapterPlan(volume_id=vol.id, sort_order=i, **{
                k: p.get(k) for k in ("chapter_no", "title", "summary", "emotional_anchor", "info_gap", "arc_position")
            }))
        for i, v in enumerate(vol_data.get("character_voices") or []):
            db.add(VolumeCharacterVoice(volume_id=vol.id, sort_order=i, **{
                k: v.get(k) for k in ("character_name", "situation", "unfinished", "interlude_thought", "next_action")
            }))

    # 章 + 正文 + 子表 + 版本 + 提示词
    for name in sorted(names):
        if not name.startswith(f"{book_dir}chapters/") or not name.endswith(".yaml"):
            continue
        ch_data = yaml.safe_load(zf.read(name))
        ref = Path(name).stem
        ch_id = str(uuid.uuid4())

        vol_no = ch_data.get("volume", 1)
        vol = (
            await db.scalars(
                select(Volume).where(Volume.project_id == novel.id, Volume.volume_no == vol_no)
            )
        ).first()
        vol_id = vol.id if vol else None

        prose = ch_data.get("prose") or ""
        status = ch_data.get("status", "writing")
        ch = Chapter(
            id=ch_id, project_id=novel.id, volume_id=vol_id,
            ref=ref, title=ch_data.get("title", ""), chapter_no=ref.count("ch-") and int(ref.rsplit("ch-", 1)[-1].split("-")[0].split(".")[0] or 1),
            status=status, word_count=len(prose), has_prose=bool(prose.strip()),
        )

        # 子表恢复（复用 save_chapter 的拆装逻辑）：在 add/flush 前的 pending 对象上
        # 整体替换子表（_replace_children 含 prose 的 ChapterContent），单次 flush 级联
        # 插入——flush 后再赋值子表会触发懒加载越界
        _disassemble_scalars(ch, ch_data)
        _replace_children(ch, ch_data)

        db.add(ch)
        await db.flush()

        # 版本快照
        for vn in sorted(n for n in names if n.startswith(f"{book_dir}versions/{ref}/")):
            ver_num = int(Path(vn).stem.lstrip("v"))
            db.add(ChapterVersion(
                chapter_id=ch_id, version=ver_num, comment="导入恢复",
                snapshot=zf.read(vn).decode("utf-8"),
            ))

        # 提示词
        for pn2 in sorted(n for n in names if n.startswith(f"{book_dir}prompts/{ref}-")):
            pname = Path(pn2).stem.replace(f"{ref}-", "")
            db.add(ChapterPrompt(chapter_id=ch_id, name=pname, content=zf.read(pn2).decode("utf-8")))

        # 归档
        for an in sorted(n for n in names if n.startswith(f"{book_dir}archives/") and n.endswith(".md") and ref in n):
            db.add(Archive(
                chapter_id=ch_id, title=Path(an).stem, content=zf.read(an).decode("utf-8"),
            ))

    await db.flush()
    return str(novel.id)


async def _restore_config(db, user_id: str, config_data: dict) -> dict:
    """配置包恢复（backup-restore spec 裁决）：user 子集只补空、api_configs 同名跳过不覆盖。

    包内 api_key 为导出端明文，落库前经 encrypt_api_key 重加密。
    返回摘要 {created, skipped, user_filled} 供恢复摘要透出。
    """
    from api_configs.crypto import encrypt_api_key
    from models.api_config import ApiConfig
    from models.user import User

    created = skipped = 0
    user_filled: list[str] = []

    user = await db.get(User, user_id)
    if user is None:
        raise ValueError("user_not_found")

    # user 子集：只补空（不覆盖已有值——legacy AI 三件套 + display_name）
    u = config_data.get("user") or {}
    for field in ("display_name", "api_key", "api_base_url", "api_model"):
        incoming = u.get(field) or ""
        current = getattr(user, field) or ""
        if incoming and not current:
            setattr(user, field, incoming)
            user_filled.append(field)
    await db.flush()

    # api_configs：同名跳过不覆盖；密钥重加密；时间字段容错落 None
    existing = {
        c.name
        for c in (
            await db.scalars(select(ApiConfig).where(ApiConfig.user_id == user_id))
        ).all()
    }
    for c in config_data.get("api_configs") or []:
        name = c.get("name") or ""
        if name in existing:
            skipped += 1
            continue
        models_updated_at = None
        if c.get("models_updated_at"):
            try:
                models_updated_at = datetime.fromisoformat(c["models_updated_at"])
            except ValueError:
                models_updated_at = None
        db.add(ApiConfig(
            user_id=user_id,
            name=name,
            vendor=c.get("vendor") or "",
            vendor_display_name=c.get("vendor_display_name") or "",
            vendor_override=c.get("vendor_override") or None,
            # 旧包无 api_format 键 → 默认 openai（与旧版运行行为等价）
            api_format=c.get("api_format") or "openai",
            api_key=encrypt_api_key(c.get("api_key") or ""),
            base_url=c.get("base_url") or "",
            models=c.get("models") or None,
            models_updated_at=models_updated_at,
        ))
        created += 1
    await db.flush()
    return {"created": created, "skipped": skipped, "user_filled": user_filled}


async def _name_taken(db, user_id: str, name: str) -> bool:
    from models.project import Novel

    return (
        await db.scalars(
            select(Novel.id).where(Novel.user_id == user_id, Novel.name == name).limit(1)
        )
    ).first() is not None


async def _slug_taken(db, user_id: str, slug: str) -> bool:
    from models.project import Novel

    return (
        await db.scalars(
            select(Novel.id).where(Novel.user_id == user_id, Novel.slug == slug).limit(1)
        )
    ).first() is not None


async def _unique_book_name(db, user_id: str, base_name: str) -> str:
    """同名书恢复为《书名（备份）》递增命名（backup-restore spec 裁决）。"""
    name = base_name
    if not await _name_taken(db, user_id, name):
        return name
    name = f"{base_name}（备份）"
    n = 2
    while await _name_taken(db, user_id, name):
        name = f"{base_name}（备份{n}）"
        n += 1
    return name


async def _reattach_configs(db, user_id: str, novel_ids: list[str]) -> dict:
    """智能挂回（backup-restore spec）：active 配置唯一→全挂；书内模型名命中恰一个
    配置→挂之；否则置空待选。幂等：已有挂回的书不重挂。"""
    from models.api_config import ApiConfig
    from models.project import Novel

    def _models(c) -> list:
        try:
            return json.loads(c.models or "[]")
        except Exception:
            return []

    actives = (await db.scalars(
        select(ApiConfig).where(ApiConfig.user_id == user_id, ApiConfig.status == "active")
    )).all()
    attached = 0

    if len(actives) == 1:
        mode = "unique_active"
        for nid in novel_ids:
            novel = await db.get(Novel, nid)
            if novel and not novel.api_config_id:
                novel.ai_config_id = actives[0].id
                attached += 1
    else:
        mode = "by_model"
        for nid in novel_ids:
            novel = await db.get(Novel, nid)
            if not novel or novel.ai_config_id or not novel.ai_model:
                continue
            hits = [c for c in actives if novel.ai_model in _models(c)]
            if len(hits) == 1:
                novel.ai_config_id = hits[0].id
                attached += 1
    return {"mode": mode, "attached": attached}
