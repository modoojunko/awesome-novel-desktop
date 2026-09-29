"""归档收尾提案（archive-reconcile）后端行为测试。

c-chapter-dossier 后收尾通道收缩为两类（伏笔登记/世界要素）——
set_changes/relations/char_states 已迁章档（archive/dossier.py）。
覆盖：模型级联与枚举／未决覆盖与已决留痕／两类采纳写回＋退役 kind 拒收／
失败保留 payload／端点语义（进度聚合、409 族、重试、退役 kind 400）／
存量 pending 迁移／未确认提案不进写章提示词。
"""

import asyncio
import json
import os
import tempfile

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import Chapter, ChapterCharacter, ChapterContent
from models.character import Character
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


def _client(nid: str, *, ai: bool = False):
    c = TestClient(app)
    c.__enter__()
    uid = _UIDS[nid]
    app.dependency_overrides[get_current_user] = lambda: {"id": uid}
    if ai:
        from auth_local.deps import (
            require_ai_access as _raa,
        )
        from auth_local.deps import (
            require_novel_model as _rnm,
        )

        app.dependency_overrides[_raa] = lambda: True
        app.dependency_overrides[_rnm] = lambda: True
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
        row_id = _add_row(nid, ch_id, "lore", {"items": []})

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
        first = _add_row(nid, ch_id, "lore", {"items": [{"key": "旧", "value": "1"}]})

        async def _upsert(payload):
            async with async_session() as s:
                rid = await _upsert_pending(s, ch_id, nid, "lore", payload)
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

    def test_lore_write_world_with_origin(self):
        from filesystem.storage import get_storage

        root, nid, ch_id = asyncio.run(_seed())
        rid = _add_row(nid, ch_id, "lore", {"items": [{"key": "lore条目", "value": "值"}]})
        self._accept(nid, rid)
        assert _get_row(rid).status == "accepted"

        world = asyncio.run(
            get_storage().read_yaml(root, "settings/world-setting.yaml")
        ) or {}
        entries = {e.get("key"): e for e in (world.get("history") or []) + (world.get("extra") or [])}
        assert entries["lore条目"]["origin"] == "vol-1-ch-1"

    def test_retired_kinds_rejected_by_accept(self):
        """退役 kind（已迁章档）到达采纳 → ValueError（上游白名单已拦，双保险）。"""
        from archive.reconcile import apply_accept

        _root, nid, ch_id = asyncio.run(_seed())
        for kind in ("set_changes", "relations", "char_states"):
            rid = _add_row(nid, ch_id, kind, {"items": []})

            async def _run(row_id=rid):
                async with async_session() as s:
                    row = await s.get(ChapterReconcile, row_id)
                    await apply_accept(s, row)

            try:
                asyncio.run(_run())
                raise AssertionError(f"{kind} 应被拒收")
            except ValueError as e:
                assert kind in str(e)

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

    def test_hooks_accept_dedupes_normalized_duplicates(self):
        """采纳幂等（真机实锤 09-29）：描述归一化后与既有钩相同（含标点/空白变体
        与同 payload 内互重）→ 跳过建条，不堆积重复伏笔。"""
        _root, nid, ch_id = asyncio.run(_seed())

        async def _seed_hook():
            from settings.hooks_service import create_hook

            async with async_session() as s:
                await create_hook(s, nid, {
                    "description": "猎血短刃来历不明、威力异常，被教团记档待验",
                    "type": "mystery", "priority": 2, "status": "active",
                })

        asyncio.run(_seed_hook())
        rid = _add_row(nid, ch_id, "hooks", {
            "planted": [
                # 与既有钩仅差标点（归一化全等）→ 跳过；语义变体由台账注入在源头防
                {"description": "猎血短刃来历不明、威力异常——被教团记档待验！"},
                {"description": "渡口的雾，久聚不散"},
                {"description": "渡口的雾、久聚不散"},  # 同 payload 内标点变体
            ],
            "resolved": [],
        })
        self._accept(nid, rid)

        async def _hooks():
            async with async_session() as s:
                return (await s.scalars(
                    select(NovelHook).where(NovelHook.novel_id == nid)
                )).all()

        hooks = asyncio.run(_hooks())
        assert _get_row(rid).status == "accepted"
        # 短刃变体被跳过；雾的两条变体只建一条
        assert sum(1 for h in hooks if "短刃" in h.description) == 1
        assert sum(1 for h in hooks if "雾" in h.description) == 1


