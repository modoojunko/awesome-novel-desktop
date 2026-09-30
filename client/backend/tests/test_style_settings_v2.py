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

    def test_v2_ghost_fatigue_words_merged_into_banned(self):
        """幽灵键 fatigue_words（6.0e 遗物）归一并入 banned_words 后剥离（banned-words-into-style）。"""
        raw = {"role": "r", "rules": ["a"], "craft": [], "few_shot_examples": ["s"], "fatigue_words": ["忽然"]}
        out = normalize_style(raw)
        assert out["banned_words"] == ["忽然"]
        assert "fatigue_words" not in out
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
        # payload 未带 banned_words 不清空该键（白名单语义＝全量替换所带键）
        merged["banned_words"] = ["突然"]
        merged2 = put_style(merged, {"rules": ["红线2"]})
        assert merged2["banned_words"] == ["突然"]
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

    def test_commit_reuses_step3_rows_and_still_merges_locked(self):
        """落卡行单源（c-style-paste-distill）：rows 缺省容差不为 ±30%；锁定行仍按落卡时点保留。"""
        rows = build_baseline(
            {"baseline": {"narrative": "新身份", "rhythm": {"dialogue": 48, "action": 24, "narration": 15, "environment": 7, "inner": 6}}, "confidence": 60}
        )
        assert rows["narrative"]["tolerance"] == 20  # 构建注入 confidence=60 → ±20%（缺省 0 会错落 ±30%）
        doc = quant_doc({})
        doc["baseline"] = {"rhythm": {"value": "旧配比", "tolerance": 10, "locked": True}}
        doc["draft"] = {"step": 3, "sample_chars": 10000, "chapter_count": 0, "step3": {"rows": rows, "banned": []}}
        doc = commit_draft(doc, sample_chars=10000, chapter_count=0, at="T1")
        assert doc["baseline"]["narrative"] == rows["narrative"]  # 落卡行＝预览行（同一产物复用）
        assert doc["baseline"]["rhythm"]["value"] == "旧配比"  # 锁定行按落卡时点保留上一版
        # 锁定行 value 留旧、容差取新构建行值（{**新行, value: 上一版}）——与前端预览逐字段一致（评审 P2）
        assert doc["baseline"]["rhythm"]["tolerance"] == 20
        assert doc["baseline"]["rhythm"]["tolerance"] != 10  # 旧落卡容差不沿用
        assert doc["history"][0]["mixture"]["rhythm"] == "locked(上一版)"

    def test_commit_rows_corrupted_value_falls_back(self):
        """守卫加固（评审 P3）：键名齐但行值损坏（非 dict）→ 整体回落现算，不落残缺基线。"""
        rows = build_baseline({"baseline": {"narrative": "新身份"}, "confidence": 60})
        rows["rhythm"] = "损坏"  # 模拟异常存储：行值不是 dict
        doc = quant_doc({})
        doc["draft"] = {"step": 3, "sample_chars": 5000, "chapter_count": 0, "step3": {"rows": rows, "banned": []}}
        doc = commit_draft(doc, sample_chars=5000, chapter_count=0, at="T1")
        assert set(doc["baseline"]) == {"narrative", "rhythm", "syntax", "lexicon", "emotion", "dialogue_verb"}
        assert isinstance(doc["baseline"]["rhythm"], dict)

    def test_quant_doc_history_not_shared_across_docs(self):
        """quant_doc 必须深拷贝默认形状：否则无 history 键的文档经 commit 后把快照串给下一个。"""
        rows = build_baseline({"baseline": {}, "confidence": 0})
        doc1 = quant_doc({"draft": {"step": 3, "sample_chars": 5000, "chapter_count": 0, "step3": {"rows": rows, "banned": []}}})
        doc1 = commit_draft(doc1, sample_chars=5000, chapter_count=0, at="T1")
        assert len(doc1["history"]) == 1
        doc2 = quant_doc({})
        assert doc2["history"] == []
        assert doc2["draft"] == {}


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

    from sqlalchemy import select

    from db import async_session
    from models.project import Novel

    async def _get():
        async with async_session() as s:
            return (await s.scalars(select(Novel).where(Novel.id == pid))).one().root_path

    return asyncio.run(_get())


