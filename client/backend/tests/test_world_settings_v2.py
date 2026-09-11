"""世界设定契约 v2（world-setting-v2）测试：

- WorldIn 契约校验（长度/条数/重复 key/控制字符/空 key）
- normalize_world：v1 十字段映射（不丢字）、v2 passthrough、_legacy 剥离
- render_world_block / render_red_lines：预算整条从略、铁律独立、no_power 跳过
- lore-apply：(key, origin) 幂等合并、满员 400、丢弃不入账
- 一致性体检降级：简介缺失 → 相关行 miss + degraded（不 400）

Usage:
    cd client/backend
    python -m pytest tests/test_world_settings_v2.py -v
"""

import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment ─────────────────────────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_world_v2.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_world_v2_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from auth_local.deps import (  # noqa: E402
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user  # noqa: E402
from main import app  # noqa: E402
from settings.world_model import (  # noqa: E402
    lore_apply_entries,
    normalize_world,
    put_world_merged,
    read_world,
    render_red_lines,
    render_world_block,
    world_is_filled,
)


@pytest.fixture(autouse=True)
def _override_auth_gates():
    """其他模块的 teardown 会 clear 全局 overrides，这里每用例前重设。"""
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1"}
    app.dependency_overrides[require_ai_access] = lambda: True
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = lambda: True
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def pid(client) -> str:
    name = "世界V2" + uuid.uuid4().hex[:6]
    r = client.post("/api/novels", json={"name": name, "source": "manual"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ── WorldIn 契约校验 ─────────────────────────────────────────────────────


class TestWorldInContract:
    def test_value_over_limit_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "stage": "长" * 301,
        })
        assert r.status_code == 400
        assert "世界设定校验失败" in r.json()["detail"]

    def test_entry_value_over_limit_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "constraints": [{"key": "不可推翻的事", "value": "长" * 201}],
        })
        assert r.status_code == 400

    def test_entry_over_count_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "constraints": [{"key": f"锁{i}", "value": "x"} for i in range(11)],
        })
        assert r.status_code == 400

    def test_duplicate_key_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "extra": [
                {"key": "迷雾森林", "value": "a"},
                {"key": "迷雾森林", "value": "b"},
            ],
        })
        assert r.status_code == 400
        assert "迷雾森林" in r.json()["detail"]

    def test_empty_key_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "extra": [{"key": "", "value": "只有内容"}],
        })
        assert r.status_code == 400

    def test_control_chars_stripped(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "stage": "云梁\x00界",
        })
        assert r.status_code == 200
        assert "\x00" not in client.get(f"/api/novels/{pid}/settings/world").json()["stage"]

    def test_factions_over_count_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "factions": [{"name": f"势力{i}", "note": "x"} for i in range(7)],
        })
        assert r.status_code == 400


# ── 归一化与迁移（不丢字）────────────────────────────────────────────────