class TestHooksPrompt:
    def test_prompt_carries_ledger_and_caps(self):
        """hooks 提示词带真伏笔判据＋条数上限＋现有台账排重（lore 同构防重）。"""
        from archive.reconcile import _collect_prompts

        prompts = dict(
            _collect_prompts(
                "vol-1-ch-1", {}, "正文", [],
                world_now="", roster="",
                hooks_now="本书已有伏笔台账（相同或高度相似的不要重复登记）：\n- 旧钩",
            )
        )
        p = prompts["hooks"]
        assert "埋下或收束了哪些伏笔" in p  # e2e 桩依赖此短语（勿改名）
        assert "planted 最多 3 条" in p and "resolved 最多 3 条" in p
        assert "氛围描写、场景细节" in p
        assert "旧钩" in p

    def test_prompt_without_ledger_has_no_block(self):
        from archive.reconcile import _collect_prompts

        p = dict(_collect_prompts("vol-1-ch-1", {}, "正文", []))["hooks"]
        assert "已有伏笔台账" not in p
        assert "planted 最多 3 条" in p


class TestEndpoints:
    def test_list_progress_and_status_transitions(self):
        _root, nid, ch_id = asyncio.run(_seed())
        r1 = _add_row(nid, ch_id, "lore", {"items": []})
        r2 = _add_row(nid, ch_id, "hooks", {"items": []}, status="failed")
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
        rid = _add_row(nid, ch_id, "lore", {"items": []}, status="failed")
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
        rid = _add_row(nid, ch_id, "hooks", {"items": []})
        assert _post(nid, f"/{rid}/reject").status_code == 200
        assert _get_row(rid).status == "rejected"


class TestRunNow:
    def test_run_kind_filtered_job_started(self, monkeypatch):
        _root, nid, _ch = asyncio.run(_seed())
        captured: list = []

        def _fake_start(novel_id, root_path, chapter_ref, chapter_id, kinds=None):
            captured.append(kinds)
            return {"state": "running"}

        monkeypatch.setattr("archive.reconcile.start_reconcile_job", _fake_start)
        c = _client(nid, ai=True)
        try:
            resp = c.post(
                f"/api/novels/{nid}/chapters/vol-1-ch-1/reconcile/run",
                json={"kind": "hooks"},
            )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"ok": True, "started": True, "kind": "hooks"}
        assert captured == [["hooks"]]

    def test_run_retired_kind_400(self):
        """退役 kind（已迁章档）按非法 kind 拒收。"""
        _root, nid, _ch = asyncio.run(_seed())
        c = _client(nid, ai=True)
        try:
            for kind in ("set_changes", "relations", "char_states"):
                resp = c.post(
                    f"/api/novels/{nid}/chapters/vol-1-ch-1/reconcile/run",
                    json={"kind": kind},
                )
                assert resp.status_code == 400, kind
        finally:
            app.dependency_overrides.clear()

    def test_run_all_when_kind_absent(self, monkeypatch):
        _root, nid, _ch = asyncio.run(_seed())
        captured: list = []

        def _fake_start(novel_id, root_path, chapter_ref, chapter_id, kinds=None):
            captured.append(kinds)
            return {"state": "running"}

        monkeypatch.setattr("archive.reconcile.start_reconcile_job", _fake_start)
        c = _client(nid, ai=True)
        try:
            resp = c.post(f"/api/novels/{nid}/chapters/vol-1-ch-1/reconcile/run", json={})
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 200, resp.text
        assert captured == [None]

    def test_run_invalid_kind_400(self):
        _root, nid, _ch = asyncio.run(_seed())
        c = _client(nid, ai=True)
        try:
            resp = c.post(
                f"/api/novels/{nid}/chapters/vol-1-ch-1/reconcile/run",
                json={"kind": "bogus"},
            )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 400

    def test_run_free_tier_403(self):
        _root, nid, _ch = asyncio.run(_seed())
        from auth_local.deps import require_ai_access

        def _forbidden():
            raise HTTPException(403, detail={"reason": "member_required"})

        c = _client(nid)
        app.dependency_overrides[require_ai_access] = _forbidden
        try:
            resp = c.post(
                f"/api/novels/{nid}/chapters/vol-1-ch-1/reconcile/run", json={}
            )
        finally:
            app.dependency_overrides.clear()
        assert resp.status_code == 403


