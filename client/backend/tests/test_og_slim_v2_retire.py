"""c-og-slim-v2 存储退役专项：删键不报错、不复活，旧包/旧快照可读。

四块：
- 备份包格式升 v5（删键规则的登记点）；
- 退役键写入被忽略（保存不报错、装配不输出）；
- 旧章快照恢复：退役键被忽略，正文与留守字段/子表不变；
- 旧包导入：退役键按忽略处理并在报告里给出可核对的处数。
"""

import asyncio
import json
import os
import tempfile
import zipfile

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
os.environ.setdefault("DATA_ROOT", tempfile.mkdtemp(prefix="test_og_slim_"))

from backup.format import FORMAT_VERSION  # noqa: E402
from chapters.store import load_chapter, save_chapter  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from models import Novel  # noqa: E402
from models.chapter import Chapter, ChapterMicroPayoff, ChapterVersion  # noqa: E402
from models.volume import Volume  # noqa: E402

RETIRED_PAYLOAD = {
    # 11 格对应键 + 隐藏字段（全量喂一遍）
    "outline": {
        "summary": "她夜探库房调包账册",
        "characters": ["林晚"],
        "key_points": ["[造悬念]匿名信被尾随"],
        "location": "库房",
        "time": "深夜",
        "narrative_pov": "第三人称限知",
        "perspective_guidance": "贴主角写",
    },
    "memo": {
        "reader_expectation": {"strategy": "顺推", "detail": "压悬念"},
        "payoff_plan": {
            "must_resolve": ["账本去向"],
            "must_hold": ["幕后主使"],
            "partial_advance": ["身世线索+1"],
        },
        "required_changes": ["账册被调包"],
    },
    "emotional_design": {
        "primary_mood": "紧张",
        "mood_progression": "松→紧",
        "intensity_peak": "对峙",
        "intensity_level": 7,
        "emotional_hook": "脚步声",
    },
    "segments": [{"summary": "潜入", "target_words": 800}],
    "scene_cards": [{"scene_name": "库房", "weight": "high", "focus": "核心冲突"}],
    "chapter_acts": ["她翻墙进库房"],
    "word_target": 2000,
    "ladder_exit": "假账册入箱",
}


def _run(coro):
    return asyncio.run(coro)


async def _new_book(name: str) -> Novel:
    root = os.path.join(os.environ["DATA_ROOT"], name)
    os.makedirs(os.path.join(root, "volumes"), exist_ok=True)
    os.makedirs(os.path.join(root, "chapters"), exist_ok=True)
    async with async_session() as s:
        proj = Novel(
            user_id="ogslim", name=name, slug=name, root_path=root,
            source="manual", current_phase="write",
        )
        s.add(proj)
        await s.flush()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        s.add(vol)
        await s.flush()
        row = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref="vol-1-ch-1", title="第一章", status="outline",
        )
        s.add(row)
        await s.commit()
        return proj


@pytest.fixture(scope="module", autouse=True)
def _tables():
    async def _create():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    _run(_create())


def test_backup_format_bumped_to_v5():
    """删键 = 升版（backup/format.py 规则）；v4 及更早包走忽略读窗。"""
    assert FORMAT_VERSION == 6


def test_retired_keys_ignored_on_save_and_assemble():
    """写入退役键：不报错、不落库、装配不输出；留守字段照常往返。"""

    async def _run_case():
        proj = await _new_book("ogslim_save")
        await save_chapter(proj.root_path, "vol-1-ch-1", RETIRED_PAYLOAD)
        data = await load_chapter(proj.root_path, "vol-1-ch-1")

        assert data["outline"]["summary"] == "她夜探库房调包账册"
        assert data["outline"]["characters"] == ["林晚"]
        for dead in ("key_points", "location", "time", "narrative_pov", "perspective_guidance"):
            assert dead not in data["outline"]
        assert "reader_expectation" not in data["memo"]
        assert data["memo"]["payoff_plan"]["must_resolve"] == ["账本去向"]
        assert "partial_advance" not in data["memo"]["payoff_plan"]
        assert data["emotional_design"] == {"primary_mood": "紧张"}
        for dead in ("segments", "scene_cards", "chapter_acts"):
            assert dead not in data
        assert data["word_target"] == 2000

    _run(_run_case())


def test_micro_payoff_location_ignored():
    """读者获得位置档退役：写入被忽略、装配不输出。"""

    async def _run_case():
        proj = await _new_book("ogslim_payoff")
        await save_chapter(
            proj.root_path,
            "vol-1-ch-1",
            {"micro_payoffs": [{"kind": "clue", "description": "半块玉佩", "location": "中段"}]},
        )
        data = await load_chapter(proj.root_path, "vol-1-ch-1")
        assert data["micro_payoffs"] == [{"kind": "clue", "description": "半块玉佩"}]

    _run(_run_case())