class TestNormalizeAndMigration:
    def test_v1_ten_fields_mapped(self):
        v1 = {
            "geography": {"scenes": "南境三地", "climate": "多雨", "limits": "北境雪山"},
            "politics": {"rule": "王朝", "factions": "青梧宗与丹阁百年对立", "social": "修士凌驾凡人", "cost": "违令逐出宗门"},
            "rules": {"world": "灵力九境", "society": "宗门律法", "personal": "血咒反噬"},
        }
        v2 = normalize_world(v1)
        assert "南境三地" in v2["stage"]
        assert v2["power"] == "灵力九境"
        assert v2["cost"] == "血咒反噬"
        keys = {e["key"]: e["value"] for e in v2["extra"]}
        assert "多雨" in keys["地理与风物"] and "北境雪山" in keys["地理与风物"]
        assert "王朝" in keys["律法与刑罚"] and "违令逐出宗门" in keys["律法与刑罚"]
        assert keys["社会与信仰"] == "修士凌驾凡人"
        assert v2["factions"][0]["note"] == "青梧宗与丹阁百年对立"

    def test_roundtrip_no_loss(self):
        v1 = {
            "geography": {"scenes": "南境", "climate": "多雨", "limits": "雪山"},
            "politics": {"rule": "王朝", "factions": "两宗对立", "social": "修士在上", "cost": "逐出宗门"},
            "rules": {"world": "灵力九境", "society": "宗门律法", "personal": "血咒反噬"},
        }
        v2 = normalize_world(v1)
        joined = "\n".join(
            [v2["stage"], v2["power"], v2["cost"]]
            + [e["value"] for e in v2["extra"]]
            + [f["note"] for f in v2["factions"]]
        )
        for fields in {
            "geography": v1["geography"], "politics": v1["politics"], "rules": v1["rules"],
        }.values():
            for v in fields.values():
                if str(v).strip():
                    assert str(v).strip() in joined, f"丢失：{v}"

    def test_read_world_strips_legacy(self):
        raw = {"stage": "云梁界", "_legacy": {"geography": {"scenes": "旧"}}}
        out = read_world(raw)
        assert out["stage"] == "云梁界"
        assert "_legacy" not in out

    def test_legacy_survives_put_merge(self):
        raw = {"_legacy": {"geography": {"scenes": "旧原文"}}}
        merged = put_world_merged(raw, {"stage": "新舞台"})
        assert merged["_legacy"]["geography"]["scenes"] == "旧原文"
        assert merged["stage"] == "新舞台"

    def test_empty_world(self):
        assert normalize_world({})["stage"] == ""
        assert normalize_world(None) == normalize_world(None)


# ── 注入渲染 ─────────────────────────────────────────────────────────────


class TestRender:
    def test_world_block_paragraphs(self):
        block = render_world_block({"stage": "云梁界", "power": "灵力九境"})
        assert "世界舞台：云梁界" in block
        assert "力量体系：灵力九境" in block
        assert block.startswith("世界观：")

    def test_red_lines_full_not_truncated(self):
        world = {"constraints": [
            {"key": f"锁{i}", "value": "长" * 150} for i in range(10)
        ]}
        lines = render_red_lines(world)
        assert len(lines) == 10
        assert all(len(x) == 158 for x in lines)  # 前缀 + 150 字，无截断

    def test_no_power_skips_power(self):
        block = render_world_block({"no_power": True, "stage": "现代都市", "power": "灵力"})
        assert "力量体系" not in block
        assert "现代都市" in block

    def test_world_block_budget_whole_entry_skip(self):
        extra = [{"key": f"条目{i}", "value": "长" * 200} for i in range(10)]
        block = render_world_block({"stage": "云梁界", "extra": extra})
        assert len(block) < 3000  # 不再是段落+全量硬塞
        assert "从略" in block

    def test_constraints_never_in_world_block(self):
        world = {"stage": "云梁界", "constraints": [{"key": "不可推翻的事", "value": "死者不可复生"}]}
        block = render_world_block(world)
        assert "不可推翻的事" not in block
        assert render_red_lines(world)[0].startswith("世界铁律·不可推翻的事")


# ── readiness 判据 ───────────────────────────────────────────────────────


class TestWorldFilled:
    def test_stage_only(self):
        assert world_is_filled({"stage": "云梁界"}) is True

    def test_entry_only(self):
        assert world_is_filled({"extra": [{"key": "地理与风物", "value": "南境多雨"}]}) is True

    def test_all_empty(self):
        assert world_is_filled({}) is False

    def test_v1_counts(self):
        assert world_is_filled({"geography": {"scenes": "南境"}}) is True


# ── lore-apply ───────────────────────────────────────────────────────────


