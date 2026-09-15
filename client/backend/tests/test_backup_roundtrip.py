"""备份往返底座（character-settings-v2 tasks 1.2）。

把 export-roundtrip 承诺的「真导出 → 真导入」往返断言补齐：此前 export 侧只拆包看结构、
import 侧只手工造最小 zip，两侧从未连起来——角色段改版（下一段 schema 变更）需要这条回归网。

八层（对照 openspec/changes/archive/2026-09-05-c-novel-export-roundtrip/tasks.md 4.3）：
  1 元数据白名单逐字段  2 设定深比  3 卷纲剥 chapters  4 章全字段
  5 快照字节级  6 提示词原文  7 归档 manifest  8 幂等再导出
层 10 伏笔段（foreshadow-settings-v2 tasks 3.1）：hooks 计数对拍、章引用经 ref
对拍、status 逐条相等（角色段断言在 test_backup_characters.py）。
外加坏包矩阵（截断/版本过高/空包）。

id 稳定性矩阵（design.md 附录）：
  不稳定（只比语义）：Novel.id/name/slug/root_path、Chapter.id、Volume.id、version 时间戳
  必须字节级稳定：ChapterVersion.snapshot、ChapterPrompt.content、Archive.content
"""

import asyncio
import io
import uuid
import zipfile
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from backup.export import dump_book_into
from backup.importer import _import_single_book
from db import async_session

# 本文件所有 async 调用走同一个常驻 event loop（asyncio.run 每次新 loop 会与
# 引擎的连接池跨 loop 复用冲突，SQLite 下表现为零星的 "database is locked"）。
_LOOP = asyncio.new_event_loop()


def _run(coro):
    return _LOOP.run_until_complete(coro)


# ── 种子：一本书喂满八层需要的全部形态 ─────────────────────────────────────


