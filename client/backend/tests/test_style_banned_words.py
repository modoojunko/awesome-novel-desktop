"""banned-words-into-style：禁用词收编文风的迁移/单源/竞态缓解测试。

覆盖 spec（specs/style-banned-words）核心场景：
- 存量 anti-ai KV 惰性迁移（齐全/幂等/删词不回灌/原键保留可回滚/新书无感）
- 双源去重（幽灵键 fatigue_words ＋ anti-ai 同批）
- 注入与体检单源（未进设定页直接体检不假通过）
- append_banned_words（NFKC 去重/满表静默丢弃/返回新增数）
- put_style 两键读写回路与 tic dict 专用归一
"""


import pytest

from filesystem.storage import get_storage
from settings.style_model import (
    BANNED_MIGRATED_KEY,
    append_banned_words,
    normalize_style,
    put_style,
    read_style,
    read_style_migrated,
)


def _run_async(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


def _tmp_root() -> str:
    import tempfile

    return tempfile.mkdtemp(prefix="test_banned_words_")


ANTI_AI_DOC = {
    "fatigue_words_zh": {
        "summary_narrative": ["本章讲述了", "与此同时"],
        "academic_tone": ["综上所述"],
    },
    "structural_tic_patterns": [
        {
            "pattern": "不是[^，。]{1,10}(而是|是)",
            "name": "不是而是句式",
            "threshold": 3,
            "severity": "high",
            "description": "d1",
        },
        {
            "pattern": "一边.{1,10}一边",
            "name": "一边一边句式",
            "threshold": 2,
            "severity": "medium",
            "description": "d2",
        },
    ],
}


# ── 迁移 ─────────────────────────────────────────────────────────────────


class TestMigration:
    def test_migrates_words_and_tics(self):
        root = _tmp_root()
        s = get_storage()
        _run_async(s.write_yaml(root, "settings/anti-ai.yaml", ANTI_AI_DOC))
        doc = _run_async(read_style_migrated(root))
        assert "本章讲述了" in doc["banned_words"]
        assert "综上所述" in doc["banned_words"]
        assert {t["pattern"] for t in doc["tic_patterns"]} >= {
            "不是[^，。]{1,10}(而是|是)",
            "一边.{1,10}一边",
        }
        # anti-ai 原键原样保留（回滚安全）
        assert _run_async(s.read_yaml(root, "settings/anti-ai.yaml")) == ANTI_AI_DOC

    def test_idempotent_and_delete_not_readded(self):
        root = _tmp_root()
        s = get_storage()
        _run_async(s.write_yaml(root, "settings/anti-ai.yaml", ANTI_AI_DOC))
        doc1 = _run_async(read_style_migrated(root))
        n_words = len(doc1["banned_words"])
        assert doc1.get(BANNED_MIGRATED_KEY) is None  # 标记 GET 剥离
        # 作者删词后重读：标记拦截重迁，不回灌
        raw = _run_async(s.read_yaml(root, "settings/writing-style.yaml"))
        raw["banned_words"] = [w for w in raw["banned_words"] if w != "综上所述"]
        _run_async(s.write_yaml(root, "settings/writing-style.yaml", raw))
        doc2 = _run_async(read_style_migrated(root))
        assert "综上所述" not in doc2["banned_words"]
        assert len(doc2["banned_words"]) == n_words - 1

    def test_double_source_dedupe(self):
        """幽灵键 fatigue_words ＋ anti-ai 同源词去重。"""
        root = _tmp_root()
        s = get_storage()
        _run_async(
            s.write_yaml(
                root,
                "settings/writing-style.yaml",
                {"role": "r", "fatigue_words": ["与此同时", "忽然"]},
            )
        )
        _run_async(s.write_yaml(root, "settings/anti-ai.yaml", ANTI_AI_DOC))
        doc = _run_async(read_style_migrated(root))
        assert doc["banned_words"].count("与此同时") == 1
        assert "忽然" in doc["banned_words"]

    def test_new_book_noop(self):
        """新书（无 anti-ai 行）：迁移只落标记，banned_words 不被凭空造出。"""
        root = _tmp_root()
        s = get_storage()
        _run_async(
            s.write_yaml(root, "settings/writing-style.yaml", {"role": "r", "banned_words": []})
        )
        doc = _run_async(read_style_migrated(root))
        assert doc["banned_words"] == []
        assert "fatigue_words" not in doc

    def test_nfkc_fullwidth_dedupe(self):
        """半/全角（NFKC）＋大小写归一去重——兑现 style-settings-v2 承诺。

        去重按归一键，词表保留首见原文（"OK" 先入即保留原大写）。"""
        out = normalize_style({"banned_words": ["OK", "ｏｋ", "突然", "突 然 "]})
        assert "ｏｋ" not in out["banned_words"]  # 全角折叠进 "OK" 的归一键
        assert "OK" in out["banned_words"]
        assert out["banned_words"].count("突然") == 1


# ── 单源消费 ─────────────────────────────────────────────────────────────


class TestSingleSourceConsumers:
    def test_quality_hits_migrated_word_without_panel(self):
        """未进设定页直接体检：统一读路径先迁移，anti-ai 词照常命中（不假通过）。"""
        from write.quality import run_quality_checks

        root = _tmp_root()
        _run_async(get_storage().write_yaml(root, "settings/anti-ai.yaml", ANTI_AI_DOC))
        results = _run_async(run_quality_checks(root, "他心想：综上所述，就这样吧。"))
        assert "综上所述" in results["checks"]["fatigue_words"]["hits"]
        assert results["checks"]["fatigue_words"]["passed"] is False

    def test_quality_tic_regex_and_threshold(self):
        from write.quality import run_quality_checks

        root = _tmp_root()
        _run_async(get_storage().write_yaml(root, "settings/anti-ai.yaml", ANTI_AI_DOC))
        # 模式不是[^，。]{1,10}(而是|是)：匹配串内不能有逗号句号；4 次超阈值 3
        text = "不是他怕而是他在算。不是你说而是我说。不是这而是那。不是天而是地。"
        results = _run_async(run_quality_checks(root, text))
        tics = results["checks"]["structural_tic_patterns"]
        assert tics["hits"].get("不是而是句式") == 4
        assert tics["over_threshold"].get("不是而是句式") == 4


# ── append_banned_words（蒸馏改目标）────────────────────────────────────


class TestAppendBannedWords:
    def test_append_dedupe_and_count(self):
        root = _tmp_root()
        _run_async(
            get_storage().write_yaml(
                root, "settings/writing-style.yaml", {"role": "r", "banned_words": ["突然"]}
            )
        )
        added = _run_async(append_banned_words(root, ["突然", "ｓｕｄｄｅｎ", "眸子"]))
        assert added == 2
        doc = read_style(_run_async(get_storage().read_yaml(root, "settings/writing-style.yaml")))
        assert doc["banned_words"] == ["突然", "ｓｕｄｄｅｎ", "眸子"]

    def test_full_table_silent_drop(self):
        root = _tmp_root()
        words = [f"词{i:03d}" for i in range(100)]
        _run_async(
            get_storage().write_yaml(
                root, "settings/writing-style.yaml", {"role": "r", "banned_words": words}
            )
        )
        added = _run_async(append_banned_words(root, ["新词甲", "新词乙"]))
        assert added == 0
        doc = _run_async(read_style_migrated(root))
        assert len(doc["banned_words"]) == 100
        assert "新词甲" not in doc["banned_words"]

    def test_bad_input_returns_zero(self):
        root = _tmp_root()
        assert _run_async(append_banned_words(root, [])) == 0
        assert _run_async(append_banned_words(root, None)) == 0
        assert _run_async(append_banned_words(root, ["", "  "])) == 0


# ── 评审修复回归（P1-1/P1-2/P1-3）────────────────────────────────────


class TestReviewFixes:
    def test_append_then_migrate_keeps_distilled_words(self):
        """P1-1：迁移前跑过蒸馏 commit 的书，迁移用合并不覆盖——蒸馏词不丢。"""
        root = _tmp_root()
        s = get_storage()
        _run_async(
            s.write_yaml(
                root,
                "settings/writing-style.yaml",
                {"role": "r", "banned_words": []},
            )
        )
        _run_async(s.write_yaml(root, "settings/anti-ai.yaml", ANTI_AI_DOC))
        # 迁移前：蒸馏 commit append 两个词（无标记位）
        added = _run_async(append_banned_words(root, ["蒸馏词甲", "蒸馏词乙"]))
        assert added == 2
        # 之后任意迁移感知读：anti 模板词并入，蒸馏词仍在
        doc = _run_async(read_style_migrated(root))
        assert "蒸馏词甲" in doc["banned_words"]
        assert "蒸馏词乙" in doc["banned_words"]
        assert "综上所述" in doc["banned_words"]

    def test_migrate_preserves_legacy_snapshot(self):
        """P1-2：迁移读剥离旧键时同款落 _legacy_style 回滚基准（老书从未 PUT 过）。"""
        root = _tmp_root()
        s = get_storage()
        _run_async(
            s.write_yaml(
                root,
                "settings/writing-style.yaml",
                {
                    "role": "r",
                    "narrator_role": "第三人称限知",
                    "tone": {"pov": ["全知片段每卷不超过一次"]},
                },
            )
        )
        doc = _run_async(read_style_migrated(root))
        assert "第三人称限知" in doc["role"]
        # GET 视图剥离留底，但库里要有（回滚基准）
        assert "_legacy_style" not in doc
        raw = _run_async(s.read_yaml(root, "settings/writing-style.yaml"))
        assert "_legacy_style" in raw
        assert raw["_legacy_style"].get("narrator_role") == "第三人称限知"

    def test_put_rejects_invalid_regex_pattern(self):
        """P1-3：非法正则 pattern 在归一边丢弃，不进库（quality 体检不炸）。"""
        merged = put_style(
            normalize_style({"role": "r"}),
            {"tic_patterns": [{"pattern": "不是("}, {"pattern": "OK"}]},
        )
        assert [t["pattern"] for t in merged["tic_patterns"]] == ["OK"]

# ── put_style 两键 ───────────────────────────────────────────────────────


class TestPutBannedKeys:
    def test_roundtrip_and_caps(self):
        base = normalize_style({"role": "r"})
        merged = put_style(
            base,
            {
                "banned_words": ["突然"] + [f"w{i}" for i in range(120)],
                "tic_patterns": [
                    {"pattern": "p1", "threshold": "bad", "severity": "extreme"},
                    {"pattern": "p1"},
                    {"pattern": ""},
                    "不是X而是Y",
                ],
            },
        )
        assert len(merged["banned_words"]) == 100
        assert merged["banned_words"][0] == "突然"
        tics = merged["tic_patterns"]
        assert len(tics) == 2
        assert tics[0]["threshold"] == 3  # 非法落默认
        assert tics[0]["severity"] == "medium"  # 非法降级
        assert tics[1]["pattern"] == "不是X而是Y"  # 字符串条目兼容

    def test_read_strips_marker(self):
        raw = {"role": "r", BANNED_MIGRATED_KEY: True, "banned_words": ["突然"]}
        view = read_style(raw)
        assert BANNED_MIGRATED_KEY not in view
        assert view["banned_words"] == ["突然"]


# ── GET/PUT 端点（含退役分支）───────────────────────────────────────────


async def _override_get_db():
    from db import async_session

    async with async_session() as session:
        yield session


class TestSettingsEndpoints:
    @pytest.fixture()
    def client(self):
        import uuid

        from fastapi.testclient import TestClient

        from auth_local.deps import (
            require_ai_access,
            require_novel_model,
            require_project_limit,
        )
        from auth_local.middleware import get_current_user
        from db import async_session, get_db
        from main import app
        from models.user import User

        # 固定用户：整个 fixture 周期一个 uid（每请求新建会让 get_novel 查不到项目）
        uid = f"bw-{uuid.uuid4().hex[:8]}"

        async def _seed_user():
            async with async_session() as session:
                session.add(
                    User(
                        id=uid,
                        email=f"{uid}@test.com",
                        password_hash="*",
                        display_name=uid,
                    )
                )
                await session.commit()

        async def _override_current_user():
            return {"id": uid}

        import asyncio

        asyncio.new_event_loop().run_until_complete(_seed_user())
        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[require_ai_access] = lambda: True
        app.dependency_overrides[require_novel_model] = lambda: True
        app.dependency_overrides[require_project_limit] = lambda: True
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def _create_project(self, client) -> str:
        import uuid

        r = client.post("/api/novels", json={"name": f"BW-{uuid.uuid4().hex[:6]}"})
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def test_style_roundtrip_with_banned_keys(self, client):
        pid = self._create_project(client)
        r = client.put(
            f"/api/novels/{pid}/settings/style",
            json={"banned_words": ["突然"], "tic_patterns": [{"pattern": "p1", "name": "n"}]},
        )
        assert r.status_code == 200, r.text
        doc = client.get(f"/api/novels/{pid}/settings/style").json()
        assert doc["banned_words"] == ["突然"]
        assert doc["tic_patterns"][0]["pattern"] == "p1"
        assert "fatigue_words" not in doc
        assert BANNED_MIGRATED_KEY not in doc

    def test_anti_ai_words_endpoint_gone(self, client):
        pid = self._create_project(client)
        r = client.post(f"/api/novels/{pid}/settings/anti-ai/words", json={"words": ["x"]})
        # 端点已删除；405（路由形状撞上方法不符）与 404 同为「不可达」表象
        assert r.status_code in (404, 405)

    def test_anti_ai_put_retired_400(self, client):
        pid = self._create_project(client)
        r = client.put(f"/api/novels/{pid}/settings/anti-ai", json={"fatigue_words_zh": {}})
        assert r.status_code == 400
        assert "文风" in r.json()["detail"]
