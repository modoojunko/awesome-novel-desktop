"""包导入引擎（c-novel-export-roundtrip PR2）。

单轨升级恢复路径：备份包 → 形态探测+校验 → 逐书单事务落库+智能挂回。
零迁移零召回（旧库留档零接触）。
"""

import json
import re
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

import yaml
from sqlalchemy import select

from backup.format import FORMAT_VERSION


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
            # 单书包同样受版本闸约束（此前只有 assets 包读版本——修洞）
            sv = proj_data.get("format_version", 0) if isinstance(proj_data, dict) else 0
            schema_version = max(schema_version or 0, sv or 0)
            books.append({"name": proj_data.get("name", ""), "path": "", "source_zip": ps})
        elif kind == "config":
            config_data = yaml.safe_load(zf.read("config.yaml"))

    # 格式契约演进规则（backup-restore spec）：高于本应用支持的格式版本一律拒绝，
    # 防止新格式包被旧应用静默半恢复。v0（无版本号）按兼容模式全量回吃。
    if schema_version and schema_version > FORMAT_VERSION:
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
                        book_warnings: list[str] = []
                        novel_id = await _import_single_book(
                            db, zf, book_dir, user_id, warnings=book_warnings
                        )
                    novel_ids.append(novel_id)
                    results.append({
                        "book_id": book_dir, "status": "ok", "novel_id": novel_id,
                        "warnings": book_warnings,
                    })
                except Exception:
                    results.append({"book_id": book_dir, "status": "failed"})
        elif kind == "single":
            pn = "project.yaml" if "project.yaml" in set(zf.namelist()) else "project.json"
            try:
                async with db.begin_nested():
                    book_warnings = []
                    novel_id = await _import_single_book(
                        db, zf, "", user_id, warnings=book_warnings
                    )
                novel_ids.append(novel_id)
                results.append({
                    "book_id": pn, "status": "ok", "novel_id": novel_id,
                    "warnings": book_warnings,
                })
            except Exception:
                results.append({"book_id": pn, "status": "failed"})

    reattach = (
        await _reattach_configs(db, user_id, novel_ids)
        if novel_ids
        else {"mode": "none", "attached": 0}
    )
    # 逐书容错提示（伏笔章引用解析失败等）并进总 warnings——「置 NULL＋warning
    # 计数、不丢行」的契约要能在恢复摘要里看到
    book_level = [w for r in results for w in r.get("warnings", [])]
    return {
        "results": results,
        "warnings": info.get("warnings", []) + book_level,
        "reattach": reattach,
    }




