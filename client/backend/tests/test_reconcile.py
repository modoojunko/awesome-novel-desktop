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

    def test_hooks_advance_resolves_and_advances_by_ref(self):
        """对账制采纳（c-hooks-advance-ledger）：resolved/advanced 按编号精确命中——
        兑现转已收束（payoff_note 落库）、推进回填 mentioned（状态不动）；不建新行；
        幻觉编号跳过不断批。"""
        _root, nid, ch_id = asyncio.run(_seed())

        async def _seed_hooks():
            from settings.hooks_service import create_hook

            async with async_session() as s:
                await create_hook(s, nid, {
                    "description": "猎血短刃来历不明", "type": "mystery",
                    "priority": 2, "status": "active",
                })
                await create_hook(s, nid, {
                    "description": "旧咬痕身世之谜", "type": "mystery",
                    "priority": 2, "status": "active",
                })

        asyncio.run(_seed_hooks())
        rid = _add_row(nid, ch_id, "hooks", {
            "resolved": [{"ref": "#H-0001", "note": "短刃出自教团圣物库", "evidence": "他认出了纹章"}],
            "advanced": [{"ref": "#H-0002", "note": "咬痕在月光下发亮", "evidence": "灰白泛起微光"},
                         {"ref": "#H-9999", "note": "幻觉编号", "evidence": "…"}],
            "planted": [{"description": "西仓巷的新委托"}],
        })
        self._accept(nid, rid)

        async def _hooks():
            async with async_session() as s:
                return {
                    h.seq: h
                    for h in (
                        await s.scalars(
                            select(NovelHook).where(NovelHook.novel_id == nid)
                        )
                    ).all()
                }

        hooks = asyncio.run(_hooks())
        assert _get_row(rid).status == "accepted"  # 幻觉编号不中断整批
        assert hooks[1].status == "resolved"
        assert hooks[1].payoff_note == "短刃出自教团圣物库"
        assert hooks[2].status == "active"
        assert hooks[2].mentioned_chapter_id == ch_id  # 最近推进回填
        # 只新建 planted 一条；resolved/advanced 未建任何重复行
        assert sum(1 for h in hooks.values() if "西仓巷" in h.description) == 1
        assert len(hooks) == 3

    def test_hooks_legacy_resolved_still_matches_by_description(self):
        """存量 pending 行兼容：resolved 无 ref 有 description → 旧描述包含匹配仍生效。"""
        _root, nid, ch_id = asyncio.run(_seed())

        async def _seed_hook():
            from settings.hooks_service import create_hook

            async with async_session() as s:
                await create_hook(s, nid, {
                    "description": "码头上的陌生船家", "type": "mystery",
                    "priority": 2, "status": "active",
                })

        asyncio.run(_seed_hook())
        rid = _add_row(nid, ch_id, "hooks", {
            "planted": [],
            "resolved": [{"description": "陌生船家", "evidence": "船家解开缆绳"}],
        })
        self._accept(nid, rid)

        async def _hooks():
            async with async_session() as s:
                return (await s.scalars(
                    select(NovelHook).where(NovelHook.novel_id == nid)
                )).all()

        hooks = asyncio.run(_hooks())
        assert _get_row(rid).status == "accepted"
        assert next(h for h in hooks if "船家" in h.description).status == "resolved"
        assert len(hooks) == 1  # 未命中不再建已收束新条


class TestHooksPrompt:
    def test_prompt_carries_reconcile_ledger_and_caps(self):
        """hooks 提示词对账制（c-hooks-advance-ledger）：编号台账注入＋三类产出
        ＋条数上限＋真伏笔判据；e2e 桩依赖短语保留。"""
        from archive.reconcile import _collect_prompts

        prompts = dict(
            _collect_prompts(
                "vol-1-ch-1", {}, "正文", [],
                world_now="", roster="",
                hooks_now=(
                    "本书已有伏笔台账（先对账：判断本章是否兑现或推进了其中条目，"
                    "resolved/advanced 按编号引用；相同或高度相似的不要重复登记为新埋）：\n"
                    "- #H-0001 旧钩（计划收束：第 4 章）"
                ),
            )
        )
        p = prompts["hooks"]
        assert "对既有伏笔的兑现与推进" in p
        assert "埋下或收束了哪些伏笔" in p or "新埋" in p  # 桩匹配短语演化留证
        assert "#H-0001 旧钩" in p and "计划收束：第 4 章" in p
        assert "resolved、advanced、planted 各最多 3 条" in p
        assert "planted 输出空数组" in p  # 宁缺勿滥
        assert "氛围描写、场景细节" in p
        # 剧情走向排除（09-29 真机反馈：什么都识别成伏笔，用户手删多条）
        assert "剧情走向不是伏笔" in p
        assert "未解承诺" in p and "读者会觉得被辜负" in p
        assert "章末悬念断点" in p and "问完即答≠伏笔" in p

    def test_prompt_without_ledger_has_no_block(self):
        from archive.reconcile import _collect_prompts

        p = dict(_collect_prompts("vol-1-ch-1", {}, "正文", []))["hooks"]
        assert "已有伏笔台账" not in p
        assert "resolved、advanced、planted 各最多 3 条" in p


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


