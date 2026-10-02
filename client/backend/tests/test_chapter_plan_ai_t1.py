"""c-chapter-plan-ai T1：拆章字段的持久化与校验（tasks 2.1/2.2；c-og-slim-v2 收窄为两格）。

覆盖：
- 两格随章保存/读取往返（challenge/plot_stage 标量）
- plot_stage 六档闭集：越界 422（API 层先于写入）
- 整表回传不抹除：仅改主情绪保存后两格原样
- 「本章行动」已退役：写入被忽略、装配不输出
"""

import pytest


def test_validate_stage_closed_set():
    from fastapi import HTTPException

    from chapters.schemas import validate_chapter_fields

    validate_chapter_fields({"plot_stage": "矛盾升级"})
    validate_chapter_fields({"plot_stage": None})
    with pytest.raises(HTTPException) as e:
        validate_chapter_fields({"plot_stage": "高潮"})
    assert e.value.status_code == 422


def test_retired_acts_ignored_by_validator():
    """c-og-slim-v2：「本章行动」退役——旧客户端仍发该键时校验不报错、也不再落库。"""
    from chapters.schemas import validate_chapter_fields

    validate_chapter_fields({"chapter_acts": ["a", "b", "c", "d", "e"]})
    validate_chapter_fields({"acts": ["x" * 99]})


# ── ORM 往返（三列真落库；含装配/写回链路）─────────────────────────────
def test_two_columns_roundtrip_via_store():
    """两格经 store 装配写回往返：challenge/plot_stage 标量；
    未设置时装配结果等价于新增前（加键兼容）；chapter_acts 写入被忽略。"""
    import asyncio
    import os
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix="_cpa.db", delete=False)  # noqa: SIM115
    tmp.close()
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp.name}"
    os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_cpa_")

    from chapters.store import _disassemble_scalars, assemble_chapter  # noqa: PLC0415
    from db import Base, async_session, engine  # noqa: PLC0415
    from models import Novel  # noqa: PLC0415
    from models.chapter import Chapter  # noqa: PLC0415

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

            # 未设置 → 装配等价于新增前（不含两键）
            plain = assemble_chapter(row)
            assert "challenge" not in plain and "plot_stage" not in plain
            assert "chapter_acts" not in plain

            # 写入 → 装配回读（退役键 chapter_acts 被忽略）
            _disassemble_scalars(row, {
                "challenge": "旧档堆不对活人开放",
                "plot_stage": "矛盾升级",
                "chapter_acts": ["她：调档", "文书：记台账"],
            })
            await s.flush()
            got = assemble_chapter(row)
            assert got["challenge"] == "旧档堆不对活人开放"
            assert got["plot_stage"] == "矛盾升级"
            assert "chapter_acts" not in got

            # 整表回传（含两格）→ 两格原样保留（前端契约：章纲表单整表回传）
            _disassemble_scalars(row, {
                "summary": "一句话",
                "challenge": "旧档堆不对活人开放",
                "plot_stage": "矛盾升级",
            })
            await s.flush()
            kept = assemble_chapter(row)
            assert kept["challenge"] == "旧档堆不对活人开放"
            assert kept["plot_stage"] == "矛盾升级"

            # c-og-chapter-put-patch-gates（2026-09-28 演示栈事故后换契约）：缺键＝保持现值，
            # 部分键 PUT 不再抹掉未带字段（旧「缺键即清空、前端必须整表回传」口径已废）。
            _disassemble_scalars(row, {"summary": "只传 summary"})
            await s.flush()
            assert assemble_chapter(row)["challenge"] == "旧档堆不对活人开放"

            # plot_items 的 presence-gate（c-plot-split）不变，现与全字段族同款：
            # 缺键/None 保持现值、显式 [] 清空。
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
def test_adopt_writes_four_fields_in_one_transaction():
    """排上：建章＋四段同一事务写入；重复提交命中既有行（不冒 500）。"""
    import asyncio
    import os
    import tempfile

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name  # noqa: SIM115 — 只要路径，句柄即弃（delete=False 留盘给引擎接管）
    os.environ["DATA_ROOT"] = tempfile.mkdtemp()

    from chapters.service import create_chapter  # noqa: PLC0415
    from db import Base, async_session, engine  # noqa: PLC0415
    from models import Novel  # noqa: PLC0415
    from models.volume import Volume  # noqa: PLC0415

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

            # 排上：四段与建章同一事务（旧客户端的 acts 键被忽略）
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

    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + tempfile.NamedTemporaryFile(suffix=".db", delete=False).name  # noqa: SIM115 — 只要路径，句柄即弃（delete=False 留盘给引擎接管）
    os.environ["DATA_ROOT"] = tempfile.mkdtemp()

    from chapters.store import _mark_next_stale_on_exit_change  # noqa: PLC0415
    from db import Base, async_session, engine  # noqa: PLC0415
    from models import Novel  # noqa: PLC0415
    from models.chapter import Chapter  # noqa: PLC0415
    from models.volume import Volume  # noqa: PLC0415

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
