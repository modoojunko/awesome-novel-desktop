"""角色 AI 端点行为测试（tasks 4.1-4.4）。

fake client 手法（照 test_world_settings_v2._fake_client）：捕获渲染后的 prompt、
按 marker 返回预置 payload——提示词渲染是纯函数，可在无模型情况下断言不变式。
"""

import asyncio
import json
import uuid

import pytest
from fastapi.testclient import TestClient

from ai_client import AITimeoutError
from auth_local.deps import require_ai_access as _require_ai_access
from auth_local.deps import require_novel_model as _require_novel_model
from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.character import Character
from models.project import Novel
from models.user import User


async def _seed(*, with_world: bool = True, with_story: bool = True) -> tuple[str, str, str]:
    from filesystem.storage import get_storage

    uid = f"cai-{uuid.uuid4().hex[:8]}"
    slug = f"cai-{uuid.uuid4().hex[:8]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="AI 测试", api_key="", api_base_url="", api_model="",
        ))
        proj = Novel(
            user_id=uid, name="AI测试书", slug=slug,
            root_path=f"./data/{slug}", source="manual", current_phase="write",
            ai_model="haiku",
        )
        session.add(proj)
        await session.commit()
        nid = proj.id

    st = get_storage()
    if with_story:
        await st.write_yaml(f"./data/{slug}", "story.yaml", {
            "synopsis": "杂役弟子靠背残页翻盘。", "genre": "仙侠",
        })
    if with_world:
        await st.write_yaml(f"./data/{slug}", "settings/world-setting.yaml", {
            "stage": "九境", "power": "练气到化神", "cost": "折寿",
        })
    return uid, nid, f"./data/{slug}"


async def _add_card(nid: str, **kw) -> Character:
    async with async_session() as session:
        ch = Character(novel_id=nid, seq=1, name=kw.get("name", "林拾"),
                       role=kw.get("role", "主角"))
        if "persona" in kw:
            ch.persona = kw["persona"]
        if "aliases" in kw:
            ch.aliases = json.dumps(kw["aliases"], ensure_ascii=False)
        if "cog" in kw:
            ch.cog = json.dumps(kw["cog"], ensure_ascii=False)
        if "dossier" in kw:
            ch.dossier = json.dumps(kw["dossier"], ensure_ascii=False)
        session.add(ch)
        await session.commit()
        await session.refresh(ch)
        return ch


class _FakeClient:
    def __init__(self, payload, capture: list):
        self._payload = payload
        self._capture = capture

    async def chat(self, **kwargs):
        self._capture.append(kwargs)
        return json.dumps(self._payload, ensure_ascii=False)


@pytest.fixture
def client(monkeypatch):
    user_id, novel_id, _root = asyncio.run(_seed())

    async def _override():
        return {"id": user_id}

    captured: list = []
    app.dependency_overrides[get_current_user] = _override
    # 门控直通（403 路径由 TestGating 单独验）
    app.dependency_overrides[_require_ai_access] = lambda: True
    app.dependency_overrides[_require_novel_model] = lambda: True
    with TestClient(app) as c:
        yield c, novel_id, captured
    app.dependency_overrides.clear()


def _install_fake(monkeypatch, payload, captured):

    async def _fake(novel_id):
        return _FakeClient(payload, captured)

    monkeypatch.setattr("ai_client.get_ai_client_for_novel", _fake)
    monkeypatch.setattr("settings.characters_ai.get_ai_client_for_novel", _fake)