class TestNotInjected:
    def test_pending_proposal_absent_from_writing_prompt(self):
        """未确认提案不参与后续章节的提示词（提案只在 chapter_reconcile，不在对象上）。"""
        from write.chapter_writer import build_chapter_context

        root, nid, ch_id = asyncio.run(_seed())
        marker = "幽灵提案记号XYZ"
        _add_row(nid, ch_id, "hooks", {"planted": [{"description": marker}]})

        async def _build():
            return await build_chapter_context(
                root, "vol-1-ch-1", "收尾书", novel_id=nid
            )

        ctx = asyncio.run(_build())
        # 两层都不得泄漏未确认提案（c-write-prompt-layering：恒定层＋user 层）
        assert marker not in ctx.to_user_material()
        assert marker not in ctx.build_system_prompt()
        assert marker not in ctx.material_markdown()


class TestLegacyMigration:
    def test_pending_migrated_and_char_states_rejected(self):
        """存量迁移：set_changes/relations pending → 章档行；char_states → rejected。"""
        from archive.reconcile import migrate_legacy_pending

        _root, nid, ch_id = asyncio.run(_seed())
        _add_row(nid, ch_id, "set_changes", {"items": [
            {"key": "信标", "value": "三百年前留下", "set": "extra"},
        ]})
        _add_row(nid, ch_id, "relations", {"items": [
            {"owner": "林晚", "other": "老聋", "rel_type": "同盟",
             "stance": "信任加深", "note": "共渡难关"},
        ]})
        _add_row(nid, ch_id, "char_states", {"items": [
            {"name": "林晚", "state_change": "从犹豫到决意"},
        ]})
        _add_row(nid, ch_id, "hooks", {"planted": [{"description": "保留在旧通道"}]})

        got = asyncio.run(migrate_legacy_pending())
        assert got == {"migrated": 2, "char_states_rejected": 1}

        from models.chapter import (
            ChapterRelationChange,
            ChapterSettingChange,
        )

        async def _check():
            async with async_session() as s:
                ch = await s.get(Chapter, ch_id)
                settings = (await s.scalars(
                    select(ChapterSettingChange)
                    .where(ChapterSettingChange.chapter_id == ch_id)
                )).all()
                relations = (await s.scalars(
                    select(ChapterRelationChange)
                    .where(ChapterRelationChange.chapter_id == ch_id)
                )).all()
                recs = (await s.scalars(
                    select(ChapterReconcile).where(ChapterReconcile.chapter_id == ch_id)
                )).all()
                return ch, settings, relations, recs

        _ch, settings, relations, recs = asyncio.run(_check())
        assert len(settings) == 1 and settings[0].status == "pending"
        assert "信标" in settings[0].content and settings[0].area == "extra"
        assert len(relations) == 1 and relations[0].owner_name == "林晚"
        assert relations[0].change_note == "信任加深"
        # 旧通道只剩 hooks pending（未迁移）＋ char_states rejected 留痕
        by_kind = {r.kind: r for r in recs}
        assert set(by_kind) == {"hooks", "char_states"}
        assert by_kind["hooks"].status == "pending"
        assert by_kind["char_states"].status == "rejected"
        # 幂等：再跑一次无迁移量
        assert asyncio.run(migrate_legacy_pending()) == {
            "migrated": 0, "char_states_rejected": 0,
        }


