"""归档收尾提案（archive-reconcile）后端行为测试。

覆盖：模型级联与枚举／未决覆盖与已决留痕／五类采纳写回（世界观/关系/伏笔）
＋lore 分支／失败保留 payload／端点语义（进度聚合、409 族、重试）／
未确认提案不进写章提示词。
"""

import asyncio
import json
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import Chapter, ChapterCharacter, ChapterContent
from models.character import Character, CharacterRelation
from models.hook import NovelHook
from models.project import Novel
from models.reconcile import ChapterReconcile
from models.user import User
from models.volume import Volume


async def _seed() -> tuple[str, str, str]:
    """书 + 一章（有正文/出场角色林晚、沉舟）+ 两张角色卡。返回 (root, nid, ch_id)。"""
    root = tempfile.mkdtemp(prefix="test_reconcile_")
    slug = f"rc-{os.path.basename(root)}"
    uid = f"rc-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{slug}@test.local", password_hash="x",
            display_name="收尾测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="收尾书", slug=slug, root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref="vol-1-ch-1", title="第1章", status="archived",
            word_count=20, has_prose=True,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch.id, prose="第1章正文：临江渡口的风很大。"))
        session.add(ChapterCharacter(chapter_id=ch.id, sort_order=1, character_name="林晚"))
        session.add(Character(novel_id=proj.id, seq=1, name="林晚"))
        session.add(Character(novel_id=proj.id, seq=2, name="老聋"))
        await session.commit()
        _UIDS[proj.id] = uid
        return root, proj.id, ch.id


_UIDS: dict[str, str] = {}


def _client(nid: str):
    c = TestClient(app)
    c.__enter__()
    uid = _UIDS[nid]
    app.dependency_overrides[get_current_user] = lambda: {"id": uid}
    return c


def _add_row(nid: str, ch_id: str, kind: str, payload: dict, status: str = "pending") -> str:
    async def _run():
        async with async_session() as s:
            row = ChapterReconcile(
                novel_id=nid, chapter_id=ch_id, kind=kind, status=status,
                payload=json.dumps(payload, ensure_ascii=False),
            )
            s.add(row)
            await s.commit()
            return row.id

    return asyncio.run(_run())


def _get_row(row_id: str) -> ChapterReconcile | None:
    async def _run():
        async with async_session() as s:
            return await s.get(ChapterReconcile, row_id)

    return asyncio.run(_run())


def _post(nid: str, path: str):
    c = _client(nid)
    try:
        return c.post(f"/api/novels/{nid}/chapters/vol-1-ch-1/reconcile{path}")
    finally:
        app.dependency_overrides.clear()


def _get(nid: str, path: str = ""):
    c = _client(nid)
    try:
        return c.get(f"/api/novels/{nid}/chapters/vol-1-ch-1/reconcile{path}")
    finally:
        app.dependency_overrides.clear()


class TestModelAndUpsert:
    def test_cascade_delete_removes_rows(self):
        _root, nid, ch_id = asyncio.run(_seed())
        row_id = _add_row(nid, ch_id, "set_changes", {"items": []})

        async def _delete_chapter():
            async with async_session() as s:
                ch = await s.get(Chapter, ch_id)
                await s.delete(ch)
                await s.commit()
            async with async_session() as s:
                return await s.get(ChapterReconcile, row_id)

        assert asyncio.run(_delete_chapter()) is None

    def test_pending_overwritten_decided_kept(self):
        from archive.reconcile import _upsert_pending

        _root, nid, ch_id = asyncio.run(_seed())
        first = _add_row(nid, ch_id, "set_changes", {"items": [{"key": "旧", "value": "1"}]})

        async def _upsert(payload):
            async with async_session() as s:
                rid = await _upsert_pending(s, ch_id, nid, "set_changes", payload)
                await s.commit()
                return rid

        # 未决 → 覆盖同一行、payload 替换
        same = asyncio.run(_upsert({"items": [{"key": "新", "value": "2"}]}))
        assert same == first
        r = _get_row(first)
        assert json.loads(r.payload)["items"][0]["key"] == "新"

        # 标已决后再 upsert → 新建 pending（已决行留痕）
        async def _accept():
            async with async_session() as s:
                row = await s.get(ChapterReconcile, first)
                row.status = "accepted"
                await s.commit()

        asyncio.run(_accept())
        second = asyncio.run(_upsert({"items": [{"key": "又新", "value": "3"}]}))
        assert second != first
        assert _get_row(first).status == "accepted"
        assert _get_row(second).status == "pending"