class TestDraft:
    def test_targets_only_empty_cells_and_prompt_hygiene(self, client, monkeypatch):
        """targets 只含空格；gender/age 与 personality 不出现在提示词。"""
        c, nid, captured = client
        card = asyncio.run(_add_card(nid, dossier={"race": "人族"}, cog={}))

        payloads = {
            "dossier": {"fills": {"race": "妖族改写", "look": "瘦高", "gender": "男"}},
            "cog": {"fills": {"w5": "盲区", "b1": "憨直", "personality": "多余键"}},
        }

        async def _fake(nid):
            return _PickPayload(payloads, captured)

        monkeypatch.setattr("ai_client.get_ai_client_for_novel", _fake)
        monkeypatch.setattr("settings.characters_ai.get_ai_client_for_novel", _fake)

        r = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/draft",
                   json={"target": "dossier"})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert "race" not in [cell["path"].split(".")[1] for cell in data["cells"]]  # 已填格拒绝
        assert any(cell["path"] == "dossier.look" for cell in data["cells"])
        assert all(cell["path"] != "dossier.gender" for cell in data["cells"])
        import re as _re
        prompt = captured[-1]["messages"][0]["content"]
        # 整词匹配（"stage" 里的 age 不算）；gender/age/personality 字样不得出现
        assert not _re.search(r"\bgender\b", prompt)
        assert not _re.search(r"\bage\b", prompt)
        assert not _re.search(r"\bpersonality\b", prompt)

    def test_persona_replace_and_no_recall_when_filled(self, client, monkeypatch):
        c, nid, captured = client
        card = asyncio.run(_add_card(nid))  # persona 为空 → 有 targets
        _install_fake(monkeypatch, {"persona": "新的人设一句话"}, captured)
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/draft",
                   json={"target": "persona"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["act"] == "replace"  # 人设唯一覆盖型
        assert r.json()["data"]["targets"] == ["persona"]
        # 已有人设时（采纳后）targets 为空 → 免调用直接返回
        c.patch(f"/api/novels/{nid}/characters/{card.id}", json={
            "path": "persona", "value": "新的人设一句话", "base_rev": card.rev,
        })
        r2 = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/draft",
                    json={"target": "persona"})
        assert r2.status_code == 200
        assert r2.json()["data"]["targets"] == []

    def test_blank_fills_rejected_502(self, client, monkeypatch):
        c, nid, captured = client
        card = asyncio.run(_add_card(nid, cog={}))
        _install_fake(monkeypatch, {"fills": {"w5": "   "}}, captured)
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/draft",
                   json={"target": "cog"})
        assert r.status_code == 502  # 全空 → 无可用内容

    def test_no_targets_skips_ai_call(self, client, monkeypatch):
        c, nid, captured = client
        card = asyncio.run(_add_card(nid))
        c.patch(f"/api/novels/{nid}/characters/{card.id}", json={
            "path": "persona", "value": "已有", "base_rev": card.rev,
        })
        called = {"n": 0}

        class _Boom(_FakeClient):
            async def chat(self, **kw):
                called["n"] += 1
                return "{}"

        async def _fake(nid):
            return _Boom({}, captured)

        monkeypatch.setattr("ai_client.get_ai_client_for_novel", _fake)
        monkeypatch.setattr("settings.characters_ai.get_ai_client_for_novel", _fake)
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/draft",
                   json={"target": "persona"})
        assert r.status_code == 200
        assert called["n"] == 0  # 免调用


class _PickPayload(_FakeClient):
    """按 prompt 里的 target 特征（targets 行内容）挑 payload——简化：轮换。"""

    def __init__(self, payloads_by_marker: dict, capture: list):
        super().__init__({}, capture)
        self._by_marker = payloads_by_marker

    async def chat(self, **kwargs):
        prompt = kwargs["messages"][0]["content"]
        self._capture.append(kwargs)
        if "只补这些空格" in prompt and "w5" in prompt:
            return json.dumps(self._by_marker["cog"], ensure_ascii=False)
        return json.dumps(self._by_marker["dossier"], ensure_ascii=False)