class TestOutputBudgetAndTruncation:
    """真机实锤（09-28）：伏笔登记输出断在半句 evidence——600 输出预算对
    planted/resolved 各几条带证据句必截断。钉死 1600 预算＋截断诊断提示。"""

    def test_hooks_lore_call_with_1600_budget_and_truncation_hint(self, monkeypatch):
        _root, nid, ch_id = asyncio.run(_seed())
        captured: dict = {}

        class _Fake:
            async def chat(self, **kwargs):
                captured["max_tokens"] = kwargs.get("max_tokens")
                captured["prompts"] = captured.get("prompts", 0) + 1
                # 模拟被截断的 JSON：断在半句 evidence（无收尾 "}"）
                return (
                    '```json\n{ "planted": [ { "description": "血裔化进程", '
                    '"evidence": "他自己知道。今天比昨天'
                )

        async def _fake_client(novel_id):
            return _Fake()

        import ai_client

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_client)
        import archive.reconcile as rc

        asyncio.run(
            rc._run_async(nid, _root, "vol-1-ch-1", ch_id, kinds=["hooks", "lore"])
        )
        assert captured["max_tokens"] == 1600
        assert captured["prompts"] == 2  # hooks + lore 各一次

        rows = asyncio.run(_rows_of(ch_id))
        assert {r.kind for r in rows} == {"hooks", "lore"}
        for r in rows:
            assert r.status == "failed"
            assert "疑似被输出预算截断" in r.error
            assert "parse" in r.error


async def _rows_of(ch_id: str):
    async with async_session() as s:
        return (await s.scalars(
            select(ChapterReconcile).where(ChapterReconcile.chapter_id == ch_id)
        )).all()


class TestLoreRosterAndFailedCleanup:
    """① lore 注入角色名册（防已登记角色背景混进世界要素——真机实锤）；
    ② 重跑成功清同章同类旧失败行（防永久挂列表）。"""

    def test_lore_prompt_contains_roster_and_rule(self, monkeypatch):
        from archive.reconcile import _collect_prompts

        prompts = dict(
            _collect_prompts(
                "vol-1-ch-1", {}, "正文", ["林晚"], "世界设定现文",
                "【本书专名册】\n- 人物：林晚、老聋\n- 势力：守夜人",
            )
        )
        assert "【本书专名册】" in prompts["lore"]
        assert "不要作为世界要素提案" in prompts["lore"]
        assert "【本书专名册】" not in prompts["hooks"]

    def test_rerun_success_clears_stale_failed_rows(self, monkeypatch):
        _root, nid, ch_id = asyncio.run(_seed())
        # 存量失败行（旧代码产物）
        _add_row(nid, ch_id, "hooks", {}, status="failed")

        class _Fake:
            async def chat(self, **kwargs):
                return '{"planted": [{"description": "渡口的雾", "evidence": "雾"}], "resolved": []}'

        async def _fake_client(novel_id):
            return _Fake()

        import ai_client

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_client)
        import archive.reconcile as rc

        asyncio.run(rc._run_async(nid, _root, "vol-1-ch-1", ch_id, kinds=["hooks"]))

        rows = asyncio.run(_rows_of(ch_id))
        hooks_rows = [r for r in rows if r.kind == "hooks"]
        assert len(hooks_rows) == 1
        assert hooks_rows[0].status == "pending"  # 旧 failed 已清、新 pending 承接