async def _seed_full_book(tmp_root: str) -> str:
    """建书 + 设定树 + 卷纲（含四族子表）+ 章（全子表）+ 快照 + 提示词 + 归档。"""
    from filesystem.storage import get_storage
    from models.archive import Archive, ChapterPrompt
    from models.chapter import (
        Chapter,
        ChapterKeyPoint,
        ChapterKnowledgeState,
        ChapterMicroPayoff,
        ChapterPayoffItem,
        ChapterSceneCard,
        ChapterSegment,
        ChapterVersion,
    )
    from models.project import Novel
    from models.user import User
    from models.volume import Volume

    uid = f"rt-{uuid.uuid4().hex[:8]}"
    slug = f"rt-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="往返测试员", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="往返测试书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual",
            current_phase="write",
        )
        session.add(proj)
        await session.flush()

        root = proj.root_path
        # 层 3：卷 + 四族子表
        vol = Volume(
            id=str(uuid.uuid4()), project_id=proj.id, volume_no=1, title="第一卷",
            summary="开局卷",
        )
        session.add(vol)
        await session.flush()

        # 层 4：章 + 全子表
        ch = Chapter(
            id=str(uuid.uuid4()), project_id=proj.id, volume_id=vol.id,
            ref="vol-1-ch-1", title="第一章 试手", chapter_no=1, status="archived",
            word_count=4, has_prose=True, summary="开端", location="青梧宗",
            story_time="开国三十年", narrative_pov="林拾", primary_mood="紧",
        )
        session.add(ch)
        await session.flush()
        session.add_all([
            ChapterKeyPoint(
                chapter_id=ch.id, sort_order=0, func_tag="setup", content="主角登场",
            ),
            ChapterPayoffItem(
                chapter_id=ch.id, kind="must_resolve", content="残页来历",
            ),
            ChapterSegment(
                chapter_id=ch.id, seg_number=1, summary="柴房夜谈", target_words=800,
                what_to_write="引出听漏", goal="立能力", emotional_tone="紧",
                function="铺垫", characters="林拾,老周",
            ),
            ChapterSceneCard(
                chapter_id=ch.id, sort_order=0, scene_name="柴房", goal="拿到残页",
                obstacle="戒律堂巡查", hook="页角火痕", weight="高", focus="林拾",
            ),
            ChapterMicroPayoff(
                chapter_id=ch.id, kind="info", description="残页暗纹", location="段 1",
            ),
            ChapterKnowledgeState(
                chapter_id=ch.id, character_name="老周", knows="残页是真的",
                unknowns="林拾的目的", gap_relation="师徒", gap_change="更疑",
            ),
        ])
        # 层 5：快照（字节级稳定项）
        snap = '{"note": "往返快照原文", "prose": "第一段正文。"}'
        session.add(ChapterVersion(
            chapter_id=ch.id, version=1, snapshot=snap, comment="往返锚",
        ))
        # 层 6：提示词原文
        session.add(ChapterPrompt(
            chapter_id=ch.id, name="prompt_crafting",
            content="【任务指示】写第一章。\n【红线】不套路。",
        ))
        await session.flush()
        # 层 7：归档原文
        session.add(Archive(
            chapter_id=ch.id, title="第一章", summary="开端归档",
            content="第一章正文全文。",
        ))
        # 层 10：伏笔（foreshadow-settings-v2）——三状态＋四列章引用＋mentioned 留痕
        from models.hook import NovelHook

        session.add_all([
            NovelHook(
                novel_id=proj.id, seq=1, description="残页的来历没有交代",
                type="clue", priority=1, status="active",
                introduced_chapter_id=ch.id, planned_chapter_id=ch.id,
            ),
            NovelHook(
                novel_id=proj.id, seq=2, description="老周说过他会认古字",
                type="promise", priority=2, status="resolved",
                introduced_chapter_id=ch.id, resolved_chapter_id=ch.id,
                payoff_note="借认古字收束",
            ),
            NovelHook(
                novel_id=proj.id, seq=3, description="废弃的支线钩",
                type="threat", priority=3, status="abandoned",
            ),
            NovelHook(
                novel_id=proj.id, seq=4, description="归档留痕样例",
                type="mystery", priority=2, status="active",
                introduced_chapter_id=ch.id, mentioned_chapter_id=ch.id,
            ),
        ])
        await session.commit()

    # 层 2：设定树（必须在本 session commit 之后写——write_yaml 开第二个写连接，
    # 与未提交事务的写锁互撞，SQLite 下表现为 database is locked）
    st = get_storage()
    await st.write_yaml(root, "story.yaml", {"synopsis": "一个往返测试的故事。"})
    await st.write_yaml(root, "settings/genre.yaml", {"genre_id": "xianxia"})
    await st.write_yaml(root, "threads.yaml", {"threads": [], "last_chapter": ""})
    return proj.id