class TestLoreApply:
    def test_append_with_origin(self):
        v2 = {"history": []}
        out = lore_apply_entries(v2, [
            {"key": "丹阁大火", "value": "三百年前", "origin": "vol-1-ch-12", "set": "history"},
        ])
        assert out["history"][0] == {"key": "丹阁大火", "value": "三百年前", "origin": "vol-1-ch-12"}

    def test_same_origin_replaces_not_duplicates(self):
        v2 = {"history": [{"key": "丹阁大火", "value": "旧表述", "origin": "vol-1-ch-12"}]}
        out = lore_apply_entries(v2, [
            {"key": "丹阁大火", "value": "新表述", "origin": "vol-1-ch-12", "set": "history"},
        ])
        assert len(out["history"]) == 1
        assert out["history"][0]["value"] == "新表述"

    def test_factions_merge_by_name(self):
        v2 = {"factions": [{"name": "丹阁", "note": "旧"}]}
        out = lore_apply_entries(v2, [{"key": "丹阁", "value": "新", "set": "factions"}])
        assert len(out["factions"]) == 1 and out["factions"][0]["note"] == "新"

    def test_unknown_set_rejected(self):
        import pytest
        with pytest.raises(ValueError):
            lore_apply_entries({}, [{"key": "x", "value": "y", "set": "characters"}])

    def test_full_set_rejected(self):
        import pytest
        v2 = {"constraints": [{"key": f"锁{i}", "value": "x"} for i in range(10)]}
        with pytest.raises(ValueError):
            lore_apply_entries(v2, [{"key": "新锁", "value": "x", "set": "constraints"}])


# ── lore 路由（suggest mock AI / apply 入账）─────────────────────────────


