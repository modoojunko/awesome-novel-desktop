"""c-chapter-plan-ai T1：拆章三列的持久化与校验（tasks 2.1/2.2）。

覆盖：
- 三列随章保存/读取往返（challenge/plot_stage 标量；chapter_acts 列表同形）
- plot_stage 六档闭集：越界 422（API 层先于写入）
- chapter_acts 归一化：逐行 ≤60、上限 4 行、去空白丢空行
- 整表回传不抹除：仅改主情绪保存后三列原样
"""

import pytest
from fastapi.testclient import TestClient

from chapters.store import _join_acts


def test_join_acts_normalizes():
    assert _join_acts(["  她：调档  ", "", "文书：记台账"]) == "她：调档\n文书：记台账"
    assert _join_acts("a\n\nb\nc\nd\ne") == "a\nb\nc\nd"          # 上限 4 行
    assert len(_join_acts(["x" * 80]).split("\n")[0]) == 60        # 单行截 60
    assert _join_acts(None) is None and _join_acts([]) is None


def test_validate_stage_closed_set():
    from fastapi import HTTPException
    from chapters.schemas import validate_chapter_fields

    validate_chapter_fields({"plot_stage": "矛盾升级"})
    validate_chapter_fields({"plot_stage": None})
    with pytest.raises(HTTPException) as e:
        validate_chapter_fields({"plot_stage": "高潮"})
    assert e.value.status_code == 422


def test_validate_acts_limits():
    from fastapi import HTTPException
    from chapters.schemas import validate_chapter_fields

    validate_chapter_fields({"chapter_acts": ["a", "b", "c", "d"]})
    with pytest.raises(HTTPException):
        validate_chapter_fields({"chapter_acts": ["a", "b", "c", "d", "e"]})
    with pytest.raises(HTTPException):
        validate_chapter_fields({"chapter_acts": ["x" * 61]})


# ── ORM 往返（三列真落库；含装配/写回链路）─────────────────────────────
def test_three_columns_roundtrip_via_store():
    """三列经 store 装配写回往返：challenge/plot_stage 标量、chapter_acts 列表同形；
    未设置时装配结果等价于新增前（加键兼容）。"""
    import asyncio
    import os
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix="_cpa.db", delete=False)  # noqa: SIM115
    tmp.close()
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp.name}"
    os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_cpa_")

    from db import Base, async_session, engine  # noqa: PLC0415
    from models import Novel  # noqa: PLC0415
    from models.chapter import Chapter  # noqa: PLC0415
    from chapters.store import _disassemble_scalars, assemble_chapter  # noqa: PLC0415

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session() as s:
            proj = Novel(user_id="cpa", name="T", slug="cpa-t", root_path=os.environ["DATA_ROOT"])
            s.add(proj)
            await s.flush()
            from models.volume import Volume  # noqa: PLC0415
            vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
            s.add(vol)
            await s.flush()
            row = Chapter(
                project_id=proj.id, volume_id=vol.id, chapter_no=1,
                ref="vol-1-ch-1", title="第一章", has_prose=False, status="outline",
            )
            s.add(row)
            await s.flush()
            # 重新取行（selectin 预载关系，避免在同步装配里触发 IO）
            from sqlalchemy import select as _select  # noqa: PLC0415
            row = (await s.execute(_select(Chapter).where(Chapter.id == row.id))).scalar_one()

            # 未设置 → 装配等价于新增前（不含三键）
            plain = assemble_chapter(row)
            assert "challenge" not in plain and "plot_stage" not in plain and "chapter_acts" not in plain

            # 写入 → 装配回读
            _disassemble_scalars(row, {
                "challenge": "旧档堆不对活人开放",
                "plot_stage": "矛盾升级",
                "chapter_acts": ["她：调档", "文书：记台账"],
            })
            await s.flush()
            got = assemble_chapter(row)
            assert got["challenge"] == "旧档堆不对活人开放"
            assert got["plot_stage"] == "矛盾升级"
            assert got["chapter_acts"] == ["她：调档", "文书：记台账"]

            # 整表回传（含三列）→ 三列原样保留（前端契约：章纲表单整表回传）
            _disassemble_scalars(row, {
                "summary": "一句话",
                "challenge": "旧档堆不对活人开放",
                "plot_stage": "矛盾升级",
                "chapter_acts": ["她：调档", "文书：记台账"],
            })
            await s.flush()
            kept = assemble_chapter(row)
            assert kept["challenge"] == "旧档堆不对活人开放"
            assert kept["plot_stage"] == "矛盾升级"
            assert kept["chapter_acts"] == ["她：调档", "文书：记台账"]

            # 既有语义文档化：缺键即清空（全标量族同款）——故前端必须整表回传，
            # 这条不是 bug 而是契约（chapter-data delta「表单整表回传」场景的依据）。
            _disassemble_scalars(row, {"summary": "只传 summary"})
            await s.flush()
            assert "challenge" not in assemble_chapter(row)

    asyncio.run(_run())