class TestCheck:
    def test_four_states_and_server_items(self, client, monkeypatch):
        c, nid, captured = client
        card = asyncio.run(_add_card(nid, cog={"w5": "x", "p3": "y", "p4": "z"}))
        payload = {"items": [
            {"name": "简介 × 角色", "status": "ok", "note": "一致"},
            {"name": "题材 × 角色", "status": "warn", "note": "调子偏冷"},
            {"name": "世界 × 能力上限", "status": "conflict", "note": "超过化神"},
            {"name": "世界 × 代价", "status": "ok", "note": "对得上"},
            {"name": "势力 × 角色落地", "status": "miss", "note": "势力未填"},
            {"name": "主线 × 角色", "status": "ok", "note": "一致"},
            {"name": "编外项", "status": "ok", "note": "模型乱加"},
        ], "verdict": "总体成立"}
        _install_fake(monkeypatch, payload, captured)
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/check", json={})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        names = [i["name"] for i in data["items"]]
        assert len(names) == 6  # 编外项被丢弃
        statuses = {i["name"]: i["status"] for i in data["items"]}
        assert statuses["世界 × 能力上限"] == "conflict"
        assert statuses["势力 × 角色落地"] == "miss"
        gotos = {i["name"]: i.get("goto") for i in data["items"]}
        assert gotos["世界 × 能力上限"] == "layer:power"  # goto 服务端出
        assert gotos["势力 × 角色落地"] == "panel:world"

    def test_does_not_pollute_world_check_whitelist(self):
        """回归锁：conflict 绝不进世界页白名单。"""
        from settings.world_model import _CHECK_STATUS

        assert "conflict" not in _CHECK_STATUS
        from settings.character_model import CHAR_CHECK_STATUS

        assert CHAR_CHECK_STATUS == ("ok", "warn", "conflict", "miss")

    def test_degraded_when_inputs_missing(self, client, monkeypatch):
        c, nid, captured = client
        # 覆写种子：清空 story / world（就在本书 root 上覆盖为空）
        async def _clear_inputs():
            from filesystem.storage import get_storage
            st = get_storage()
            # 查这本书的 root_path
            async with async_session() as db:
                proj = await db.get(Novel, nid)
                root = proj.root_path
            await st.write_yaml(root, "story.yaml", {})
            await st.delete_file(root, "settings/world-setting.yaml")

        asyncio.run(_clear_inputs())
        card = asyncio.run(_add_card(nid))
        called = {"n": 0}

        class _Boom(_FakeClient):
            async def chat(self, **kw):
                called["n"] += 1
                return "{}"

        async def _fake(nid):
            return _Boom({}, captured)

        monkeypatch.setattr("ai_client.get_ai_client_for_novel", _fake)
        monkeypatch.setattr("settings.characters_ai.get_ai_client_for_novel", _fake)
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/check", json={})
        assert r.status_code == 200  # 降级不 400
        data = r.json()["data"]
        assert data["degraded"] is True
        assert all(i["status"] == "miss" for i in data["items"])
        assert called["n"] == 0  # 全空免调用

    def test_extra_card_no_cognition_short_circuit(self, client):
        c, nid, _captured = client
        card = asyncio.run(_add_card(nid, role="路人", name="路人甲"))
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/check", json={})
        assert r.status_code == 200
        assert r.json()["data"]["degraded"] is True


class TestGating:
    def test_free_user_blocked_403(self, client, monkeypatch):
        c, nid, _captured = client
        card = asyncio.run(_add_card(nid))

        # 模拟免费用户：覆盖 require_ai_access 的依赖为抛 403
        from fastapi import HTTPException

        from settings.characters_ai import require_ai_access as _unused  # noqa: F401

        def _forbidden():
            raise HTTPException(403, "该功能属于 PRO 套餐")

        app.dependency_overrides[require_ai_access_dep()] = _forbidden
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/{card.id}/draft",
                   json={"target": "persona"})
        assert r.status_code == 403


def require_ai_access_dep():
    from auth_local.deps import require_ai_access

    return require_ai_access