class TestLoreBareArrayAndTruncationHint:
    """c-reconcile-empty-array-fix：lore 提示词形状唯一＋裸数组兜底＋截断判据不误报。

    真机实锤 09-29：旧提示词「JSON 数组输出/没有则输出空数组」教模型回了字面
    `[]`，解析器只认对象落失败行，截断判据（结尾非 "}"）又误诊「被预算截断」。
    """

    def test_lore_prompt_single_object_shape(self):
        from archive.reconcile import _collect_prompts

        prompts = dict(_collect_prompts("vol-1-ch-1", {}, "正文", []))
        # 唯一形状：对象；无新要素 → {"items": []}
        assert '{"items": []}' in prompts["lore"]
        assert "JSON 对象输出" in prompts["lore"]
        assert "JSON 数组输出" not in prompts["lore"]
        assert "没有则输出空数组" not in prompts["lore"]
        assert "识别新出现或变化的世界要素" in prompts["lore"]  # e2e 桩锚点短语
        # hooks 同口径理顺（对象三键）；桩锚点与既有断言短语不动
        assert "JSON 对象输出" in prompts["hooks"]
        assert "JSON 数组输出" not in prompts["hooks"]
        assert "对既有伏笔的兑现与推进" in prompts["hooks"]
        assert "planted 输出空数组" in prompts["hooks"]

    def test_parse_lenient_bare_array_wrap_lore_only(self):
        from archive.reconcile import _parse_json_lenient

        assert _parse_json_lenient("[]", allow_bare_array=True) == {"items": []}
        assert _parse_json_lenient(
            '[{"key": "临江渡口", "value": "北境最大渡口", "set": "extra"}]',
            allow_bare_array=True,
        ) == {"items": [{"key": "临江渡口", "value": "北境最大渡口", "set": "extra"}]}
        # 对象优先语义不变；不开兜底时裸数组仍失败（hooks 语义）
        assert _parse_json_lenient('{"items": []}', allow_bare_array=True) == {"items": []}
        assert _parse_json_lenient("[]") is None
        # 前导文字含 [ 的对象输出走对象路径（评审 #607 P2：对账常带 [#H-xxxx]
        # 前导引用、lore 可能带 [第N段] 式引注——不得因数组优先短路误判失败）
        assert _parse_json_lenient(
            '比对台账[#H-0001]后判断：{"resolved": [], "advanced": [{"ref": "#H-0001"}]}'
        ) == {"resolved": [], "advanced": [{"ref": "#H-0001"}]}
        assert _parse_json_lenient(
            '根据正文[第3段]识别：{"items": [{"key": "临江渡口"}]}', allow_bare_array=True
        ) == {"items": [{"key": "临江渡口"}]}
        # 数组段残缺（截断）→ 对象回退也不得把首元素当顶层对象（对象段亦不合法则 None）
        assert _parse_json_lenient('[{"key": "a"}, {"key": "b', allow_bare_array=True) \
            == {"key": "a"}  # 与旧实现同口径：截取首 { 到末 }

    def test_lore_bare_empty_array_succeeds_and_clears_stale_failed(self, monkeypatch):
        _root, nid, ch_id = asyncio.run(_seed())
        _add_row(nid, ch_id, "lore", {}, status="failed")  # 真机存量失败行

        class _Fake:
            async def chat(self, **kwargs):
                return "[]"  # 旧措辞教出来的字面空数组

        async def _fake_client(novel_id):
            return _Fake()

        import ai_client

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_client)
        import archive.reconcile as rc

        asyncio.run(rc._run_async(nid, _root, "vol-1-ch-1", ch_id, kinds=["lore"]))

        # c-lore-reconcile-guardrails：空批（模型真空或护栏滤空）不落行、不覆盖
        # 既有未决行（空行＝「待确认 1（无明细）」假信号）；本轮已成功 → 旧失败行
        # 照清，列表不残留（#607 关心的「失败行永久挂列表」仍成立）
        lore_rows = [r for r in asyncio.run(_rows_of(ch_id)) if r.kind == "lore"]
        assert lore_rows == []

    def test_lore_bare_array_with_items_becomes_pending(self, monkeypatch):
        _root, nid, ch_id = asyncio.run(_seed())

        class _Fake:
            async def chat(self, **kwargs):
                return '[{"key": "临江渡口", "value": "北境最大的渡口", "set": "extra"}]'

        async def _fake_client(novel_id):
            return _Fake()

        import ai_client

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_client)
        import archive.reconcile as rc

        asyncio.run(rc._run_async(nid, _root, "vol-1-ch-1", ch_id, kinds=["lore"]))

        lore_rows = [r for r in asyncio.run(_rows_of(ch_id)) if r.kind == "lore"]
        assert len(lore_rows) == 1 and lore_rows[0].status == "pending"
        items = json.loads(lore_rows[0].payload)["items"]
        assert items == [{"key": "临江渡口", "value": "北境最大的渡口", "set": "extra"}]

    def test_hooks_bare_array_fails_without_truncation_hint(self, monkeypatch):
        """hooks 裸数组维持失败（无对账语义）；`[]` 是完整短输出，不得误报截断。"""
        _root, nid, ch_id = asyncio.run(_seed())

        class _Fake:
            async def chat(self, **kwargs):
                return "[]"

        async def _fake_client(novel_id):
            return _Fake()

        import ai_client

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_client)
        import archive.reconcile as rc

        asyncio.run(rc._run_async(nid, _root, "vol-1-ch-1", ch_id, kinds=["hooks"]))

        hooks_rows = [r for r in asyncio.run(_rows_of(ch_id)) if r.kind == "hooks"]
        assert len(hooks_rows) == 1
        assert hooks_rows[0].status == "failed"
        assert "parse" in hooks_rows[0].error
        assert "疑似被输出预算截断" not in hooks_rows[0].error

    def test_hooks_preamble_with_ledger_ref_parses(self, monkeypatch):
        """评审 #607 P2：前导句引用台账编号（[#H-0001]）的对象输出不得误判失败。"""
        _root, nid, ch_id = asyncio.run(_seed())

        class _Fake:
            async def chat(self, **kwargs):
                return (
                    '比对台账[#H-0001]后判断：'
                    '{"resolved": [], '
                    '"advanced": [{"ref": "#H-0001", "note": "雾中人数被清点", '
                    '"evidence": "雾里传来第二个呼吸声"}], "planted": []}'
                )

        async def _fake_client(novel_id):
            return _Fake()

        import ai_client

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_client)
        import archive.reconcile as rc

        asyncio.run(rc._run_async(nid, _root, "vol-1-ch-1", ch_id, kinds=["hooks"]))

        hooks_rows = [r for r in asyncio.run(_rows_of(ch_id)) if r.kind == "hooks"]
        assert len(hooks_rows) == 1
        assert hooks_rows[0].status == "pending"  # 不落失败行
        payload = json.loads(hooks_rows[0].payload)
        assert payload["advanced"][0]["ref"] == "#H-0001"