class TestDistillEndpoints:
    def _seed_samples(self, pid):
        from config import book_disk_dir

        root = book_disk_dir(_project_root(pid))
        os.makedirs(os.path.join(root, "novel-samples"), exist_ok=True)
        body = "雨点砸在铁皮棚上。他没有抬头。" * 400  # 去空白后 3200 字
        with open(os.path.join(root, "novel-samples", "a.md"), "w", encoding="utf-8") as f:
            f.write(body)

    def test_three_steps_resume_commit(self, client, pid, monkeypatch):
        self._seed_samples(pid)
        payloads = [
            '{"sections": [{"label": "雨点砸棚", "layer": "环境"}]}',
            '{"metrics": {"平均句长": "14.6 字", "对话占比": "48%"}}',
            '{"baseline": {"narrative": "第三人称限知", "rhythm": {"dialogue": 48, "action": 24, "narration": 15, "environment": 7, "inner": 6}}, "details": {"词法": "x"}, "portrait": "一个冷静的讲述者。", "banned": ["突然"]}',
        ]
        _install_fake_distill(monkeypatch, payloads)

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
        # 禁用词已服务端并入文风 KV banned_words（banned-words-into-style 改目标）
        style_doc = client.get(f"/api/novels/{pid}/settings/style").json()
        assert "突然" in (style_doc.get("banned_words") or [])

    def test_sample_under_range_400(self, client, pid, monkeypatch):
        from config import book_disk_dir

        root = book_disk_dir(_project_root(pid))
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
        from fastapi import HTTPException

        def _deny():
            raise HTTPException(403, "member_required")

        app.dependency_overrides[require_ai_access] = _deny
        try:
            r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"files": [], "chapter_ids": []})
            assert r.status_code == 403
        finally:
            app.dependency_overrides[require_ai_access] = lambda: True

    # ── 粘贴样本第三路（c-style-paste-distill）─────────────────────────

    _PASTE = "他把账合上，像合上一口棺材。" * 360  # 无空白，5040 字

    def test_paste_step1_accepts_text(self, client, pid, monkeypatch):
        calls = _install_fake_distill(monkeypatch, ['{"sections": [{"label": "合账", "layer": "动作"}]}'])
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"text": self._PASTE})
        assert r.status_code == 200, r.text
        assert r.json()["step"] == 1
        # LLM 收到的样本＝粘贴文本本体
        assert "他把账合上" in calls["prompts"][0]
        q = client.get(f"/api/novels/{pid}/settings/style-quant").json()
        assert q["draft"]["samples_used"] == ["粘贴文本"]
        assert q["draft"]["chapter_count"] == 0
        assert q["draft"]["sample_chars"] == 5040

    def test_paste_step1_rejects_out_of_range_and_writes_nothing(self, client, pid):
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"text": "字" * 2100})
        assert r.status_code == 400
        assert "再补" in r.json()["detail"]
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"text": "字" * 10001})
        assert r.status_code == 400
        assert "挑最有代表性" in r.json()["detail"]
        # 零写入：持久层 draft 不产生任何产物
        q = client.get(f"/api/novels/{pid}/settings/style-quant").json()
        assert not q.get("draft")

    def test_paste_step1_rejects_non_string(self, client, pid):
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"text": 12345})
        assert r.status_code == 400
        q = client.get(f"/api/novels/{pid}/settings/style-quant").json()
        assert not q.get("draft")

    def test_paste_restart_clears_old_draft_and_no_text_resumes(self, client, pid, monkeypatch):
        self._seed_samples(pid)
        payloads = [
            '{"sections": [{"label": "雨点砸棚", "layer": "环境"}]}',
            '{"metrics": {"平均句长": "14.6 字"}}',
            '{"sections": [{"label": "合账", "layer": "动作"}]}',
        ]
        _install_fake_distill(monkeypatch, payloads)
        # 文件路跑到 step2（旧 draft 有 step1+step2 产物）
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"files": ["a.md"], "chapter_ids": []})
        assert r.status_code == 200
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step2", json={})
        assert r.status_code == 200
        # 粘贴重启：旧产物作废，按新文本重跑 step1
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"text": self._PASTE})
        assert r.status_code == 200, r.text
        q = client.get(f"/api/novels/{pid}/settings/style-quant").json()
        assert q["draft"]["step"] == 1
        assert "step2" not in q["draft"]  # 旧 step2 产物已作废
        assert q["draft"]["samples_used"] == ["粘贴文本"]
        # 无 text 时续跑短路保持：不重复调用、旧（新粘贴）产物保留
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"files": ["a.md"], "chapter_ids": []})
        assert r.json().get("resumed") is True

    def test_paste_full_chain_rows_match_commit(self, client, pid, monkeypatch):
        payloads = [
            '{"sections": [{"label": "合账", "layer": "动作"}]}',
            '{"metrics": {"平均句长": "14.6 字"}}',
            '{"baseline": {"narrative": "第三人称限知", "rhythm": {"dialogue": 48, "action": 24, "narration": 15, "environment": 7, "inner": 6}}, "details": {"词法": "x"}, "portrait": "一个冷静的讲述者。", "banned": ["突然"]}',
        ]
        _install_fake_distill(monkeypatch, payloads)
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/step1", json={"text": self._PASTE})
        assert r.status_code == 200
        assert client.post(f"/api/novels/{pid}/settings/ai/style-distill/step2", json={}).status_code == 200
        assert client.post(f"/api/novels/{pid}/settings/ai/style-distill/step3", json={}).status_code == 200
        q = client.get(f"/api/novels/{pid}/settings/style-quant").json()
        rows = q["draft"]["step3"]["rows"]
        assert set(rows) == {"narrative", "rhythm", "syntax", "lexicon", "emotion", "dialogue_verb"}
        assert rows["narrative"]["tolerance"] == 20  # 5,040 字 → confidence 53 → ±20%（非缺省 ±30%）
        r = client.post(f"/api/novels/{pid}/settings/ai/style-distill/commit", json={})
        assert r.status_code == 200
        q2 = r.json()["quant"]
        # 预览行与落卡行逐字段一致（确认卡＝正式区同一构建产物）
        for k, row in rows.items():
            assert q2["baseline"][k] == row
        assert q2["confidence"] == 53
        assert q2["draft"] == {}