class TestAcceptWriteBack:
    def _accept(self, nid: str, row_id: str):
        from archive.reconcile import apply_accept

        async def _run():
            from models.reconcile import ChapterReconcile as R

            async with async_session() as s:
                row = await s.get(R, row_id)
                await apply_accept(s, row)
                await s.commit()

        asyncio.run(_run())

    def test_set_changes_and_lore_write_world_with_origin(self):
        from filesystem.storage import get_storage

        root, nid, ch_id = asyncio.run(_seed())
        for kind in ("set_changes", "lore"):
            rid = _add_row(nid, ch_id, kind, {"items": [{"key": f"{kind}条目", "value": "值"}]})
            self._accept(nid, rid)
            assert _get_row(rid).status == "accepted"

        world = asyncio.run(
            get_storage().read_yaml(root, "settings/world-setting.yaml")
        ) or {}
        entries = {e.get("key"): e for e in (world.get("history") or []) + (world.get("extra") or [])}
        assert entries["set_changes条目"]["origin"] == "vol-1-ch-1"
        assert entries["lore条目"]["origin"] == "vol-1-ch-1"

    def test_relations_upsert_with_origin_chapter(self):
        _root, nid, ch_id = asyncio.run(_seed())
        rid = _add_row(nid, ch_id, "relations", {"items": [{
            "owner": "林晚", "other": "老聋", "rel_type": "同盟",
            "stance": "信任加深", "note": "共渡难关",
        }]})
        self._accept(nid, rid)

        async def _check():
            async with async_session() as s:
                rows = (
                    await s.scalars(
                        select(CharacterRelation).where(
                            CharacterRelation.novel_id == nid
                        )
                    )
                ).all()
                return rows

        rows = asyncio.run(_check())
        assert len(rows) == 1
        assert rows[0].origin_chapter_id == ch_id
        assert _get_row(rid).status == "accepted"

    def test_hooks_planted_and_resolved(self):
        _root, nid, ch_id = asyncio.run(_seed())

        async def _seed_hook():
            from settings.hooks_service import create_hook

            async with async_session() as s:
                await create_hook(s, nid, {
                    "description": "码头上的陌生船家",
                    "type": "mystery", "priority": 2, "status": "active",
                })

        asyncio.run(_seed_hook())
        rid = _add_row(nid, ch_id, "hooks", {
            "planted": [{"description": "渡口的雾", "evidence": "雾还没散尽"}],
            "resolved": [{"description": "陌生船家", "evidence": "船家解开缆绳"}],
        })
        self._accept(nid, rid)

        async def _hooks():
            async with async_session() as s:
                return (await s.scalars(
                    select(NovelHook).where(NovelHook.novel_id == nid)
                )).all()

        hooks = asyncio.run(_hooks())
        planted = next(h for h in hooks if "渡口的雾" in h.description)
        assert planted.status == "active"
        old = next(h for h in hooks if "船家" in h.description)
        assert old.status == "resolved"
        assert _get_row(rid).status == "accepted"


class TestEndpoints:
    def test_list_progress_and_status_transitions(self):
        _root, nid, ch_id = asyncio.run(_seed())
        r1 = _add_row(nid, ch_id, "set_changes", {"items": []})
        r2 = _add_row(nid, ch_id, "relations", {"items": []}, status="failed")
        r3 = _add_row(nid, ch_id, "hooks", {}, status="rejected")

        got = _get(nid).json()
        assert got["progress"] == {"pending": 1, "failed": 1, "accepted": 0, "rejected": 1}
        assert {r["id"] for r in got["rows"]} == {r1, r2, r3}

        # 已决行再操作 → 409
        assert _post(nid, f"/{r3}/accept").status_code == 409
        assert _post(nid, f"/{r3}/reject").status_code == 409
        # 非失败行重试 → 409
        assert _post(nid, f"/{r1}/retry").status_code == 409

    def test_accept_failure_keeps_payload_and_marks_failed(self):
        _root, nid, ch_id = asyncio.run(_seed())
        rid = _add_row(nid, ch_id, "bogus_kind", {"items": [{"key": "x"}]})
        r = _post(nid, f"/{rid}/accept")
        assert r.status_code == 502, r.text
        row = _get_row(rid)
        assert row.status == "failed"
        assert "bogus_kind" in (row.error or "")
        assert json.loads(row.payload)["items"] == [{"key": "x"}]  # payload 保留供重试

    def test_retry_failed_starts_job(self, monkeypatch):
        _root, nid, ch_id = asyncio.run(_seed())
        rid = _add_row(nid, ch_id, "set_changes", {"items": []}, status="failed")
        started: list = []

        def _fake_start(novel_id, root_path, chapter_ref, chapter_id):
            started.append((novel_id, chapter_ref, chapter_id))
            return {"state": "running"}

        monkeypatch.setattr("archive.reconcile.start_reconcile_job", _fake_start)
        r = _post(nid, f"/{rid}/retry")
        assert r.status_code == 200, r.text
        assert r.json()["started"] is True
        assert started and started[0][1] == "vol-1-ch-1"

    def test_reject_marks_rejected(self):
        _root, nid, ch_id = asyncio.run(_seed())
        rid = _add_row(nid, ch_id, "set_changes", {"items": []})
        assert _post(nid, f"/{rid}/reject").status_code == 200
        assert _get_row(rid).status == "rejected"


class TestNotInjected:
    def test_pending_proposal_absent_from_writing_prompt(self):
        """未确认提案不参与后续章节的提示词（提案只在 chapter_reconcile，不在对象上）。"""
        from write.chapter_writer import build_chapter_context

        root, nid, ch_id = asyncio.run(_seed())
        marker = "幽灵提案记号XYZ"
        _add_row(nid, ch_id, "set_changes", {"items": [{"key": marker, "value": marker}]})

        async def _build():
            return await build_chapter_context(
                root, "vol-1-ch-1", "收尾书", novel_id=nid
            )

        ctx = asyncio.run(_build())
        assert marker not in ctx.to_prompt()
        assert marker not in ctx.material_markdown()