async def _import_characters(db, zf, names: list[str], book_dir: str, novel) -> None:
    """角色段恢复：v2 直读 + v1 映射；主角收敛（>1 时保 seq 最小）。"""
    from characters.legacy_map import map_legacy_character
    from models.character import Character, CharacterRelation

    seq = 0

    # v2：characters/characters.yaml（数组，含 id/seq/legacy/relations 内嵌 owner/other id）
    v2_name = f"{book_dir}characters/characters.yaml"
    v2_rel_name = f"{book_dir}characters/relations.yaml"
    if v2_name in set(names):
        cards = yaml.safe_load(zf.read(v2_name)) or []
        # id 冲突策略：包内 id 与本库已有角色撞车（同一包导回同一库/两机互导）→
        # 重新生成 id 保内容；包内引用（relations / chapter_characters）经映射跟随
        all_existing = set(
            await db.scalars(select(Character.id))
        )
        id_remap: dict[str, str] = {}
        for raw in cards:
            old_id = raw.get("id")
            if old_id and old_id in all_existing and old_id not in id_remap:
                id_remap[old_id] = str(uuid.uuid4())
        for raw in cards:
            seq += 1
            raw_id = raw.get("id")
            if raw_id and raw_id in id_remap:
                raw_id = id_remap[raw_id]
            ch = Character(
                id=raw_id or str(uuid.uuid4()),
                novel_id=novel.id,
                seq=raw.get("seq") or seq,
                name=str(raw.get("name") or f"\u0000{uuid.uuid4().hex[:12]}"),
                aliases=json.dumps(raw.get("aliases") or [], ensure_ascii=False),
                role=raw.get("role") or "配角",
                persona=raw.get("persona") or "",
                dossier=json.dumps(raw.get("dossier") or {}, ensure_ascii=False),
                cog=json.dumps(raw.get("cog") or {}, ensure_ascii=False),
                legacy=json.dumps(raw.get("legacy") or {}, ensure_ascii=False),
            )
            db.add(ch)
        rels = yaml.safe_load(zf.read(v2_rel_name)) if v2_rel_name in set(names) else []
        from models.character import CharacterRelation as _CR
        all_existing_rels = set(
            await db.scalars(select(_CR.id))
        )
        for raw in rels or []:
            rel_id = raw.get("id")
            if rel_id and rel_id in all_existing_rels:
                rel_id = str(uuid.uuid4())
            if rel_id:
                all_existing_rels.add(rel_id)
            db.add(CharacterRelation(
                id=rel_id or str(uuid.uuid4()),
                novel_id=novel.id,
                owner_id=id_remap.get(raw["owner_id"], raw["owner_id"]),
                other_id=id_remap.get(raw["other_id"], raw["other_id"]),
                rel_type=raw.get("rel_type") or "",
                stance=raw.get("stance") or "", note=raw.get("note") or "",
                ch_ref=raw.get("ch_ref") or "",
            ))
        await db.flush()
        # 同步计数器（不倒退、不复用）
        if cards:
            novel.character_seq_high = max(novel.character_seq_high, max(
                int(c.get("seq") or 0) for c in cards))
        return

    # v1：settings/character-setting/*.yaml → 映射进新形状
    v1_names = sorted(
        n for n in names
        if n.startswith(f"{book_dir}settings/character-setting/") and n.endswith(".yaml")
    )
    prot_seen = False
    for name in v1_names:
        raw = yaml.safe_load(zf.read(name))
        if not raw:
            continue
        mapped = map_legacy_character(raw)
        seq += 1
        role = mapped["role"]
        if role == "主角":
            if prot_seen:
                role = "配角"  # 主角收敛：保第一个
            prot_seen = True
        ch = Character(
            novel_id=novel.id, seq=seq, name=mapped["name"] or f"\u0000{uuid.uuid4().hex[:12]}",
            aliases=json.dumps(mapped["aliases"], ensure_ascii=False),
            role=role, persona=mapped["persona"],
            dossier=json.dumps(mapped["dossier"], ensure_ascii=False),
            cog=json.dumps(mapped["cog"], ensure_ascii=False),
            legacy=json.dumps(mapped["legacy"], ensure_ascii=False),
        )
        db.add(ch)
    if v1_names:
        await db.flush()
        novel.character_seq_high = max(novel.character_seq_high, seq)

async def _resolve_character_ids(db, novel_id: str) -> dict[str, str]:
    """本书的名字/别名 → 角色 id（导入路径的 id 绑定用）。"""
    from models.character import Character

    cards = (
        await db.scalars(select(Character).where(Character.novel_id == novel_id))
    ).all()
    out: dict[str, str] = {}
    for c in cards:
        if c.name:
            out.setdefault(c.name, c.id)
        try:
            for alias in json.loads(c.aliases or "[]"):
                out.setdefault(alias, c.id)
        except (TypeError, ValueError):
            continue
    return out


# ── 伏笔段（foreshadow-settings-v2 tasks 3.1/3.2）────────────────────────────

# v1 自由文本章引用 → 规范 ref 的容错形态："vol-1-ch-2" / "1-2"（含全半角连接符）
_CANON_REF_RE = re.compile(r"^vol-(\d+)-ch-(\d+)$", re.IGNORECASE)
_SHORT_REF_RE = re.compile(r"^(\d+)\s*[-–—－]\s*(\d+)$")