class TestLoreRoutes:
    def test_lore_apply_merges_and_returns_world(self, client, pid):
        r = client.post(f"/api/novels/{pid}/settings/world/lore-apply", json={
            "entries": [
                {"key": "丹阁大火", "value": "三百年前烧了半部功法",
                 "origin": "vol-1-ch-12", "set": "history"},
            ],
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert any(e["key"] == "丹阁大火" for e in data["history"])
        assert "_legacy" not in data
        # GET 也可见（已落库）
        world = client.get(f"/api/novels/{pid}/settings/world").json()
        assert any(e["key"] == "丹阁大火" for e in world["history"])

    def test_lore_apply_idempotent_same_origin(self, client, pid):
        body = {"entries": [
            {"key": "丹阁大火", "value": "v1", "origin": "vol-1-ch-12", "set": "history"},
        ]}
        client.post(f"/api/novels/{pid}/settings/world/lore-apply", json=body)
        body["entries"][0]["value"] = "v2"
        client.post(f"/api/novels/{pid}/settings/world/lore-apply", json=body)
        world = client.get(f"/api/novels/{pid}/settings/world").json()
        assert len(world["history"]) == 1
        assert world["history"][0]["value"] == "v2"

    def test_lore_apply_unknown_set_400(self, client, pid):
        r = client.post(f"/api/novels/{pid}/settings/world/lore-apply", json={
            "entries": [{"key": "x", "value": "y", "set": "characters"}],
        })
        assert r.status_code == 400

    def test_lore_suggest_normalizes_ai_output(self, client, pid, monkeypatch):
        import json as _json

        class _Fake:
            model = "fake"

            async def chat(self, *a, **k):
                return _json.dumps({"suggestions": [
                    {"key": "血衣楼", "value": "第12章登场的新势力", "set": "extra"},
                    {"key": "坏项", "value": "无 set"},
                    {"key": "", "value": "无名目", "set": "extra"},
                ]})

        async def _fake_get_client(novel_id=None):
            return _Fake()

        async def _fake_load_chapter(root_path, ref):
            return {"content": "第12章正文……", "volume": 1, "chapter": 12, "title": "x"}

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _fake_get_client)
        monkeypatch.setattr("workflow.engine.load_chapter", _fake_load_chapter)
        r = client.post(f"/api/novels/{pid}/settings/ai/world/lore-suggest",
                        json={"chapter_ref": "vol-1-ch-12"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["suggestions"] == [
            {"key": "血衣楼", "value": "第12章登场的新势力", "set": "extra"},
        ]


# ── 一致性体检降级（路由级）──────────────────────────────────────────────


class TestCheckDegraded:
    @pytest.fixture
    def client(self):
        # 复用模块级 overrides（auth/ai 门控已开）；AI 客户端在本用例内伪造成空 items
        with TestClient(app) as c:
            yield c

    def test_synopsis_missing_degrades(self, client, pid, monkeypatch):
        class _Fake:
            model = "fake"

            async def chat(self, *a, **k):
                import json
                return json.dumps({"items": [], "verdict": ""})

        async def _fake_get_client(novel_id=None):
            return _Fake()

        monkeypatch.setattr(
            "settings.ai_router.get_ai_client_for_novel", _fake_get_client
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/world/check", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["degraded"] is True
        cross = [i for i in data["items"] if "简介" in i["name"]]
        assert cross and all(i["status"] == "miss" for i in cross)


# ── 通用起草 shape（text/kv/faction）────────────────────────────────────


class TestDraftShape:
    @pytest.fixture
    def client(self):
        with TestClient(app) as c:
            yield c

    @staticmethod
    def _fake_client(payload_by_marker):
        """按 prompt 里的格式行标记返回对应 JSON 的假 AI 客户端。"""
        import json as _json

        class _Fake:
            model = "fake"

            async def chat(self, *a, **k):
                prompt = k.get("messages", [{}])[0].get("content", "")
                for marker, payload in payload_by_marker.items():
                    if marker in prompt:
                        return _json.dumps(payload)
                return _json.dumps({"value": "一段话内容"})

        async def _fake_get_client(novel_id=None):
            return _Fake()

        return _fake_get_client

    def test_default_text_shape(self, client, pid, monkeypatch):
        monkeypatch.setattr(
            "settings.ai_router.get_ai_client_for_novel", self._fake_client({})
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "力量体系"})
        assert r.status_code == 200, r.text
        assert r.json()["value"] == "一段话内容"
        assert isinstance(r.json()["value"], str)

    def test_kv_shape_normalizes(self, client, pid, monkeypatch):
        monkeypatch.setattr(
            "settings.ai_router.get_ai_client_for_novel",
            self._fake_client({"名目": {"value": [
                {"key": "不可推翻的事", "value": "死者不可复生"},
                {"key": "", "value": "缺 key 回退取名目前十字"},
                {"key": "空值", "value": ""},
                "不是字典",
            ]}}),
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "世界铁律", "shape": "kv"})
        assert r.status_code == 200, r.text
        value = r.json()["value"]
        assert isinstance(value, list)
        assert {"key": "不可推翻的事", "value": "死者不可复生"} in value
        assert {"key": "缺 key 回退取名", "value": "缺 key 回退取名目前十字"} in value
        assert len(value) == 2

    def test_kv_shape_caps_at_ten(self, client, pid, monkeypatch):
        monkeypatch.setattr(
            "settings.ai_router.get_ai_client_for_novel",
            self._fake_client({"名目": {"value": [
                {"key": f"铁律{i}", "value": "一句话"} for i in range(12)
            ]}}),
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "世界铁律", "shape": "kv"})
        assert r.status_code == 200, r.text
        assert len(r.json()["value"]) == 10

    def test_faction_shape_normalizes(self, client, pid, monkeypatch):
        monkeypatch.setattr(
            "settings.ai_router.get_ai_client_for_novel",
            self._fake_client({"势力名": {"value": [
                {"name": "丹阁", "note": "要为残卷讨一个说法"},
                {"name": "", "note": "无名者丢弃"},
                {"name": "散修联盟", "note": ""},
            ]}}),
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "势力", "shape": "faction"})
        assert r.status_code == 200, r.text
        value = r.json()["value"]
        assert {"name": "丹阁", "note": "要为残卷讨一个说法"} in value
        assert {"name": "散修联盟", "note": ""} in value
        assert len(value) == 2

    def test_invalid_shape_400(self, client, pid):
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "力量体系", "shape": "table"})
        assert r.status_code == 400

    def test_kv_empty_result_502(self, client, pid, monkeypatch):
        monkeypatch.setattr(
            "settings.ai_router.get_ai_client_for_novel",
            self._fake_client({"名目": {"value": []}}),
        )
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "世界铁律", "shape": "kv"})
        assert r.status_code == 502
