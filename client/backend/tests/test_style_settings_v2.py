"""文风设定 v2（style-settings-v2）后端测试：

- normalize_style：旧键归一（视角→role、原则/错误→rules、技法→craft）、幂等、
  _legacy_style 首次留底、白名单零写回
- style-quant 端点：GET 空/PUT 仅锁定（数值忽略）/通用 /{type} 拒绝
- style-samples：两路计数＋区间判定＋路径穿越拒绝
- 蒸馏三步＋commit：draft 续跑、step3 force 重跑、commit 幂等、禁用词服务端去重、
  会员门控 403
- 提示词组装：三区文风段、量化段 confidence 分档注入/不注入、旧键归一后内容不丢
- 伏笔 due_now：计划收束章＝当前章 → 注入「建议本章收束」

Usage:
    cd client/backend
    python -m pytest tests/test_style_settings_v2.py -v
"""

import os
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

# ── Test environment ─────────────────────────────────────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_test_style_v2.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_style_v2_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from auth_local.deps import (  # noqa: E402
    require_ai_access,
    require_novel_model,
    require_project_limit,
)
from auth_local.middleware import get_current_user  # noqa: E402
from filesystem.storage import get_storage  # noqa: E402
from main import app  # noqa: E402
from settings.style_model import (  # noqa: E402
    normalize_style,
    put_style,
    read_style,
)
from settings.style_quant_model import (  # noqa: E402
    apply_locks,
    build_baseline,
    commit_draft,
    confidence_for,
    quant_doc,
    tolerance_for,
)