class TestBootstrap:
    """从简介立主角（character-bootstrap-from-intro）：只出稿不建卡、只补空格、性别年龄永不出现。"""

    def test_returns_draft_without_creating_card(self, client, monkeypatch):
        c, nid, captured = client
        _install_fake(monkeypatch, {
            "name": "林拾", "aliases": ["拾哥"],
            "persona": "扫了十年落叶的杂役弟子，一双能看见修为漏洞的眼。",
            "fills": {"race": "人族", "faction": "青梧宗", "plot": "背残页翻盘",
                      "w1": "修行如登山", "w5": "不知眼眸来历", "p3": "化神即顶"},
            "skipped": [{"key": "age", "why": "作者自己定"}],
        }, captured)
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap", json={})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == "林拾"
        assert data["aliases"] == ["拾哥"]
        assert data["persona"] == "扫了十年落叶的杂役弟子，一双能看见修为漏洞的眼。"
        paths = [cell["path"] for cell in data["cells"]]
        assert "dossier.race" in paths and "dossier.faction" in paths and "dossier.plot" in paths
        assert "cog.w5" in paths and "cog.p3" in paths
        # 只出稿不落库
        rows = asyncio.run(_roster_count(nid))
        assert rows == 0
        # prompt 带上了简介与题材
        prompt = captured[0]["messages"][0]["content"]
        assert "背残页翻盘" in prompt and "仙侠" in prompt

    def test_gender_age_never_enter_cells(self, client, monkeypatch):
        c, nid, _captured = client
        _install_fake(monkeypatch, {
            "name": "林拾", "aliases": [], "persona": "人设",
            "fills": {"gender": "男", "age": "十六", "race": "人族", "w5": "盲区"},
        }, [])
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap", json={})
        assert r.status_code == 200
        paths = [cell["path"] for cell in r.json()["data"]["cells"]]
        assert "dossier.gender" not in paths and "dossier.age" not in paths
        assert "dossier.race" in paths and "cog.w5" in paths

    def test_400_when_synopsis_missing(self, client, monkeypatch):
        c, nid, _captured = client

        async def _wipe():
            from filesystem.storage import get_storage
            async with async_session() as session:
                proj = await session.get(Novel, nid)
                slug = proj.slug
            st = get_storage()
            data = await st.read_yaml(f"./data/{slug}", "story.yaml") or {}
            data["synopsis"] = ""
            await st.write_yaml(f"./data/{slug}", "story.yaml", data)

        asyncio.run(_wipe())
        _install_fake(monkeypatch, {"name": "x"}, [])
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap", json={})
        assert r.status_code == 400
        assert "简介" in r.json()["detail"]

    def test_empty_output_502(self, client, monkeypatch):
        c, nid, _captured = client
        _install_fake(monkeypatch, {"name": "", "aliases": [], "persona": "", "fills": {}}, [])
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap", json={})
        assert r.status_code == 502
        assert "没给出可用的内容" in r.json()["detail"]

    def test_timeout_records_fail_usage(self, client, monkeypatch):
        c, nid, _captured = client
        calls: list[dict] = []

        async def _fake_record(db, **kw):
            calls.append(kw)

        monkeypatch.setattr("settings.characters_ai.record_usage", _fake_record)

        class _TimeoutClient:
            async def chat(self, **kwargs):
                raise AITimeoutError("timed out")

        async def _fake(novel_id):
            return _TimeoutClient()

        monkeypatch.setattr("ai_client.get_ai_client_for_novel", _fake)
        monkeypatch.setattr("settings.characters_ai.get_ai_client_for_novel", _fake)

        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap", json={})
        assert r.status_code == 502
        assert "超时" in r.json()["detail"]
        assert calls and calls[0]["operation"] == "settings_char_bootstrap_fail" and calls[0]["force"] is True

    def test_named_card_only_fills_empty_and_reports_skips(self, client, monkeypatch):
        """主角待立：已有名字/人设/已写格一律不动，改记入 skipped。"""
        c, nid, _captured = client
        card = asyncio.run(_add_card(nid, name="林拾", role="主角", persona="已有的人设",
                                     dossier={"race": "人族"},
                                     cog={"w5": "已有盲区"}))
        captured: list = []
        _install_fake(monkeypatch, {
            "name": "另名", "aliases": ["外号"], "persona": "新的人设",
            "fills": {"race": "再写一次", "faction": "青梧宗", "w5": "再写一次", "p3": "上限"},
        }, captured)
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap",
                   json={"character_id": card.id})
        assert r.status_code == 200
        data = r.json()["data"]
        # 卡上名字/人设已有 → 不返回；别名卡上为空 → 照给
        assert data["name"] == "" and data["persona"] == "" and data["aliases"] == ["外号"]
        skips = {s["key"] for s in data["skipped"]}
        assert {"name", "persona"} <= skips and "aliases" not in skips
        paths = [cell["path"] for cell in data["cells"]]
        assert "dossier.race" not in paths and "cog.w5" not in paths
        assert "dossier.faction" in paths and "cog.p3" in paths
        # prompt 的已写段带上了卡上已有内容
        prompt = captured[0]["messages"][0]["content"]
        assert "已有盲区" in prompt

    def test_placeholder_name_card_still_gets_name(self, client, monkeypatch):
        c, nid, _captured = client
        card = asyncio.run(_add_card(nid, name="\u0000abcdef123456", role="主角"))
        _install_fake(monkeypatch, {"name": "林拾", "persona": "人设"}, [])
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap",
                   json={"character_id": card.id})
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "林拾"

    def test_existing_aliases_skipped(self, client, monkeypatch):
        c, nid, _captured = client
        card = asyncio.run(_add_card(nid, name="\u0000abcdef654321", role="主角",
                                     aliases=["旧号"]))
        _install_fake(monkeypatch, {"name": "林拾", "aliases": ["新号"]}, [])
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap",
                   json={"character_id": card.id})
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["aliases"] == []
        assert any(s["key"] == "aliases" for s in data["skipped"])

    def test_unknown_bootstrap_gives_404(self, client, monkeypatch):
        c, nid, _captured = client
        _install_fake(monkeypatch, {"name": "x"}, [])
        r = c.post(f"/api/novels/{nid}/settings/ai/characters/bootstrap",
                   json={"character_id": "no-such-id"})
        assert r.status_code == 404


async def _roster_count(nid: str) -> int:
    from sqlalchemy import select

    async with async_session() as session:
        rows = (await session.scalars(
            select(Character.id).where(Character.novel_id == nid)
        )).all()
        return len(rows)