def _normalize_free_chapter_ref(value) -> str:
    """v1 `introduced_in` 自由文本 → vol-N-ch-M 规范 ref；解析不了返回空串。

    读窗只归一数字形态（"1-1"/"vol-1-ch-1" 等）；叙述性文本（垃圾文本）返回
    ""，由调用方置 NULL＋warning，不丢行。
    """
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    m = _CANON_REF_RE.match(text)
    if m:
        return f"vol-{int(m.group(1))}-ch-{int(m.group(2))}"
    m = _SHORT_REF_RE.match(text)
    if m:
        return f"vol-{int(m.group(1))}-ch-{int(m.group(2))}"
    return ""


def _hooks_v1_to_entries(data: dict) -> list[dict]:
    """v1 读窗（tasks 3.2）：KV 三数组 {active,resolved,abandoned} → v3 条目列表。

    逐条细则（spec + tasks，全部有测试钉住）：
    - 数组名 → status（条目内 status 只有 "mentioned" 特判：迁为 active＋
      mentioned 走 introduced_in 同一绑定——spec「mentioned_in_chapter_id=引入章」）；
    - introduced_in 自由文本经 _normalize_free_chapter_ref 归一 → introduced/mentioned
      章 ref，包内解析失败由 _import_hooks 置 NULL＋warning；
    - priority 混形（int/"1"/"high"）走 hooks_model.normalize_priority，非法置默认 2；
    - type 未知 slug 置默认 mystery（novel_hooks.type 列 nullable=False 且有默认值，
      「置空」不可落库——spec 两选项按 hooks_model 现状取后者）；
    - v1 无 seq/planned/resolved/payoff_note：seq 留空由导入顺序取号器补，其余置空。
    """
    from settings.hooks_model import HOOK_TYPE_KEYS, normalize_priority

    entries: list[dict] = []
    for array_name, status in (
        ("active", "active"),
        ("resolved", "resolved"),
        ("abandoned", "abandoned"),
    ):
        for raw in data.get(array_name) or []:
            if not isinstance(raw, dict):
                continue  # 数组里的非对象条目是格式噪声，不落行
            raw_introduced = str(raw.get("introduced_in") or "").strip()
            introduced_ref = _normalize_free_chapter_ref(raw_introduced)
            entry_status = status
            mentioned_ref = ""
            if str(raw.get("status") or "").strip().lower() == "mentioned":
                entry_status = "active"
                mentioned_ref = introduced_ref
            try:
                priority = normalize_priority(raw.get("priority"))
            except ValueError:
                priority = 2
            hook_type = str(raw.get("hook_type") or raw.get("type") or "").strip()
            if hook_type not in HOOK_TYPE_KEYS:
                hook_type = "mystery"
            entries.append({
                "seq": raw.get("seq"),
                "description": str(raw.get("description") or ""),
                "type": hook_type,
                "priority": priority,
                "status": entry_status,
                "introduced_chapter_ref": introduced_ref,
                "planned_chapter_ref": "",
                "resolved_chapter_ref": "",
                "mentioned_chapter_ref": mentioned_ref,
                "payoff_note": "",
                # 内部键：有 introduced_in 原文但归一不出 ref → 导入时记 warning
                "_unparsed_ref": raw_introduced if raw_introduced and not introduced_ref else "",
            })
    return entries