def test_old_snapshot_restore_ignores_retired_keys():
    """旧快照（含退役键）恢复：正文与留守字段/子表不变，不因缺键清空。"""

    async def _run_case():
        proj = await _new_book("ogslim_versions")
        await save_chapter(proj.root_path, "vol-1-ch-1", dict(RETIRED_PAYLOAD, prose="正文第一版。"))
        # 再造一份「旧快照」：形状＝历史 {prose, outline, status}，outline 带退役键
        old_snapshot = {
            "prose": "正文第一版。",
            "status": "outline",
            "outline": {
                "summary": "旧概要",
                "key_points": ["[过渡]收摊打烊"],
                "location": "旧地点",
            },
        }
        async with async_session() as s:
            from sqlalchemy import select

            row = (
                await s.scalars(
                    select(Chapter).where(Chapter.project_id == proj.id)
                )
            ).one()
            s.add(ChapterVersion(chapter_id=row.id, version=1, snapshot=json.dumps(old_snapshot, ensure_ascii=False)))
            await s.commit()

        from chapters.versions import restore_version

        # 直调路由函数体（绕 Depends，与 TestClient 路径同一实现）
        async with async_session() as db:
            out = await restore_version(
                project_id=proj.id,
                chapter_ref="vol-1-ch-1",
                version_id="v1",
                user={"id": "ogslim"},
                db=db,
            )
        assert out["ok"] is True
        data = await load_chapter(proj.root_path, "vol-1-ch-1")
        assert data["outline"]["summary"] == "旧概要"  # 快照覆盖
        assert "key_points" not in data["outline"] and "location" not in data["outline"]
        # 留守子表不被快照缺键清空（微弧线/伏笔项等来自当前行）
        assert data["memo"]["payoff_plan"]["must_resolve"] == ["账本去向"]
        assert data["prose"] == "正文第一版。"

    _run(_run_case())


def test_old_package_import_ignores_retired_keys_and_reports():
    """v4 包导入：退役键忽略、不报错，报告给出「忽略 N 处」。"""

    async def _run_case():
        import io

        import yaml
        from sqlalchemy import select

        from backup.export import dump_book_into
        from backup.importer import persist_package

        # 1) 真导出一本书（单书包形态，prefix=""）
        proj = await _new_book("ogslim_pack_src")
        await save_chapter(proj.root_path, "vol-1-ch-1", {"outline": {"summary": "原样概要"}})
        buf = io.BytesIO()
        async with async_session() as db:
            src = await db.get(Novel, proj.id)
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                await dump_book_into(zf, db, src, prefix="")

        # 2) 打补丁：章 yaml 注入退役键；project.yaml 标 v4（模拟旧包）
        patched = io.BytesIO()
        with zipfile.ZipFile(buf) as zin, zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "chapters/vol-1-ch-1.yaml":
                    payload = dict(yaml.safe_load(data))
                    payload.update({
                        "segments": [{"summary": "潜入"}],
                        "scene_cards": [{"scene_name": "库房"}],
                        "chapter_acts": ["她翻墙进库房"],
                    })
                    payload["outline"] = {
                        **payload.get("outline", {}),
                        "key_points": ["[造悬念]匿名信"],
                        "location": "库房",
                    }
                    payload.setdefault("memo", {})
                    payload["memo"] = {
                        **payload["memo"],
                        "reader_expectation": {"strategy": "顺推"},
                        "payoff_plan": {"must_resolve": ["账本去向"], "partial_advance": ["身世+1"]},
                    }
                    data = yaml.safe_dump(payload, allow_unicode=True).encode("utf-8")
                elif info.filename == "project.yaml":
                    payload = dict(yaml.safe_load(data))
                    payload["format_version"] = 4
                    data = yaml.safe_dump(payload, allow_unicode=True).encode("utf-8")
                zout.writestr(info, data)

        path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        path.write(patched.getvalue())
        path.close()

        # 3) 导入：忽略 + 计数告警
        async with async_session() as db:
            info = await persist_package(db, "ogslim_importer", [path.name], include_config=False)
        warnings = info.get("warnings", [])
        assert any("已退役" in w for w in warnings), (warnings, info)

        # 4) 忽略语义：留存字段照常落库，退役键不复活
        async with async_session() as db:
            novel = (
                await db.scalars(select(Novel).where(Novel.user_id == "ogslim_importer"))
            ).first()
            assert novel is not None
            row = (
                await db.scalars(select(Chapter).where(Chapter.project_id == novel.id))
            ).first()
            assert row.summary == "原样概要"
            assert row.challenge is None and row.plot_stage is None
            micros = (
                await db.scalars(
                    select(ChapterMicroPayoff).where(ChapterMicroPayoff.chapter_id == row.id)
                )
            ).all()
            assert micros == []

    _run(_run_case())


def test_migration_plan_skips_retired_columns():
    """旧库迁入走列交集：退役列落在 skipped_source_cols、不进搬运列清单。

    （迁入引擎第 3 步的计划段；c-og-slim-v2 删列不需要任何 DDL 步骤即由此保证。）
    """
    import sqlite3

    from migration.engine import build_plan

    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()
    conn = sqlite3.connect(db.name)
    # 最小旧库形状：chapters 带退役列（location/narrative_pov/chapter_acts/segments 等）
    conn.execute(
        """
        CREATE TABLE chapters (
            id VARCHAR(36) PRIMARY KEY,
            novel_id VARCHAR(36),
            title VARCHAR(200),
            summary VARCHAR(300),
            ladder_exit VARCHAR(300),
            word_target INTEGER,
            location VARCHAR(200),
            story_time VARCHAR(150),
            narrative_pov VARCHAR(50),
            perspective_guidance VARCHAR(300),
            chapter_acts TEXT,
            intensity_level INTEGER,
            mood_progression VARCHAR(300),
            expectation_strategy VARCHAR(50)
        )
        """
    )
    conn.commit()
    conn.close()

    plan = build_plan(db.name)
    entry = next(e for e in plan["tables"] if e["table"] == "chapters")
    retired = {
        "location", "story_time", "narrative_pov", "perspective_guidance",
        "chapter_acts", "intensity_level", "mood_progression", "expectation_strategy",
    }
    assert retired <= set(entry["skipped_source_cols"])
    assert not (retired & set(entry["columns"]))
    assert {"summary", "ladder_exit", "word_target"} <= set(entry["columns"])