class TestLoreGuardrails:
    """c-lore-reconcile-guardrails：lore 提案侧护栏＋prompt 注入＋采纳侧归并/复检。

    真机事故对照（演示栈《我在夜晚打吸血鬼》两章灌 13 条）：人物进势力格（银铎）、
    跨格双落（停战条款第三条 history+factions）、单批 8 条无上限、势力 6/6 满。
    """

    def _accept(self, nid: str, row_id: str):
        from archive.reconcile import apply_accept

        async def _run():
            async with async_session() as s:
                row = await s.get(ChapterReconcile, row_id)
                await apply_accept(s, row)
                await s.commit()

        asyncio.run(_run())

    # ── 提案侧过滤 ──

    def test_filter_truncates_to_batch_max(self):
        from archive.reconcile import _filter_lore_items

        items = [{"key": f"要素{i}", "value": "v", "set": "extra"} for i in range(6)]
        kept, trace = _filter_lore_items(items, set(), [])
        assert [k["key"] for k in kept] == [f"要素{i}" for i in range(4)]
        assert trace["truncated"] == ["要素4", "要素5"]

    def test_filter_drops_cast_name_silver_case(self):
        """银铎案形状：cast 有名、名册无卡——名目命中出场名单即丢（无论 set）。"""
        from archive.reconcile import _filter_lore_items, _norm

        items = [
            {"key": "银铎", "value": "圣银教团猎魔人", "set": "factions"},
            {"key": "静默带", "value": "无信号航段", "set": "extra"},
        ]
        kept, trace = _filter_lore_items(items, {_norm("银铎")}, [])
        assert [k["key"] for k in kept] == ["静默带"]
        assert trace["dropped"] == [{"key": "银铎", "reason": "cast"}]

    def test_filter_faction_cap_keeps_existing(self):
        """势力 ≥3：新名目丢弃、命中既有势力放行；extra 类不受势力上限影响。"""
        from archive.reconcile import _filter_lore_items, _norm

        facs = [_norm(n) for n in ("夜巡", "血族议会", "圣银教团")]
        items = [
            {"key": "猎魔人公会", "value": "新组织", "set": "factions"},
            {"key": "圣银教团", "value": "更新既有势力", "set": "factions"},
            {"key": "哨站", "value": "地点", "set": "extra"},
        ]
        kept, trace = _filter_lore_items(items, set(), facs)
        assert [k["key"] for k in kept] == ["圣银教团", "哨站"]
        assert trace["dropped"] == [{"key": "猎魔人公会", "reason": "faction_cap"}]

    def test_filter_skips_non_dict_and_keyless(self):
        from archive.reconcile import _filter_lore_items

        kept, trace = _filter_lore_items(["junk", None, {"key": ""}], set(), [])
        assert kept == []
        assert trace["dropped"] == []

    # ── prompt 注入 ──

    def test_lore_prompt_injects_faction_and_pending_blocks(self):
        from archive.reconcile import _collect_prompts

        prompts = dict(_collect_prompts(
            "vol-1-ch-3", {}, "正文", ["林晚"], "现有世界设定文",
            faction_line="现有势力（2 个）：夜巡、血族议会",
            pending_line="以下名目已有提案待作者确认，不要重复提：屠宰巷",
        ))
        lore = prompts["lore"]
        assert "现有势力（2 个）：夜巡、血族议会" in lore
        assert "以下名目已有提案待作者确认，不要重复提：屠宰巷" in lore
        # 护栏口径逐项在 prompt 中
        assert "势力先立两三个" in lore
        assert "变相提交" in lore
        assert "名目（key）不得是人名" in lore
        assert "constraints" in lore
        assert "识别新出现或变化的世界要素" in lore  # e2e 桩锚点短语，逐字保留

    def test_lore_prompt_blocks_absent_without_material(self):
        from archive.reconcile import _collect_prompts

        prompts = dict(_collect_prompts("vol-1-ch-1", {}, "正文", []))
        assert "现有势力（" not in prompts["lore"]
        assert "待作者确认" not in prompts["lore"]

    def test_run_async_pending_injection_excludes_current_chapter(self, monkeypatch):
        """他章 pending 名目注入、本章排除（防自吞：旧名目被「不要重复提」压掉
        → 新批省略 → 整行覆盖 → 未拍板提案静默蒸发）。"""
        _root, nid, ch_id = asyncio.run(_seed())

        async def _seed_second():
            async with async_session() as s:
                ch = (await s.scalars(select(Chapter).where(Chapter.id == ch_id))).one()
                ch2 = Chapter(
                    project_id=ch.project_id, volume_id=ch.volume_id, chapter_no=2,
                    ref="vol-1-ch-2", title="第2章", status="archived",
                    word_count=20, has_prose=True,
                )
                s.add(ch2)
                await s.flush()
                s.add(ChapterContent(chapter_id=ch2.id, prose="第2章正文：风更大。"))
                await s.commit()
                return ch2.id

        ch2_id = asyncio.run(_seed_second())
        _add_row(nid, ch2_id, "lore", {"items": [{"key": "屠宰巷", "value": "v", "set": "extra"}]})
        _add_row(nid, ch_id, "lore", {"items": [{"key": "本章专属名目", "value": "v", "set": "extra"}]})

        captured: dict = {}

        class _Fake:
            async def chat(self, **kwargs):
                captured["prompt"] = kwargs["messages"][0]["content"]
                return '{"items": [{"key": "临江渡口", "value": "北境最大的渡口", "set": "extra"}]}'

        async def _fake_client(novel_id):
            return _Fake()

        import ai_client

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_client)
        import archive.reconcile as rc

        asyncio.run(rc._run_async(nid, _root, "vol-1-ch-1", ch_id, kinds=["lore"]))

        assert "屠宰巷" in captured["prompt"]           # 他章 pending 名目注入
        assert "本章专属名目" not in captured["prompt"]  # 本章排除
        lore_rows = [
            r for r in asyncio.run(_rows_of(ch_id))
            if r.kind == "lore" and r.status == "pending"
        ]
        assert len(lore_rows) == 1
        assert json.loads(lore_rows[0].payload)["items"][0]["key"] == "临江渡口"

    def test_run_async_empty_after_filter_no_row_no_overwrite(self, monkeypatch):
        """整批过滤为空：不落行、不覆盖既有未决行（空行＝「待确认 1」假信号）。"""
        _root, nid, ch_id = asyncio.run(_seed())
        _add_row(nid, ch_id, "lore", {"items": [{"key": "既有提案", "value": "v", "set": "extra"}]})

        class _Fake:
            async def chat(self, **kwargs):
                # 唯一候选为出场人物名目（_seed 出场＝林晚）→ 过滤后为空
                return '{"items": [{"key": "林晚", "value": "主角", "set": "extra"}]}'

        async def _fake_client(novel_id):
            return _Fake()

        import ai_client

        monkeypatch.setattr(ai_client, "get_ai_client_for_novel", _fake_client)
        import archive.reconcile as rc

        asyncio.run(rc._run_async(nid, _root, "vol-1-ch-1", ch_id, kinds=["lore"]))

        lore_rows = [
            r for r in asyncio.run(_rows_of(ch_id))
            if r.kind == "lore" and r.status == "pending"
        ]
        assert len(lore_rows) == 1
        assert json.loads(lore_rows[0].payload)["items"][0]["key"] == "既有提案"

    # ── 采纳侧归并＋复检 ──

    def test_accept_merges_cross_set_same_name_no_dual_land(self):
        """停战条款案：history 已有（origin=旧章），提案 set=factions 归一化同名
        → 更新既有条目（字面 key/origin/set），factions 不出现该名目。"""
        from filesystem.storage import get_storage

        root, nid, ch_id = asyncio.run(_seed())

        async def _seed_world():
            await get_storage().write_yaml(root, "settings/world-setting.yaml", {
                "history": [{"key": "停战条款第三条", "value": "旧文", "origin": "vol-1-ch-0"}],
                "factions": [], "constraints": [], "extra": [],
            })

        asyncio.run(_seed_world())
        rid = _add_row(nid, ch_id, "lore", {"items": [
            {"key": "停战条款第三条", "value": "新文", "set": "factions"},
        ]})
        self._accept(nid, rid)
        assert _get_row(rid).status == "accepted"

        world = asyncio.run(
            get_storage().read_yaml(root, "settings/world-setting.yaml")
        ) or {}
        assert len(world.get("history") or []) == 1
        assert world["history"][0]["value"] == "新文"
        assert world["history"][0]["origin"] == "vol-1-ch-0"
        assert not (world.get("factions") or [])

    def test_accept_rewrites_with_literal_key(self):
        """既有 key 系作者手书异形（内部空格）→ 字面改写仍命中，不新增第二条。"""
        from filesystem.storage import get_storage

        root, nid, ch_id = asyncio.run(_seed())

        async def _seed_world():
            await get_storage().write_yaml(root, "settings/world-setting.yaml", {
                "history": [{"key": "停战条款 第三条", "value": "旧文", "origin": "vol-1-ch-0"}],
                "factions": [], "constraints": [], "extra": [],
            })

        asyncio.run(_seed_world())
        rid = _add_row(nid, ch_id, "lore", {"items": [
            {"key": "停战条款第三条", "value": "新文", "set": "history"},
        ]})
        self._accept(nid, rid)

        world = asyncio.run(
            get_storage().read_yaml(root, "settings/world-setting.yaml")
        ) or {}
        assert len(world.get("history") or []) == 1
        assert world["history"][0]["key"] == "停战条款 第三条"
        assert world["history"][0]["value"] == "新文"

    def test_accept_dedupes_in_batch_same_name(self):
        """批内同名目 set 各异 → 仅首条入账（停战条款案批内变体）。"""
        from filesystem.storage import get_storage

        root, nid, ch_id = asyncio.run(_seed())
        rid = _add_row(nid, ch_id, "lore", {"items": [
            {"key": "停战条款", "value": "第一条", "set": "history"},
            {"key": "停战条款", "value": "第二条", "set": "factions"},
        ]})
        self._accept(nid, rid)

        world = asyncio.run(
            get_storage().read_yaml(root, "settings/world-setting.yaml")
        ) or {}
        hist = [e for e in (world.get("history") or []) if e.get("key") == "停战条款"]
        assert len(hist) == 1 and hist[0]["value"] == "第一条"
        assert not (world.get("factions") or [])

    def test_accept_drops_cast_names_and_annotates(self):
        """采纳侧人物复检：人物名目丢弃不入账，其余照常，payload 留痕。"""
        from filesystem.storage import get_storage

        root, nid, ch_id = asyncio.run(_seed())  # 出场＝林晚（ChapterCharacter）
        rid = _add_row(nid, ch_id, "lore", {"items": [
            {"key": "林晚", "value": "主角档案", "set": "factions"},
            {"key": "静默带", "value": "航段", "set": "extra"},
        ]})
        self._accept(nid, rid)
        row = _get_row(rid)
        assert row.status == "accepted"
        guard = json.loads(row.payload).get("guard") or {}
        assert guard.get("dropped_cast") == ["林晚"]

        world = asyncio.run(
            get_storage().read_yaml(root, "settings/world-setting.yaml")
        ) or {}
        assert not (world.get("factions") or [])
        assert any(e.get("key") == "静默带" for e in world.get("extra") or [])

    def test_accept_does_not_merge_into_constraints(self):
        """constraints 不进归并目标：同归一化名目提案（set=extra）落 extra 新条，
        铁律原文不被覆盖（作者手写硬边界）。"""
        from filesystem.storage import get_storage

        root, nid, ch_id = asyncio.run(_seed())

        async def _seed_world():
            await get_storage().write_yaml(root, "settings/world-setting.yaml", {
                "history": [], "factions": [],
                "constraints": [{"key": "银器定伤", "value": "作者手写铁律原文"}],
                "extra": [],
            })

        asyncio.run(_seed_world())
        rid = _add_row(nid, ch_id, "lore", {"items": [
            {"key": "银器定伤", "value": "AI 改写版", "set": "extra"},
        ]})
        self._accept(nid, rid)

        world = asyncio.run(
            get_storage().read_yaml(root, "settings/world-setting.yaml")
        ) or {}
        assert world["constraints"][0]["value"] == "作者手写铁律原文"
        assert any(
            e.get("key") == "银器定伤" and e.get("value") == "AI 改写版"
            for e in world.get("extra") or []
        )

    def test_accept_updates_existing_faction_when_full(self):
        """势力 6/6 满状态下采纳既有势力更新：归并命中 → 更新 note，
        不整批 ValueError（真机紧迫项）。"""
        from filesystem.storage import get_storage

        root, nid, ch_id = asyncio.run(_seed())

        async def _seed_world():
            await get_storage().write_yaml(root, "settings/world-setting.yaml", {
                "history": [], "constraints": [], "extra": [],
                "factions": [{"name": f"势力{i}", "note": f"旧{i}"} for i in range(6)],
            })

        asyncio.run(_seed_world())
        rid = _add_row(nid, ch_id, "lore", {"items": [
            {"key": "势力3", "value": "新注", "set": "factions"},
        ]})
        self._accept(nid, rid)
        assert _get_row(rid).status == "accepted"

        world = asyncio.run(
            get_storage().read_yaml(root, "settings/world-setting.yaml")
        ) or {}
        target = next(f for f in world["factions"] if f["name"] == "势力3")
        assert target["note"] == "新注"
        assert len(world["factions"]) == 6