def _hook_row_fields(raw: dict, warnings: list[str], index: int, ref_to_id: dict) -> dict:
    """v3 条目 → NovelHook 列 dict（白名单外键一律忽略，混形兜底不丢行）。"""
    from settings.hooks_model import (
        DESCRIPTION_MAX,
        HOOK_STATUSES,
        HOOK_TYPE_KEYS,
        PAYOFF_NOTE_MAX,
        normalize_priority,
    )

    try:
        priority = normalize_priority(raw.get("priority"))
    except ValueError:
        priority = 2
        warnings.append(f"伏笔第 {index} 条 priority 非法，已置默认「中」")
    status = str(raw.get("status") or "").strip()
    if status not in HOOK_STATUSES:
        status = "active"
        warnings.append(f"伏笔第 {index} 条 status 非法，已置默认 active")
    hook_type = str(raw.get("type") or "").strip()
    if hook_type not in HOOK_TYPE_KEYS:
        hook_type = "mystery"

    def _bind(column: str) -> str | None:
        ref = str(raw.get(column) or "").strip()
        if not ref:
            return None
        chapter_id = ref_to_id.get(ref)
        if chapter_id is None:
            # 解析失败：置 NULL＋warning，行不丢（backup-restore spec 硬契约）
            warnings.append(f"伏笔第 {index} 条的章节引用 {ref} 无法解析，已置空")
            return None
        return chapter_id

    return {
        "description": str(raw.get("description") or "").strip()[:DESCRIPTION_MAX],
        "type": hook_type,
        "priority": priority,
        "status": status,
        "introduced_chapter_id": _bind("introduced_chapter_ref"),
        "planned_chapter_id": _bind("planned_chapter_ref"),
        "resolved_chapter_id": _bind("resolved_chapter_ref"),
        "mentioned_chapter_id": _bind("mentioned_chapter_ref"),
        "payoff_note": str(raw.get("payoff_note") or "").strip()[:PAYOFF_NOTE_MAX],
    }


async def _import_hooks(
    db, zf: zipfile.ZipFile, names: set[str], book_dir: str, novel, warnings: list[str]
) -> None:
    """伏笔段恢复：v3 直读（hooks/hooks.yaml）＋ v1 读窗（settings/hooks.yaml 三数组）。

    顺序约束（backup-restore spec，落库顺序显式注释）：本函数必须在「章循环落库
    之后」调用——ref→id 重绑按本书已落库的 chapters(ref) 解析。它与既有的
    「characters 先于 chapters（出场引用绑定 id）」顺序约束并列：角色喂章的
    子表，伏笔在章循环收尾重绑，两段都不倒序。
    """
    from models.chapter import Chapter
    from models.hook import NovelHook

    v3_name = f"{book_dir}hooks/hooks.yaml"
    v1_name = f"{book_dir}settings/hooks.yaml"
    if v3_name in names:
        data = yaml.safe_load(zf.read(v3_name)) or {}
        entries = data.get("hooks") if isinstance(data, dict) else data
        entries = list(entries or [])
    elif v1_name in names:
        # v1 读窗：settings/hooks.yaml 不会进 project_settings——settings 循环里
        # route_relative_path 对 hooks 已无路由（返回 None 被跳过），旧 KV 键零残留
        data = yaml.safe_load(zf.read(v1_name))
        entries = _hooks_v1_to_entries(data if isinstance(data, dict) else {})
    else:
        return
    if not entries:
        return

    # ref → id 表：此刻本书 chapters 已全部落库（顺序约束见 docstring）
    ref_to_id = {
        ref: cid
        for cid, ref in (
            await db.execute(
                select(Chapter.id, Chapter.ref).where(Chapter.project_id == novel.id)
            )
        ).all()
    }

    # 包内 id 撞车重排沿角色先例：包 id 与本库已有伏笔撞车（同包导回同一库/
    # 两机互导）→ 重新生成 id 保内容（v3 导出不写 id，此分支只兜底容错）
    all_existing = set(await db.scalars(select(NovelHook.id)))
    id_remap: dict[str, str] = {}
    for raw in entries:
        if isinstance(raw, dict):
            old_id = raw.get("id")
            if old_id and old_id in all_existing and old_id not in id_remap:
                id_remap[old_id] = str(uuid.uuid4())

    seen_seqs: set[int] = set()
    for index, raw in enumerate(entries, start=1):
        if not isinstance(raw, dict):
            warnings.append(f"伏笔第 {index} 条不是对象，已跳过")
            continue
        if raw.get("_unparsed_ref"):
            # v1 读窗：introduced_in 有原文但归一不出 ref → 置 NULL＋warning，不丢行
            warnings.append(
                f"伏笔第 {index} 条的引入章「{raw['_unparsed_ref']}」无法解析为章节引用，已置空"
            )
        raw_id = raw.get("id")
        if raw_id and raw_id in id_remap:
            raw_id = id_remap[raw_id]
        # seq：包值优先；缺失/非法/包内重复（v1 读窗常态）→ 按导入顺序同事务取号
        try:
            seq = int(raw.get("seq") or 0)
        except (TypeError, ValueError):
            seq = 0
        if seq <= 0 or seq in seen_seqs:
            seq = novel.hook_seq_high + 1
        novel.hook_seq_high = max(novel.hook_seq_high, seq)
        seen_seqs.add(seq)

        fields = _hook_row_fields(raw, warnings, index, ref_to_id)
        db.add(NovelHook(
            id=raw_id or str(uuid.uuid4()),
            novel_id=novel.id,
            seq=seq,
            **fields,
        ))
    await db.flush()


