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
    V2_EMPTY,
    lore_apply_entries,
    normalize_world,
    put_world_merged,
    read_world,
    render_red_lines,
    render_world_block,
    world_is_filled,
    world_summary_text,
)


@pytest.fixture(autouse=True)
def _override_auth_gates():
    """每用例前重设门控覆盖，用后自清（不依赖其他模块的 teardown 擦场）。"""
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1"}
    app.dependency_overrides[require_ai_access] = lambda: True
    app.dependency_overrides[require_novel_model] = lambda: True
    app.dependency_overrides[require_project_limit] = lambda: True
    yield
    for key in (get_current_user, require_ai_access, require_novel_model, require_project_limit):
        app.dependency_overrides.pop(key, None)


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

    def test_extra_duplicate_key_allowed(self, client, pid):
        """history/extra 名目不强制唯一（§2.1：幂等靠 (key, origin)）。"""
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "extra": [
                {"key": "迷雾森林", "value": "a"},
                {"key": "迷雾森林", "value": "b"},
            ],
        })
        assert r.status_code == 200, r.text

    def test_constraints_duplicate_key_400(self, client, pid):
        """世界铁律是硬边界，同 key 必须唯一。"""
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "constraints": [
                {"key": "不可推翻的事", "value": "a"},
                {"key": "不可推翻的事", "value": "b"},
            ],
        })
        assert r.status_code == 400
        assert "不可推翻的事" in r.json()["detail"]

    def test_faction_empty_name_with_note_ok(self, client, pid):
        """迁移映射：politics.factions → {name:"", note:原文}，无名有注合法。"""
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "factions": [{"name": "", "note": "丹阁与青梧宗世仇"}],
        })
        assert r.status_code == 200, r.text
        r2 = client.put(f"/api/novels/{pid}/settings/world", json={
            "factions": [{"name": "", "note": "  "}],
        })
        assert r2.status_code == 400

    def test_faction_duplicate_named_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "factions": [
                {"name": "丹阁", "note": "a"},
                {"name": "丹阁", "note": "b"},
            ],
        })
        assert r.status_code == 400

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
        # 与 archive 产出同形：建议带 canonical origin（幂等键）
        assert data["suggestions"] == [
            {"key": "血衣楼", "value": "第12章登场的新势力", "set": "extra", "origin": "vol-1-ch-12"},
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


# ── 评审回归补充：上下文 await / 迁移往返 / 幂等键 / 模板 v2 ──────────────


class TestReviewRegression:
    """三路评审（PM/后端/提示词）实锤问题的回归钉。"""

    @pytest.fixture
    def client(self):
        with TestClient(app) as c:
            yield c

    def test_template_seed_is_v2_shape(self):
        """建书骨架模板必须是 v2 形状——否则所有新书被当 legacy 嵌入 _legacy。"""
        import pathlib

        tpl = pathlib.Path(__file__).resolve().parents[1] / "reference" / "world-setting.yaml.template"
        text = tpl.read_text(encoding="utf-8")
        assert "geography" not in text and "politics" not in text
        assert "no_power" in text and "constraints" in text

    def test_world_summary_keeps_red_lines_whole(self):
        """AI 输入侧摘要：预算只截世界块，铁律逐条完整（D4/D5 口径）。"""
        long_extra = [{"key": f"条目{i}", "value": "字" * 180} for i in range(8)]
        raw = {"constraints": [{"key": "不可推翻的事", "value": "死者不可复生"}], "extra": long_extra}
        summary = world_summary_text(raw, 300)
        assert "世界铁律·不可推翻的事：死者不可复生" in summary

    def test_render_block_entry_granular_packing(self):
        """D5：条目为最小渲染单元——放不下的大条目只跳自己，同段小条目存活。"""
        raw = {"history": [
            {"key": "小一", "value": "短"},
            {"key": "大条甲", "value": "字" * 200},
            {"key": "大条乙", "value": "字" * 200},
            {"key": "大条丙", "value": "字" * 200},
            {"key": "小二", "value": "短"},
        ]}
        block = render_world_block(raw)
        assert "小一" in block and "小二" in block, "小条目不被大条目拖累"
        assert block.count("字" * 200) == 2, "只装得下两条大条目"
        assert "另有 1 条世界细节从略" in block
        # 无半截条目
        for line in block.splitlines():
            if line.startswith("  - "):
                assert len(line) <= 230

    def test_v1_migration_get_put_roundtrip_200(self, client, pid):
        """老书升级链：v1 十字段（超长 climate）→ GET → 整包 PUT 必须 200 可保存。"""

        raw_v1 = {
            "geography": {"scenes": "南境修仙界", "climate": "气" * 300, "limits": "灵气南浓北稀"},
            "politics": {"rule": "宗门议会制", "factions": "丹阁与青梧宗世仇", "social": "修士为尊"},
            "rules": {"world": "灵力体系", "personal": "代价是寿数", "society": "凡人不知修士"},
        }
        # 直接写存储（模拟存量旧书），再走 GET → PUT 往返
        from main import app  # noqa: F401

        # 经 API 写入 v1 形状（兼容旧客户端路径）
        r = client.put(f"/api/novels/{pid}/settings/world", json=raw_v1)
        assert r.status_code == 200, r.text
        got = client.get(f"/api/novels/{pid}/settings/world").json()
        assert got["extra"], "迁移产物应含 extra 条目"
        assert all(len(e["value"]) <= 200 for e in got["extra"]), "超限截断加省略号且 ≤VALUE_MAX"
        assert any(e["value"].endswith("…") for e in got["extra"]), "省略号必须落地"
        # GET → PUT 往返（老书首次保存不再 400）
        r2 = client.put(f"/api/novels/{pid}/settings/world", json=got)
        assert r2.status_code == 200, r2.text
        # 无名有注势力行可保存（politics.factions 映射）
        got2 = client.get(f"/api/novels/{pid}/settings/world").json()
        assert any(f["name"] == "" and f["note"] for f in got2["factions"]) or got2["factions"] == []

    def test_lore_apply_factions_dedup_by_name(self):
        """factions 幂等键=name（§2.1）：不同 origin 同名 → 更新 note 不新增行。"""
        v2 = dict(V2_EMPTY)
        out = lore_apply_entries(v2, [
            {"key": "丹阁", "value": "要为残卷讨说法", "set": "factions", "origin": "vol-1-ch-1"},
        ])
        out = lore_apply_entries(out, [
            {"key": "丹阁", "value": "改口：要吞并青梧宗", "set": "factions", "origin": "vol-1-ch-9"},
        ])
        assert len(out["factions"]) == 1
        assert out["factions"][0] == {"name": "丹阁", "note": "改口：要吞并青梧宗"}

    def test_lore_apply_constraints_dedup_by_key(self):
        """constraints 幂等键=key：铁律同 key 不同 origin 原地更新。"""
        v2 = dict(V2_EMPTY)
        out = lore_apply_entries(v2, [
            {"key": "不可推翻的事", "value": "死者不可复生", "set": "constraints", "origin": "vol-1-ch-1"},
        ])
        out = lore_apply_entries(out, [
            {"key": "不可推翻的事", "value": "死者不可复生，灵根不可再造", "set": "constraints", "origin": "vol-1-ch-9"},
        ])
        assert len(out["constraints"]) == 1
        assert out["constraints"][0]["value"] == "死者不可复生，灵根不可再造"

    def test_lore_apply_batch_limit_400(self, client, pid):
        r = client.post(f"/api/novels/{pid}/settings/world/lore-apply", json={
            "entries": [{"key": f"k{i}", "value": "v", "set": "extra"} for i in range(21)],
        })
        assert r.status_code == 400

    def test_world_is_filled_counts_factions(self):
        """只填势力的书也能确认世界（§2.4 value 或 name）。"""
        assert world_is_filled({"factions": [{"name": "丹阁", "note": ""}]})
        assert world_is_filled({"factions": [{"name": "", "note": "旧势力长文"}]})

    def test_draft_no_power_power_topic_400(self, client, pid, monkeypatch):
        """现实向书拒绝起草力量内容（写边界与面板收起口径一致）。"""
        client.put(f"/api/novels/{pid}/settings/world", json={"no_power": True})
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "力量体系", "shape": "text"})
        assert r.status_code == 400
        assert "现实向" in r.json()["detail"]

    def test_draft_prompt_carries_world_context(self, client, pid, monkeypatch):
        """起草 prompt 必须带已有世界设定（防 await 丢失回归）。"""
        import json as _json

        client.put(f"/api/novels/{pid}/settings/world", json={
            "stage": "云梁界修仙世界",
        })
        captured: dict = {}

        class _Fake:
            model = "fake"

            async def chat(self, *a, **k):
                captured["prompt"] = k.get("messages", [{}])[0].get("content", "")
                return _json.dumps({"value": [{"name": "丹阁", "note": "要与青梧宗争锋"}]})

        async def _fake_get_client(novel_id=None):
            return _Fake()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _fake_get_client)
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "势力", "shape": "faction"})
        assert r.status_code == 200, r.text
        assert "云梁界修仙世界" in captured["prompt"], "已有世界设定必须进 prompt"
        assert "「势力」" in captured["prompt"], "topic 须为中文要素名"

    def test_check_both_missing_skips_ai(self, client, pid, monkeypatch):
        """简介+题材全空 → 不烧 AI 调用，全部置 miss + degraded_reasons。"""
        called = {"n": 0}

        class _Boom:
            async def chat(self, *a, **k):
                called["n"] += 1
                raise AssertionError("不应调用 AI")

        async def _fake_get_client(novel_id=None):
            return _Boom()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _fake_get_client)
        r = client.post(f"/api/novels/{pid}/settings/ai/world/check", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert called["n"] == 0
        assert data["degraded"] is True
        assert set(data["degraded_reasons"]) == {"简介未填", "题材未确认"}
        assert all(i["status"] == "miss" for i in data["items"])

    def test_check_name_normalization_matches(self, client, pid, monkeypatch):
        """模型把「简介 × 世界」写岔（半角 x）也能命中官方项名。"""
        import json as _json

        client.put(f"/api/novels/{pid}/story", json={"synopsis": "测试前提"})
        client.put(f"/api/novels/{pid}/settings/genre", json={"theme": "玄幻"})

        class _Fake:
            model = "fake"

            async def chat(self, *a, **k):
                return _json.dumps({"items": [
                    {"name": "简介x世界", "status": "ok", "note": "对得上"},
                    {"name": " 力量与上限 ", "status": "warn", "note": "上限模糊"},
                ], "verdict": "x"})

        async def _fake_get_client(novel_id=None):
            return _Fake()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _fake_get_client)
        r = client.post(f"/api/novels/{pid}/settings/ai/world/check", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        by_name = {i["name"]: i for i in data["items"]}
        assert by_name["简介 × 世界"]["status"] == "ok"
        assert by_name["力量与上限"]["status"] == "warn"


# ── 测试评审补测：origin 往返 / 现实向项集 / 降级矩阵 / 满员边界 ──────────


class TestTestReviewAdds:
    @pytest.fixture
    def client(self):
        with TestClient(app) as c:
            yield c

    def test_lore_origin_survives_client_roundtrip(self, client, pid):
        """lore 入账 → GET → 客户端形状整包 PUT → GET 仍有 origin（幂等键不被手存抹掉）。"""
        r = client.post(f"/api/novels/{pid}/settings/world/lore-apply", json={
            "entries": [{"key": "血衣楼", "value": "第12章登场", "set": "extra", "origin": "vol-1-ch-12"}],
        })
        assert r.status_code == 200, r.text
        got = client.get(f"/api/novels/{pid}/settings/world").json()
        assert got["extra"][0]["origin"] == "vol-1-ch-12"
        # 客户端整包回写（normalizeWorld 保留 origin）
        r2 = client.put(f"/api/novels/{pid}/settings/world", json=got)
        assert r2.status_code == 200, r2.text
        got2 = client.get(f"/api/novels/{pid}/settings/world").json()
        assert got2["extra"][0].get("origin") == "vol-1-ch-12"
        # 同 origin 重放不重复追加（幂等键仍有效）
        r3 = client.post(f"/api/novels/{pid}/settings/world/lore-apply", json={
            "entries": [{"key": "血衣楼", "value": "改写", "set": "extra", "origin": "vol-1-ch-12"}],
        })
        assert r3.status_code == 200
        got3 = client.get(f"/api/novels/{pid}/settings/world").json()
        assert len(got3["extra"]) == 1
        assert got3["extra"][0]["value"] == "改写"

    def test_check_no_power_swaps_to_real_items(self, client, pid, monkeypatch):
        """现实向书体检返回 CHECK_ITEMS_REAL 项集（无力量两把尺，有现实规则完备）。"""
        import json as _json

        client.put(f"/api/novels/{pid}/story", json={"synopsis": "都市言情"})
        client.put(f"/api/novels/{pid}/settings/world", json={"no_power": True})

        class _Fake:
            model = "fake"

            async def chat(self, *a, **k):
                prompt = k.get("messages", [{}])[0].get("content", "")
                assert "现实向" in prompt, "现实向语境必须进 prompt"
                names = ["简介 × 世界", "题材 × 世界", "铁律 × 简介", "势力立场", "历史自洽", "现实规则完备"]
                return _json.dumps({"items": [{"name": n, "status": "ok", "note": "ok"} for n in names],
                                    "verdict": "齐"})

        async def _fake_get_client(novel_id=None):
            return _Fake()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _fake_get_client)
        r = client.post(f"/api/novels/{pid}/settings/ai/world/check", json={})
        assert r.status_code == 200, r.text
        names = [i["name"] for i in r.json()["items"]]
        assert "现实规则完备" in names
        assert "力量与上限" not in names and "代价与边界" not in names

    def test_check_theme_missing_degrades_only_theme_rows(self, client, pid, monkeypatch):
        """题材缺失：题材行置 miss，其余行保留 AI 结论（降级≠全 miss）。"""
        import json as _json

        client.put(f"/api/novels/{pid}/story", json={"synopsis": "测试前提"})

        class _Fake:
            model = "fake"

            async def chat(self, *a, **k):
                names = ["简介 × 世界", "题材 × 世界", "力量与上限", "代价与边界", "铁律 × 简介", "势力立场", "历史自洽"]
                return _json.dumps({"items": [{"name": n, "status": "ok", "note": "好"} for n in names],
                                    "verdict": "行"})

        async def _fake_get_client(novel_id=None):
            return _Fake()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _fake_get_client)
        r = client.post(f"/api/novels/{pid}/settings/ai/world/check", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["degraded"] is True
        by_name = {i["name"]: i for i in data["items"]}
        assert by_name["题材 × 世界"]["status"] == "miss"
        assert by_name["力量与上限"]["status"] == "ok", "非题材行保留 AI 结论"
        assert "题材未确认" in data["degraded_reasons"]

    def test_faction_shape_caps_at_six(self, client, pid, monkeypatch):
        import json as _json

        class _Fake:
            model = "fake"

            async def chat(self, *a, **k):
                return _json.dumps({"value": [
                    {"name": f"势力{i}", "note": "注"} for i in range(9)
                ]})

        async def _fake_get_client(novel_id=None):
            return _Fake()

        monkeypatch.setattr("settings.ai_router.get_ai_client_for_novel", _fake_get_client)
        r = client.post(f"/api/novels/{pid}/settings/ai/world/draft",
                        json={"topic": "势力", "shape": "faction"})
        assert r.status_code == 200, r.text
        assert len(r.json()["value"]) == 6

    def test_history_extra_count_limits_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "history": [{"key": f"事{i}", "value": "v"} for i in range(101)],
        })
        assert r.status_code == 400
        r2 = client.put(f"/api/novels/{pid}/settings/world", json={
            "extra": [{"key": f"名{i}", "value": "v"} for i in range(51)],
        })
        assert r2.status_code == 400

    def test_entry_key_over_limit_400(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/world", json={
            "constraints": [{"key": "钥" * 21, "value": "v"}],
        })
        assert r.status_code == 400

    def test_status_world_empty_confirm_400(self, client, pid):
        """空世界确认被拦（确认需有内容）。"""
        r = client.put(f"/api/novels/{pid}/settings/status/world")
        assert r.status_code == 400
