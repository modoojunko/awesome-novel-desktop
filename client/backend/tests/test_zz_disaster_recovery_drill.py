"""删库救回演练（archive-reconcile tasks 1.3/4.3 硬门禁；迁移 PR 验收项）。

场景：本机库文件损毁（等价：全表丢失但 schema 重建）→ 应用以空库启动 →
用导出包完整救回资产。断言随包字段（出场引用 state_change、关系来源章
origin_chapter 的 ref→id 重绑、伏笔章引用、归档/提示词原文）全部恢复，
且运行态待办（chapter_reconcile）不随包、界外为零。

**执行顺序约束**：本测试 drop_all 清全库，文件名以 test_zz_ 前缀保证
pytest 字母序最后执行（同会话其它测试文件先跑完）。
"""

import asyncio
import io
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import select

from db import Base, async_session, engine

_LOOP = asyncio.new_event_loop()


def _run(coro):
    return _LOOP.run_until_complete(coro)


async def _seed(tmp_root: str) -> str:
    """书 + 2 章（第 1 章归档）＋出场引用 state_change＋来源章关系＋伏笔＋
    归档原文＋提示词＋一条收尾提案（界外，验不随包）。"""
    from filesystem.storage import get_storage
    from models.archive import Archive, ChapterPrompt
    from models.chapter import Chapter, ChapterCharacter, ChapterContent
    from models.character import Character, CharacterRelation
    from models.project import Novel
    from models.reconcile import ChapterReconcile
    from models.user import User
    from models.volume import Volume
    from settings.hooks_service import create_hook

    uid = f"drill-{uuid.uuid4().hex[:8]}"
    slug = f"drill-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="演练员", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="演练书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual",
            current_phase="write",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()

        ch1 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref="vol-1-ch-1", title="第1章 试手", status="archived",
            word_count=12, has_prose=True,
        )
        ch2 = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=2,
            ref="vol-1-ch-2", title="第2章", status="writing",
            word_count=8, has_prose=True,
        )
        session.add_all([ch1, ch2])
        await session.flush()
        session.add(ChapterContent(chapter_id=ch1.id, prose="第1章正文：残页上的火痕。"))
        session.add(ChapterContent(chapter_id=ch2.id, prose="第2章正文。"))
        # 随包字段 ①：出场引用状态变化
        session.add(ChapterCharacter(
            chapter_id=ch1.id, sort_order=1, character_name="林拾",
            state_change="从怀疑到确信残页是真的",
        ))
        # 随包字段 ②：关系来源章（origin_chapter_id + ch_ref 双写）
        c1 = Character(novel_id=proj.id, seq=1, name="林拾")
        c2 = Character(novel_id=proj.id, seq=2, name="老周")
        session.add_all([c1, c2])
        await session.flush()
        session.add(CharacterRelation(
            novel_id=proj.id, owner_id=c1.id, other_id=c2.id,
            rel_type="师徒", stance="信任", note="柴房夜谈后",
            ch_ref="vol-1-ch-1", origin_chapter_id=ch1.id,
        ))
        session.add(Archive(
            chapter_id=ch1.id, title="第1章 试手", summary="残页登场",
            content="归档原文：残页上的火痕。",
        ))
        session.add(ChapterPrompt(
            chapter_id=ch1.id, name="write", content="# 整章任务\n提到残页。",
        ))
        # 界外：运行态待办不随包
        session.add(ChapterReconcile(
            novel_id=proj.id, chapter_id=ch1.id, kind="set_changes",
            status="pending", payload='{"items":[{"key":"残页","value":"火痕"}]}',
        ))
        await session.commit()
        proj_id = proj.id

    # 伏笔（真实服务取号）：埋于第 1 章
    async with async_session() as session:
        ch1 = (await session.scalars(
            select(Chapter).where(Chapter.ref == "vol-1-ch-1", Chapter.project_id == proj_id)
        )).one()
        await create_hook(session, proj_id, {
            "description": "残页火痕", "type": "clue", "priority": 1,
            "status": "active", "introduced_chapter_id": ch1.id,
        })

    await get_storage().write_yaml(
        str(Path(tmp_root) / slug), "story.yaml", {"synopsis": "残页牵出旧案。"}
    )
    return proj_id


class TestDisasterRecoveryDrill:
    def test_export_wipe_import_recovers_assets(self, tmp_path):
        from backup.export import dump_book_into
        from backup.importer import _import_single_book
        from models.archive import Archive, ChapterPrompt
        from models.chapter import Chapter, ChapterCharacter
        from models.character import CharacterRelation
        from models.hook import NovelHook
        from models.project import Novel
        from models.reconcile import ChapterReconcile
        from volumes.service import list_volumes

        async def run_all():
            src_id = await _seed(str(tmp_path / "src"))

            # ① 导出（灾前救生包）
            async with async_session() as db:
                proj = await db.get(Novel, src_id)
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    await dump_book_into(zf, db, proj, prefix="")
            path = tmp_path / "rescue.zip"
            path.write_bytes(buf.getvalue())
            names = zipfile.ZipFile(str(path)).namelist()
            assert not any("reconcile" in n for n in names), "待办不随包"

            # ② 删库：全表清空 + schema 重建（等价库文件损毁后应用以空库启动）
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # ③ 救回
            async with async_session() as db:
                dst_id = await _import_single_book(
                    db, zipfile.ZipFile(str(path)), "", "drill-user"
                )
                await db.commit()

            # ④ 逐层断言
            async with async_session() as db:
                dst = await db.get(Novel, dst_id)
                assert dst is not None and dst.name == "演练书"

                chs = (await db.scalars(
                    select(Chapter).where(Chapter.project_id == dst_id)
                )).all()
                by_ref = {c.ref: c for c in chs}
                assert set(by_ref) == {"vol-1-ch-1", "vol-1-ch-2"}

                # 随包字段 ①：出场引用状态变化
                ch1 = by_ref["vol-1-ch-1"]
                cc = (await db.scalars(
                    select(ChapterCharacter).where(ChapterCharacter.chapter_id == ch1.id)
                )).one()
                assert cc.state_change == "从怀疑到确信残页是真的"

                # 随包字段 ②：关系来源章 ref→id 重绑（指向救回后的章 id）
                rel = (await db.scalars(
                    select(CharacterRelation).where(CharacterRelation.novel_id == dst_id)
                )).one()
                assert rel.origin_chapter_id == ch1.id
                assert rel.ch_ref == "vol-1-ch-1"

                # 伏笔章引用重绑
                hook = (await db.scalars(
                    select(NovelHook).where(NovelHook.novel_id == dst_id)
                )).one()
                assert hook.introduced_chapter_id == ch1.id

                # 归档与提示词原文
                arch = (await db.scalars(
                    select(Archive).where(Archive.chapter_id == ch1.id)
                )).one()
                assert arch.content == "归档原文：残页上的火痕。"
                prompt = (await db.scalars(
                    select(ChapterPrompt).where(ChapterPrompt.chapter_id == ch1.id)
                )).one()
                assert "残页" in prompt.content

                # 界外：收尾待办零行；卷章树主线口径正确
                rec = (await db.scalars(
                    select(ChapterReconcile).where(ChapterReconcile.novel_id == dst_id)
                )).all()
                assert rec == []
                vols = await list_volumes(db, dst)
                assert [c["ref"] for v in vols for c in v["chapters"]] == [
                    "vol-1-ch-1", "vol-1-ch-2",
                ]

        _run(run_all())