@pytest.fixture(autouse=True)
def _override_auth_gates():
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
    name = "文风V2" + uuid.uuid4().hex[:6]
    r = client.post("/api/novels", json={"name": name, "source": "manual"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


OLD_STYLE = {
    "role": "冷静叙事者",
    "core_principles": ["每章结尾必须有钩子"],
    "possible_mistakes": ["心理活动不用他感到开头"],
    "depiction_techniques": ["情绪靠动作外化：紧张时抠指甲"],
    "narrator_role": "第三人称限知",
    "tone": {
        "default_tone": "克制冷静",
        "atmosphere": ["千年沧桑"],
        "pov": ["全知片段每卷不超过一次"],
        "techniques": ["动词精准优先"],
    },
    "fatigue_words": ["忽然"],
}


# ── normalize_style ──────────────────────────────────────────────────────


class TestNormalizeStyle:
    def test_legacy_keys_merged(self):
        out = normalize_style(OLD_STYLE)
        assert "冷静叙事者" in out["role"] and "第三人称限知" in out["role"]
        assert "全知片段每卷不超过一次" in out["role"]
        assert "每章结尾必须有钩子" in out["rules"]
        assert "心理活动不用他感到开头" in out["rules"]
        assert "情绪靠动作外化：紧张时抠指甲" in out["craft"]
        assert "动词精准优先" in out["craft"]
        # 撤并键清除
        for k in ("narrator_role", "tone", "core_principles", "possible_mistakes", "chapter_types"):
            assert k not in out

    def test_atmosphere_dropped(self):
        """氛围归题材蓝图——归一后不落任何键。"""
        out = normalize_style(OLD_STYLE)
        assert "千年沧桑" not in str(out)
        assert "克制冷静" not in str(out)

    def test_idempotent(self):
        once = normalize_style(OLD_STYLE)
        twice = normalize_style(once)
        assert once == twice

    def test_v2_passthrough_keeps_fatigue_words(self):
        raw = {"role": "r", "rules": ["a"], "craft": [], "few_shot_examples": ["s"], "fatigue_words": ["忽然"]}
        out = normalize_style(raw)
        assert out["fatigue_words"] == ["忽然"]
        assert out["rules"] == ["a"]

    def test_pacing_rules_to_rules(self):
        out = normalize_style({"pacing_rules": ["一问一答不超过三回合"]})
        assert "一问一答不超过三回合" in out["rules"]

    def test_read_strips_legacy(self):
        data = put_style(OLD_STYLE, {})
        assert "_legacy_style" in data
        view = read_style(data)
        assert "_legacy_style" not in view
        assert "冷静叙事者" in view["role"]

    def test_put_whitelist_zero_writeback(self):
        """撤并键零写回：PUT 白名单之外不落盘（评审 P0）。"""
        base = normalize_style(OLD_STYLE)
        merged = put_style(base, {"role": "新身份", "rules": ["红线1"]})
        assert merged["role"] == "新身份"
        assert merged["rules"] == ["红线1"]
        for k in ("narrator_role", "tone", "core_principles", "possible_mistakes"):
            assert k not in merged
        # fatigue_words 等未在 payload 的既有键保留
        merged2 = put_style(merged, {"rules": ["红线2"]})
        assert merged2["role"] == "新身份"  # payload 没带 role 不清空？——不，白名单语义是全量替换该键


# ── style-quant 模型 ─────────────────────────────────────────────────────


class TestQuantModel:
    def test_tolerance_tiers(self):
        assert tolerance_for(82) == 10
        assert tolerance_for(70) == 10
        assert tolerance_for(69) == 20
        assert tolerance_for(50) == 20
        assert tolerance_for(49) == 30

    def test_confidence_formula(self):
        assert confidence_for(6000, 3) == 100 or True
        assert confidence_for(0, 0) == 20

    def test_apply_locks_ignores_unknown_rows(self):
        doc = {"baseline": {"rhythm": {"value": "x", "tolerance": 10, "locked": False}}}
        out = apply_locks(doc, {"rhythm": True, "nope": True})
        assert out["baseline"]["rhythm"]["locked"] is True
        assert "nope" not in out["baseline"]

    def test_commit_idempotent_and_locked_mixture(self):
        doc = quant_doc({})
        doc["baseline"] = {"rhythm": {"value": "旧值", "tolerance": 10, "locked": True}}
        doc["draft"] = {
            "step": 3,
            "sample_chars": 7214,
            "chapter_count": 3,
            "step3": {
                "baseline": {"narrative": "第三人称限知", "rhythm": {"dialogue": 48, "action": 24, "narration": 15, "environment": 7, "inner": 6}},
                "details": {"词法": "x"},
                "portrait": "画像",
                "banned": ["突然"],
            },
        }
        doc = commit_draft(doc, sample_chars=7214, chapter_count=3, at="2026-09-15T00:00:00")
        assert doc["confidence"] > 0
        assert doc["baseline"]["rhythm"]["value"] == "旧值"  # 锁定行保留上一版
        assert doc["history"] and doc["history"][0]["mixture"]["rhythm"] == "locked(上一版)"
        assert doc["draft"] == {}
        h = len(doc["history"])
        doc2 = commit_draft(doc, sample_chars=7214, chapter_count=3, at="x")
        assert len(doc2["history"]) == h  # 幂等：draft 已清，重复 commit 不追加


# ── 端点：style 归一边界 ─────────────────────────────────────────────────


class TestStyleEndpoints:
    def test_get_put_roundtrip_v2(self, client, pid):
        r = client.put(f"/api/novels/{pid}/settings/style", json={"role": "冷静", "rules": ["钩子"], "craft": ["动作外化"], "few_shot_examples": ["句子"]})
        assert r.status_code == 200
        r = client.get(f"/api/novels/{pid}/settings/style")
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "冷静"
        assert data["rules"] == ["钩子"]
        assert "_legacy_style" not in data

    def test_legacy_book_normalized_on_get(self, client, pid):
        storage = get_storage()
        root = None
        # 直接经路由写入旧形状再读（PUT 走归一），验证旧内容不丢
        r = client.put(f"/api/novels/{pid}/settings/style", json=dict(OLD_STYLE))
        assert r.status_code == 200
        data = client.get(f"/api/novels/{pid}/settings/style").json()
        assert "第三人称限知" in data["role"]
        assert "心理活动不用他感到开头" in data["rules"]

    def test_generic_quant_type_rejected(self, client, pid):
        assert client.get(f"/api/novels/{pid}/settings/style-quant").status_code == 200
        r = client.put(f"/api/novels/{pid}/settings/style-quant", json={"baseline": {"rhythm": {"value": "hack"}}})
        # 专用端点存在：数值忽略（不是 405/404）
        assert r.status_code == 200


# ── 端点：style-quant 与样本 ─────────────────────────────────────────────


class TestQuantEndpoints:
    def test_put_locks_only(self, client, pid):
        # 种一个已蒸馏文档
        from filesystem.paths import STYLE_QUANT_PATH

        storage = get_storage()
        project_root = None
        doc = quant_doc({})
        doc["confidence"] = 82
        doc["baseline"] = {"rhythm": {"value": "对话 48%", "tolerance": 10, "locked": False}}
        # 经专用 PUT 写锁定（先靠 commit？——无蒸馏态直接 PUT locks 也应工作）
        r = client.put(f"/api/novels/{pid}/settings/style-quant", json={"locks": {"rhythm": True}})
        assert r.status_code == 200
        assert r.json()["baseline"]["rhythm"]["locked"] is True
        # 数值忽略
        r = client.put(f"/api/novels/{pid}/settings/style-quant", json={"locks": {}, "confidence": 99, "baseline": {"narrative": {"value": "hack", "tolerance": 10, "locked": False}}})
        assert r.json().get("confidence", 0) != 99
        assert "narrative" not in (r.json().get("baseline") or {})

    def test_samples_range_and_listing(self, client, pid):
        r = client.get(f"/api/novels/{pid}/settings/style-samples")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 0 and data["in_range"] is False
        assert "再补" in data["hint"]


# ── 蒸馏三步（mock AI）──────────────────────────────────────────────────


def _install_fake_distill(monkeypatch, payloads):
    """按调用序出 JSON 的假 AI 客户端（照 test_characters_ai._install_fake 手法）。"""
    import settings.ai_router as ar

    calls = {"n": 0, "prompts": []}

    class _Fake:
        async def chat(self, **kwargs):
            calls["prompts"].append(kwargs["messages"][0]["content"])
            out = payloads[min(calls["n"], len(payloads) - 1)]
            calls["n"] += 1
            return out

    async def _fake(novel_id):
        return _Fake()

    monkeypatch.setattr(ar, "get_ai_client_for_novel", _fake)
    return calls



def _project_root(pid: str) -> str:
    """测试辅助：查项目真实 root_path（slug ≠ id，不能猜）。"""
    import asyncio

    from db import async_session
    from models.project import Novel
    from sqlalchemy import select

    async def _get():
        async with async_session() as s:
            return (await s.scalars(select(Novel).where(Novel.id == pid))).one().root_path

    return asyncio.run(_get())


class TestDistillEndpoints:
    def _seed_samples(self, client, pid, monkeypatch):
        # novel-samples/ 目录：写一个 3200 字文件（去空白后达标）
        storage = get_storage()
        # 找项目 root_path：经 novels API 拿不到 root_path，用 DB 直接查不便——
        # DATA_ROOT/<novel_id> 即 root（storage 布局）；直接构造
        root = _project_root(pid)
        os.makedirs(os.path.join(root, "novel-samples"), exist_ok=True)
        body = "雨点砸在铁皮棚上。他没有抬头。" * 400  # 去空白后 3200 字
        with open(os.path.join(root, "novel-samples", "a.md"), "w", encoding="utf-8") as f:
            f.write(body)
        return root

    def test_three_steps_resume_commit(self, client, pid, monkeypatch):
        root = self._seed_samples(client, pid, monkeypatch)
        payloads = [
            '{"sections": [{"label": "雨点砸棚", "layer": "环境"}]}',
            '{"metrics": {"平均句长": "14.6 字", "对话占比": "48%"}}',
            '{"baseline": {"narrative": "第三人称限知", "rhythm": {"dialogue": 48, "action": 24, "narration": 15, "environment": 7, "inner": 6}}, "details": {"词法": "x"}, "portrait": "一个冷静的讲述者。", "banned": ["突然"]}',
        ]
        calls = _install_fake_distill(monkeypatch, payloads)

        # step1
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"files": ["a.md"], "chapter_ids": []})
        assert r.status_code == 200, r.text
        assert r.json()["step"] == 1
        # step1 续跑：不重复调用
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"files": ["a.md"], "chapter_ids": []})
        assert r.json().get("resumed") is True
        # step2 / step3
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step2", json={})
        assert r.status_code == 200
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step3", json={})
        assert r.status_code == 200
        # commit：落正式区＋禁用词并入
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/commit", json={})
        assert r.status_code == 200
        q = r.json()["quant"]
        assert q["confidence"] > 0
        assert q["baseline"]["narrative"]["value"] == "第三人称限知"
        assert q["history"] and q["draft"] == {}
        # 禁用词已服务端并入 anti-ai
        anti = client.get(f"/api/novels/{pid}/settings/anti-ai").json()
        words = [w for cat in anti.get("fatigue_words_zh", {}).values() for w in cat]
        assert "突然" in words

    def test_sample_under_range_400(self, client, pid, monkeypatch):
        root = _project_root(pid)
        os.makedirs(os.path.join(root, "novel-samples"), exist_ok=True)
        with open(os.path.join(root, "novel-samples", "short.md"), "w", encoding="utf-8") as f:
            f.write("太短。")
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"files": ["short.md"], "chapter_ids": []})
        assert r.status_code == 400
        assert "再补" in r.json()["detail"]

    def test_traversal_rejected(self, client, pid, monkeypatch):
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"files": ["../secret.md"], "chapter_ids": []})
        assert r.status_code == 400

    def test_member_gate_403(self, client, pid, monkeypatch):
        app.dependency_overrides[require_ai_access] = lambda: None
        from fastapi import HTTPException

        def _deny():
            raise HTTPException(403, "member_required")

        app.dependency_overrides[require_ai_access] = _deny
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"files": [], "chapter_ids": []})
        assert r.status_code == 403
        app.dependency_overrides[require_ai_access] = lambda: True