async def _import_single_book(
    db, zf: zipfile.ZipFile, book_dir: str, user_id: str, warnings: list[str] | None = None
) -> str:
    """从 zip 内目录恢复一本书的全部资产。

    warnings：可选收集列表——章 ref 解析失败等「容错不丢行」的提示逐条追加，
    由 persist_package 并进恢复摘要（不传则静默容错，直调方兼容旧签名）。
    """
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

    # 角色段恢复（character-settings-v2）：必须在 chapters 之前落库（出场引用绑定 id）。
    # v2 布局 = characters/*.yaml（直读）；v1 布局 = settings/character-setting/*.yaml（映射）。
    # 设定循环不碰角色文件（route_relative_path 对 character: 前缀会返回 KV 键——
    # 真表上线后那是无人读的死数据；防御性 continue 在下方 settings 分支里）。
    await _import_characters(db, zf, names, book_dir, novel)

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
        # v1 角色文件已由 _import_characters 处理；这里跳过防写回 character: KV
        if name.startswith(f"{book_dir}settings/character-setting/"):
            continue
        rel = name[len(book_dir):]
        data = yaml.safe_load(zf.read(name))
        if not data:
            continue
        key = route_relative_path(rel)
        if key is None:
            continue  # 未知/未路由的 settings 文件不入 KV（否则 NOT NULL 炸整书）
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
        # 出场角色 id 绑定（character-settings-v2）：包里是名字数组，先建角色映射
        # （characters 必须先于 chapters 落库——persist 流程已保证），未命中留 NULL+快照
        _disassemble_scalars(ch, ch_data)
        name_map = await _resolve_character_ids(db, novel.id)
        outline_names = [
            str(n).strip()[:50]
            for n in (ch_data.get("outline") or {}).get("characters") or []
            if str(n).strip()
        ]
        await _replace_children(db, ch, ch_data, character_ids={
            n: name_map.get(n) for n in outline_names
        })

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

    # 伏笔段恢复（foreshadow-settings-v2）：必须在「章循环落库之后」执行——
    # ref→id 重绑按本书已落库的 chapters 解析（顺序约束与上方「角色段必须在
    # chapters 之前落库：出场引用绑定 id」并列，落库顺序不得倒置）。
    # 另：settings/hooks.yaml（v1 KV 形状）不会被 settings 循环写进
    # project_settings——route_relative_path 已无 hooks 路由，旧 KV 键零残留。
    hook_warnings: list[str] = warnings if warnings is not None else []
    await _import_hooks(db, zf, names, book_dir, novel, hook_warnings)

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
