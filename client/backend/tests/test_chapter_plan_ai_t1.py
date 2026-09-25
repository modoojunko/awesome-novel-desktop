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

            # c-plot-split 新口径：plot_items 是缺键语义的例外（presence-gate，
            # 与 style_shadow 同款）——缺键/None 保持现值、显式 [] 清空；
            # 标量族缺键即清空的旧口径不变（上方钉住），差异在 c-plot-split 登记。
            _disassemble_scalars(row, {"plot_items": ["开场：荒庙接头", "结尾：她回头"]})
            await s.flush()
            _disassemble_scalars(row, {"summary": "还是只传 summary"})
            await s.flush()
            assert assemble_chapter(row)["plot_items"] == ["开场：荒庙接头", "结尾：她回头"]
            _disassemble_scalars(row, {"plot_items": []})
            await s.flush()
            assert assemble_chapter(row)["plot_items"] == []

    asyncio.run(_run())


# ── 排上（同事务）与重复提交幂等（tasks 4.1/4.2）────────────────────────
def test_adopt_writes_five_fields_in_one_transaction():
    """排上：建章＋五段同一事务写入；重复提交命中既有行（不冒 500）。"""
    import asyncio
    import os
    import tempfile

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.environ["DATA_ROOT"] = tempfile.mkdtemp()

    from db import Base, async_session, engine  # noqa: PLC0415
    from models import Novel  # noqa: PLC0415
    from models.volume import Volume  # noqa: PLC0415
    from chapters.service import create_chapter  # noqa: PLC0415
    from repositories import chapter_repo  # noqa: PLC0415

    async def _run():
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with async_session() as s:
            proj = Novel(user_id="adopt", name="T", slug="adopt-t", root_path=os.environ["DATA_ROOT"])
            s.add(proj)
            await s.flush()
            vol = Volume(project_id=proj.id, volume_no=1, title="第一卷", chapter_target=6)
            s.add(vol)
            await s.commit()

            # 排上：五段与建章同一事务
            out = await create_chapter(
                s, proj, "vol-1", "突击清查",
                {"plot": "清查队登船前她带着信标出逃", "challenge": "挨船搜舱，藏无可藏",
                 "ending": "信标暴露——全港都知道", "acts": ["清查队：登船搜舱", "沉舟：跳帮出逃"],
                 "stage": "重要转折"},
            )
            assert out["ref"] == "vol-1-ch-1"
            # 直读列（同一事务已落库；assemble 需预载关系，这里不必要）
            from sqlalchemy import select as _sel  # noqa: PLC0415
            from models.chapter import Chapter as _C  # noqa: PLC0415

            row = (
                await s.execute(
                    _sel(_C).where(_C.project_id == proj.id, _C.ref == "vol-1-ch-1")
                )
            ).scalar_one()
            assert row.summary.startswith("清查队登船前")
            assert row.challenge == "挨船搜舱，藏无可藏"
            assert row.ladder_exit.startswith("信标暴露")
            assert row.chapter_acts == "清查队：登船搜舱\n沉舟：跳帮出逃"
            assert row.plot_stage == "重要转折"

            # ① 同 client_token 重放（双击/超时重发）→ 返回首次建出的章，不再建
            tok = "tok-abc-123"
            out_a = await create_chapter(s, proj, "vol-1", "第一章", client_token=tok)
            out_b = await create_chapter(s, proj, "vol-1", "第一章", client_token=tok)
            assert out_a["ref"] == out_b["ref"] == "vol-1-ch-2"
            assert out_b.get("idempotent") is True
            # ② 无 token 的裸重放＝作者真的想再排一章 → 正常续号（不是错误）
            out_c = await create_chapter(s, proj, "vol-1", "重复")
            assert out_c["ref"] == "vol-1-ch-3"

    asyncio.run(_run())


# ── stale 第二触发面（task 4.5）─────────────────────────────────────────
def test_exit_change_marks_next_chapter_stale():
    """上游章末落点实质变更 → 下一有正文章 stale；措辞微调不触发。"""
    import asyncio
    import os
    import tempfile

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    os.environ["DATA_ROOT"] = tempfile.mkdtemp()

    from db import Base, async_session, engine  # noqa: PLC0415
    from models import Novel  # noqa: PLC0415
    from models.chapter import Chapter  # noqa: PLC0415
    from models.volume import Volume  # noqa: PLC0415
    from chapters.store import _mark_next_stale_on_exit_change  # noqa: PLC0415

    async def _run():
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        async with async_session() as s:
            p = Novel(user_id="st", name="T", slug="st-t", root_path=os.environ["DATA_ROOT"])
            s.add(p)
            await s.flush()
            v = Volume(project_id=p.id, volume_no=1, title="V")
            s.add(v)
            await s.flush()
            up = Chapter(project_id=p.id, volume_id=v.id, chapter_no=1, ref="vol-1-ch-1",
                         title="上", status="outline", ladder_exit="旧落点")
            nxt = Chapter(project_id=p.id, volume_id=v.id, chapter_no=2, ref="vol-1-ch-2",
                          title="下", status="writing", has_prose=True)
            s.add_all([up, nxt])
            await s.flush()

            # 措辞微调（trim 后相同）→ 不置位
            await _mark_next_stale_on_exit_change(s, up, {"ladder_exit": "  旧落点  "}, "旧落点")
            assert nxt.stale is False
            # 实质变更 → 置位
            await _mark_next_stale_on_exit_change(s, up, {"ladder_exit": "新落点"}, "旧落点")
            assert nxt.stale is True

    asyncio.run(_run())