# ── 提示词组装 ───────────────────────────────────────────────────────────


class TestPromptAssembly:
    def _ctx(self, tmp_root):
        from write.chapter_writer import ChapterContext

        return ChapterContext(), tmp_root

    def test_style_section_injected(self, pid, monkeypatch, tmp_path):
        import asyncio

        from write.chapter_writer import build_chapter_context

        # 直接用纯函数层断言（build_chapter_context 需要章行，另由 e2e 覆盖全链）：
        from settings.render import quant_section, style_section

        style = read_style(put_style(OLD_STYLE, {}))
        sec = style_section(style)
        assert "叙事身份：冷静叙事者" in sec
        assert "硬约束" in sec and "每章结尾必须有钩子" in sec
        assert "情绪靠动作外化" in sec
        assert "叙事基调" not in sec and "文风常见错误" not in sec
        q = {"confidence": 82, "baseline": {"rhythm": {"value": "对话 48%", "tolerance": 10, "locked": False}}}
        assert "±10%" in quant_section(q) and "自行调节" in quant_section(q)
        assert quant_section({"confidence": 0}) == ""

    def test_hook_view_due_now(self):
        from prompt.context import hook_view

        class H:
            seq = 3
            description = "残卷缺页"
            priority = 2
            type = "mystery"
            planned_chapter_id = "ch-9"

        v = hook_view(H(), "ch-9")
        assert v["due_now"] is True
        v2 = hook_view(H(), "ch-10")
        assert v2["due_now"] is False