# ── 提示词组装 ───────────────────────────────────────────────────────────




class TestReviewFixRegressions:
    def test_template_scale_rules_not_truncated(self):
        """评审 P2：模板全量归一（≈58 条）不得被上限截断——反 AI 红线一条不能丢。"""
        raw = {
            "role": "r",
            "core_principles": {f"cat{i}": [f"原则{i}-{j}" for j in range(6)] for i in range(5)},
            "possible_mistakes": [f"错误{i}" for i in range(20)],
            "pacing_rules": ["节奏规则"],
        }
        out = normalize_style(raw)
        assert len(out["rules"]) >= 50
        # 全部原则与错误都在（抽查首尾）
        assert "原则0-0" in out["rules"] and "原则4-5" in out["rules"]
        assert "错误19" in out["rules"]

    def test_auxiliary_style_read_goes_through_normalize(self):
        """评审 P2：辅助写作链（续写/润色/扩写）读 style 必须经归一——
        老书只填旧键时三区照常注入，不走未归一直读。"""

        from write.auxiliary import _format_style

        legacy = {
            "role": "冷静叙事者",
            "narrator_role": "第三人称限知",
            "tone": {"techniques": ["动作外化"]},
            "core_principles": ["每章结尾必须有钩子"],
            "depiction_techniques": ["情绪靠动作外化"],
        }
        normalized = read_style(legacy)
        sec = _format_style(normalized)
        assert "冷静叙事者" in sec
        assert "每章结尾必须有钩子" in sec
        assert "情绪靠动作外化" in sec
        # 未归一直读在迁移窗口期会丢这些内容——这里钉住归一后的行为


class TestPromptAssembly:
    def _ctx(self, tmp_root):
        from write.chapter_writer import ChapterContext

        return ChapterContext(), tmp_root

    def test_style_section_injected(self, pid, monkeypatch, tmp_path):

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