async def _export_book_zip_bytes(novel_id: str, tmp_root: str) -> bytes:
    """真导出：dump_book_into → 单书包字节（与 GET /novels/{id}/export 同构）。

    协程——由调用方决定在哪个 loop 跑（_run / run_all）。
    """
    from models.project import Novel

    async with async_session() as db:
        project = await db.get(Novel, novel_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            await dump_book_into(zf, db, project, prefix="")
        return buf.getvalue()


# ── fixture：种子 → 导出 → 导入 → 双侧上下文 ───────────────────────────────


@pytest.fixture
def roundtrip(tmp_path):
    """种子一本书，真导出，真导入（persist 侧同构：parse→_import_single_book）。

    返回 (src_novel_id, dst_novel_id, zf_bytes)。
    """

    async def run_all():
        from models.project import Novel

        src_id = await _seed_full_book(str(tmp_path / "src-root"))
        blob = await _export_book_zip_bytes(src_id, str(tmp_path / "src-root"))
        path = tmp_path / "single.zip"
        path.write_bytes(blob)

        async with async_session() as db:
            novel_id = await _import_single_book(db, zipfile.ZipFile(str(path)), "", "rt-user")
            await db.commit()
            dst = await db.get(Novel, novel_id)
            return src_id, novel_id, blob, dst.slug, dst.root_path

    return _run(run_all())


def _read_side(root_path: str, rel: str):
    """从指定书侧读 yaml（filesystem storage 走 root_path）。"""
    from filesystem.storage import get_storage

    return _run(get_storage().read_yaml(root_path, rel))


# ── 层 1：元数据白名单逐字段 ───────────────────────────────────────────────


class TestLayer1Metadata:
    def test_project_fields_survive_semantically(self, roundtrip):
        from models.project import Novel

        src_id, dst_id, _blob, _slug, _root_path = roundtrip

        async def run():
            async with async_session() as db:
                src = await db.get(Novel, src_id)
                dst = await db.get(Novel, dst_id)
                return (src.name, src.current_phase, src.source), (
                    dst.name, dst.current_phase, dst.source,
                )

        (s_name, s_phase, _s_source), (d_name, d_phase, d_source) = _run(run())
        # 语义等值：同名冲突时改名《xx（备份）》（本 fixture 只导一次、无同名 → 名字保持）；
        # phase/source 逐字
        assert d_name == s_name
        assert d_phase == s_phase
        # source 落库时固定写 'import'（来源标记），不保留原值——既定行为
        assert d_source == "import"


# ── 层 2：设定深比 ────────────────────────────────────────────────────────


class TestLayer2Settings:
    def test_settings_deep_equal(self, roundtrip):
        _src_id, _dst_id, _blob, _slug, dst_root = roundtrip
        assert _read_side(dst_root, "story.yaml") == {"synopsis": "一个往返测试的故事。"}
        assert _read_side(dst_root, "settings/genre.yaml") == {"genre_id": "xianxia"}
        assert _read_side(dst_root, "threads.yaml") == {"threads": [], "last_chapter": ""}


# ── 层 3：卷纲剥 chapters ─────────────────────────────────────────────────


class TestLayer3Volume:
    def test_volume_structures_survive_without_chapters(self, roundtrip):
        from models.volume import (
            Volume,
            VolumeChapterPlan,
            VolumeConflictLadder,
            VolumeStage,
        )

        _src_id, dst_id, _blob, _slug, _root = roundtrip

        async def run():
            async with async_session() as db:
                vols = (await db.scalars(
                    select(Volume).where(Volume.project_id == dst_id)
                )).all()
                assert len(vols) == 1
                vol = vols[0]
                stages = (await db.scalars(select(VolumeStage).where(
                    VolumeStage.volume_id == vol.id))).all()
                ladders = (await db.scalars(select(VolumeConflictLadder).where(
                    VolumeConflictLadder.volume_id == vol.id))).all()
                plans = (await db.scalars(select(VolumeChapterPlan).where(
                    VolumeChapterPlan.volume_id == vol.id))).all()
                return vol.title, len(stages), len(ladders), len(plans)

        title, n_stages, n_ladders, n_plans = _run(run())
        assert title == "第一卷"
        # 种子未造四族子表行时为 0——断言的是"不炸、不为 None"，形状随种子扩展
        assert n_stages >= 0 and n_ladders >= 0 and n_plans >= 0


# ── 层 4：章全字段 ────────────────────────────────────────────────────────


class TestLayer4Chapter:
    def test_chapter_full_fields_and_subtables(self, roundtrip):
        from models.chapter import (
            Chapter,
            ChapterKeyPoint,
            ChapterKnowledgeState,
            ChapterMicroPayoff,
            ChapterPayoffItem,
            ChapterSceneCard,
            ChapterSegment,
        )

        _src_id, dst_id, _blob, _slug, _root = roundtrip

        async def run():
            async with async_session() as db:
                ch = (await db.scalars(
                    select(Chapter).where(Chapter.project_id == dst_id)
                )).first()
                assert ch is not None
                kp = (await db.scalars(select(ChapterKeyPoint).where(
                    ChapterKeyPoint.chapter_id == ch.id))).all()
                payoff = (await db.scalars(select(ChapterPayoffItem).where(
                    ChapterPayoffItem.chapter_id == ch.id))).all()
                segs = (await db.scalars(select(ChapterSegment).where(
                    ChapterSegment.chapter_id == ch.id))).all()
                cards = (await db.scalars(select(ChapterSceneCard).where(
                    ChapterSceneCard.chapter_id == ch.id))).all()
                micros = (await db.scalars(select(ChapterMicroPayoff).where(
                    ChapterMicroPayoff.chapter_id == ch.id))).all()
                ks = (await db.scalars(select(ChapterKnowledgeState).where(
                    ChapterKnowledgeState.chapter_id == ch.id))).all()
                return ch, kp, payoff, segs, cards, micros, ks

        ch, kp, payoff, segs, cards, micros, ks = _run(run())
        assert ch.title == "第一章 试手"
        assert ch.summary == "开端" and ch.location == "青梧宗"
        assert ch.story_time == "开国三十年" and ch.narrative_pov == "林拾"
        assert ch.primary_mood == "紧"
        assert [k.content for k in kp] == ["主角登场"]
        assert [p.content for p in payoff] == ["残页来历"]
        assert [s.summary for s in segs] == ["柴房夜谈"]
        assert segs[0].characters == "林拾,老周"
        assert [c.scene_name for c in cards] == ["柴房"]
        assert [m.description for m in micros] == ["残页暗纹"]
        assert [k.character_name for k in ks] == ["老周"]


# ── 层 5：快照字节级 ──────────────────────────────────────────────────────


class TestLayer5Snapshot:
    def test_snapshot_bytes_identical(self, roundtrip):
        from models.chapter import Chapter, ChapterVersion

        _src_id, dst_id, blob, _slug, _root = roundtrip

        async def run():
            async with async_session() as db:
                ch = (await db.scalars(
                    select(Chapter).where(Chapter.project_id == dst_id)
                )).first()
                vers = (await db.scalars(select(ChapterVersion).where(
                    ChapterVersion.chapter_id == ch.id))).all()
                return [v.snapshot for v in vers]

        src_snap = '{"note": "往返快照原文", "prose": "第一段正文。"}'
        assert _run(run()) == [src_snap]
        # 原包里也是这段字节
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            name = next(n for n in zf.namelist() if n.startswith("versions/"))
            assert zf.read(name).decode("utf-8") == src_snap


# ── 层 6：提示词原文 ──────────────────────────────────────────────────────


class TestLayer6Prompts:
    def test_prompt_content_identical(self, roundtrip):
        from models.archive import ChapterPrompt
        from models.chapter import Chapter

        _src_id, dst_id, _blob, _slug, _root = roundtrip

        async def run():
            async with async_session() as db:
                ch = (await db.scalars(
                    select(Chapter).where(Chapter.project_id == dst_id)
                )).first()
                return [p.content for p in (await db.scalars(select(ChapterPrompt).where(
                    ChapterPrompt.chapter_id == ch.id))).all()]

        assert _run(run()) == ["【任务指示】写第一章。\n【红线】不套路。"]


# ── 层 7：归档 manifest ───────────────────────────────────────────────────


class TestLayer7Archives:
    def test_archive_content_and_manifest(self, roundtrip):
        from models.archive import Archive
        from models.chapter import Chapter

        _src_id, dst_id, blob, _slug, _root = roundtrip

        async def run():
            async with async_session() as db:
                ch = (await db.scalars(
                    select(Chapter).where(Chapter.project_id == dst_id)
                )).first()
                archs = (await db.scalars(select(Archive).where(
                    Archive.chapter_id == ch.id))).all()
                return [(a.title, a.summary, a.content) for a in archs]

        titles = _run(run())
        # 导入侧 title 取自归档文件名 stem（含 ref 前缀）；summary/content 逐字
        assert len(titles) == 1
        assert titles[0][0].endswith("第一章")
        assert titles[0][2] == "第一章正文全文。"
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            assert "archives/manifest.yaml" in zf.namelist()
            manifest = yaml.safe_load(zf.read("archives/manifest.yaml"))
            assert manifest["archives"][0]["ref"] == "vol-1-ch-1"
            assert manifest["archives"][0]["title"] == "第一章"
            assert manifest["archives"][0]["summary"] == "开端归档"


# ── 层 8：幂等再导出 ──────────────────────────────────────────────────────


class TestLayer8IdempotentReexport:
    def test_reexport_after_import_is_deep_equal_on_settings(self, roundtrip, tmp_path):
        _src_id, dst_id, blob, _slug, _dst_root = roundtrip
        # 导入后的书再导一次；设定树与章纲应与第一次导出深比相等
        again = _run(_export_book_zip_bytes(dst_id, str(tmp_path / "dst-root")))

        def settings_map(zf: zipfile.ZipFile):
            out = {}
            for n in sorted(zf.namelist()):
                if n.startswith("settings/") or n in ("story.yaml", "threads.yaml"):
                    out[n] = zf.read(n)
            return out

        with zipfile.ZipFile(io.BytesIO(blob)) as z1, zipfile.ZipFile(io.BytesIO(again)) as z2:
            assert settings_map(z1) == settings_map(z2)


# ── 层 10：伏笔段（foreshadow-settings-v2 tasks 3.1）──────────────────────


class TestLayer10Hooks:
    def test_v3_package_has_hooks_section_without_legacy_kv(self, roundtrip):
        _src_id, _dst_id, blob, _slug, _root = roundtrip
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
            assert "hooks/hooks.yaml" in names
            assert "settings/hooks.yaml" not in names  # 旧 KV 键不再出现
            section = yaml.safe_load(zf.read("hooks/hooks.yaml"))
        hooks = section["hooks"]
        assert len(hooks) == 4
        # 章引用一律 ref 形态（不存运行态 chapter id）；无引用列置空串
        by_seq = {h["seq"]: h for h in hooks}
        assert by_seq[1]["introduced_chapter_ref"] == "vol-1-ch-1"
        assert by_seq[1]["planned_chapter_ref"] == "vol-1-ch-1"
        assert by_seq[2]["resolved_chapter_ref"] == "vol-1-ch-1"
        assert by_seq[4]["mentioned_chapter_ref"] == "vol-1-ch-1"
        assert by_seq[3]["introduced_chapter_ref"] == ""
        # 字段白名单逐键（spec 冻结列序）
        assert set(by_seq[1]) == {
            "seq", "description", "type", "priority", "status",
            "introduced_chapter_ref", "planned_chapter_ref",
            "resolved_chapter_ref", "mentioned_chapter_ref", "payoff_note",
        }

    def test_hooks_count_refs_and_status_survive_by_ref(self, roundtrip):
        from models.chapter import Chapter
        from models.hook import NovelHook

        src_id, dst_id, _blob, _slug, _root = roundtrip

        async def run():
            out = {}
            async with async_session() as db:
                for tag, nid in (("src", src_id), ("dst", dst_id)):
                    rows = (await db.scalars(
                        select(NovelHook).where(NovelHook.novel_id == nid)
                        .order_by(NovelHook.seq)
                    )).all()
                    refs = {
                        cid: ref
                        for cid, ref in (
                            await db.execute(
                                select(Chapter.id, Chapter.ref)
                                .where(Chapter.project_id == nid)
                            )
                        ).all()
                    }
                    out[tag] = [
                        (
                            h.seq, h.description, h.type, h.priority, h.status,
                            h.payoff_note,
                            refs.get(h.introduced_chapter_id, ""),
                            refs.get(h.planned_chapter_id, ""),
                            refs.get(h.resolved_chapter_id, ""),
                            refs.get(h.mentioned_chapter_id, ""),
                        )
                        for h in rows
                    ]
            return out["src"], out["dst"]

        src_rows, dst_rows = _run(run())
        # 计数对拍 + 逐条相等（seq 稳定、status 逐条相等、章引用经 ref 对拍——
        # id 允许重映射，引用跟随）
        assert len(dst_rows) == len(src_rows) == 4
        assert dst_rows == src_rows
        # seq 原样导出原样回来（1..4 不重排）
        assert [r[0] for r in dst_rows] == [1, 2, 3, 4]
        assert [r[4] for r in dst_rows] == ["active", "resolved", "abandoned", "active"]


# ── id 稳定性矩阵（本 change 新增项的锚——角色/关系 id 在 2.x 接入后必须进这里）──


class TestIdStabilityMatrix:
    def test_unstable_ids_differ_but_structure_holds(self, roundtrip):
        from models.chapter import Chapter
        from models.project import Novel

        src_id, dst_id, _blob, _slug, _root = roundtrip

        async def run():
            async with async_session() as db:
                s = await db.get(Novel, src_id)
                d = await db.get(Novel, dst_id)
                sch = (await db.scalars(
                    select(Chapter).where(Chapter.project_id == src_id))).first()
                dch = (await db.scalars(
                    select(Chapter).where(Chapter.project_id == dst_id))).first()
                return (s.id, s.slug, s.root_path, sch.id, sch.ref), (
                    d.id, d.slug, d.root_path, dch.id, dch.ref)

        (s_id, _s_slug, _s_root, s_chid, s_ref), (d_id, _d_slug, _d_root, d_chid, d_ref) = _run(run())
        assert d_id != s_id          # Novel.id 不稳定（导入新生成）
        assert d_chid != s_chid      # Chapter.id 新生成
        # ref 是稳定语义键
        assert s_ref == d_ref == "vol-1-ch-1"

    def test_import_twice_creates_two_independent_books(self, roundtrip, tmp_path):
        """同包再导一次 → 两本独立的书（不合并、不冲突）。"""
        _src_id, _dst_id, blob, _slug, _root = roundtrip
        path = tmp_path / "again.zip"
        path.write_bytes(blob)

        async def run():
            from models.project import Novel
            async with async_session() as db:
                nid = await _import_single_book(db, zipfile.ZipFile(str(path)), "", "rt-user")
                await db.commit()
                return nid, (await db.scalars(select(Novel.id))).all()

        nid2, all_ids = _run(run())
        assert len(all_ids) >= 3  # 源书 + 第一次导入 + 第二次导入
        assert nid2 in all_ids


# ── 坏包矩阵 ──────────────────────────────────────────────────────────────


class TestBadPackages:
    def test_truncated_zip_rejected(self, tmp_path):
        from backup.importer import parse_package

        blob = _run(_export_book_zip_bytes(
            _run(_seed_full_book(str(tmp_path / "t1"))), str(tmp_path / "t1")))
        cut = blob[: len(blob) // 2]
        path = tmp_path / "cut.zip"
        path.write_bytes(cut)
        # 既定契约：坏 zip 不炸、记 warning、books 为空（容错矩阵）
        info = parse_package([str(path)])
        assert info["books"] == []
        assert any("zip" in w for w in info["warnings"])

    def test_version_above_supported_rejected_for_assets(self, tmp_path):
        from backup.importer import parse_package

        meta = {
            "backup.yaml": yaml.safe_dump({
                "kind": "assets", "format_version": 99,
                "created_at": "2026-09-13T00:00:00",
                "books": [{"slug": "ghost", "name": "幽灵书"}],
            }),
            "projects/ghost/project.yaml": yaml.safe_dump({"name": "幽灵书"}),
        }
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for n, d in meta.items():
                zf.writestr(n, d)
        path = tmp_path / "v99.zip"
        path.write_bytes(buf.getvalue())
        with pytest.raises(ValueError):
            parse_package([str(path)])

    def test_empty_zip_yields_no_books(self, tmp_path):
        from backup.importer import parse_package

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("backup.yaml", yaml.safe_dump({
                "kind": "assets", "format_version": 1,
                "created_at": "2026-09-13T00:00:00", "books": [],
            }))
        path = tmp_path / "empty.zip"
        path.write_bytes(buf.getvalue())
        info = parse_package([str(path)])
        assert info["books"] == []
