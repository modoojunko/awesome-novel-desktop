"""重写旧稿支线章的导出/导入往返（chapter-rewrite 契约场景）。

- 旧稿章（内容寻址 ref `…-r{8hex}`）随包往返：ghost_of 与正文保留；
- 主线统计不变：卷章树/书级统计继续排除支线章（导入侧与源侧同口径）。
"""

import asyncio
import io
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import select

from backup.export import dump_book_into
from backup.importer import _import_single_book
from chapters.rewrite import rewrite_chapter
from db import async_session

_LOOP = asyncio.new_event_loop()


def _run(coro):
    return _LOOP.run_until_complete(coro)


async def _seed_with_ghost(tmp_root: str) -> tuple[str, str]:
    """种一本书（2 章有正文，第 1 章归档）→ 重写第 1 章产生一份旧稿快照。"""
    from models.chapter import Chapter, ChapterContent
    from models.project import Novel
    from models.user import User
    from models.volume import Volume

    uid = f"wr-{uuid.uuid4().hex[:8]}"
    slug = f"wr-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="重写往返员", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="重写往返书", slug=slug,
            root_path=str(Path(tmp_root) / slug), source="manual",
            current_phase="write",
        )
        session.add(proj)
        await session.flush()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        for no, status in ((1, "archived"), (2, "writing")):
            ch = Chapter(
                project_id=proj.id, volume_id=vol.id, chapter_no=no,
                ref=f"vol-1-ch-{no}", title=f"第{no}章", status=status,
                word_count=7, has_prose=True,
            )
            session.add(ch)
            await session.flush()
            session.add(ChapterContent(chapter_id=ch.id, prose=f"第{no}章的正文。"))
        await session.commit()
        proj_id = proj.id

    async with async_session() as session:
        proj = await session.get(Novel, proj_id)
        r = await rewrite_chapter(session, proj, "vol-1-ch-1")
    return proj_id, r["ghost_ref"]


class TestRewriteGhostRoundtrip:
    def test_ghost_survives_roundtrip_and_stats_exclude_it(self, tmp_path):
        async def run_all():
            from models.chapter import Chapter
            from models.project import Novel
            from volumes.service import list_ghosts, list_volumes

            src_id, ghost_ref = await _seed_with_ghost(str(tmp_path / "src"))

            # 源侧：导出
            async with async_session() as db:
                proj = await db.get(Novel, src_id)
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    await dump_book_into(zf, db, proj, prefix="")
            path = tmp_path / "book.zip"
            path.write_bytes(buf.getvalue())

            # 导入
            async with async_session() as db:
                dst_id = await _import_single_book(
                    db, zipfile.ZipFile(str(path)), "", "wr-user"
                )
                await db.commit()

            # 导入侧：旧稿章在、ghost_of 与正文保留
            async with async_session() as db:
                rows = (
                    await db.scalars(
                        select(Chapter).where(Chapter.project_id == dst_id)
                    )
                ).all()
                by_ref = {c.ref: c for c in rows}
                assert ghost_ref in by_ref, sorted(by_ref)
                g = by_ref[ghost_ref]
                assert g.ghost_of == "vol-1-ch-1"
                dst = await db.get(Novel, dst_id)

                # 主线统计不变：卷章树排除旧稿；ghosts 列表含之且标 rewrite
                vols = await list_volumes(db, dst)
                refs = [c["ref"] for v in vols for c in v["chapters"]]
                assert refs == ["vol-1-ch-1", "vol-1-ch-2"]
                assert vols[0]["chapter_count"] == 2
                ghosts = await list_ghosts(db, dst)
                hit = next(x for x in ghosts if x["ref"] == ghost_ref)
                assert hit["origin"] == "rewrite"
                assert hit["ghost_of"] == "vol-1-ch-1"

            # 源侧不受导出/导入影响
            async with async_session() as db:
                src = await db.get(Novel, src_id)
                vols = await list_volumes(db, src)
                assert [c["ref"] for v in vols for c in v["chapters"]] == [
                    "vol-1-ch-1", "vol-1-ch-2",
                ]
                ghosts = await list_ghosts(db, src)
                assert any(x["ref"] == ghost_ref for x in ghosts)

        _run(run_all())
