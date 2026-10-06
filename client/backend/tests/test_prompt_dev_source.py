"""开发态模板目录与注释剥除收口（c-prompt-source-flip）。

覆盖：
- 解析序②＝`PROMPT_PACK_DEV_DIR` 指定目录 → 回退包内目录；force/frozen 双禁；
- `load()` 剥注释收口：一切读取路径（裸 load、load_layers、片段 load_fragment、
  _rules_sections、style .format 消费方）产物不含纳管注释与哨兵行；
- 包状态同源：dev-dir 可用 ⇒ `prompt_pack.sync.get_status().phase == "ready"`。

模板源两态对拍：dev-dir 指向 sibling 提示词仓（带纳管注释）剥注释后须与包内
目录（上游单源）逐字一致——两源漂移即红。
"""

import sys
from pathlib import Path

import pytest

import prompts
from prompts import (
    PromptPackMissing,
    dev_template_dir,
    load,
    load_layers,
)

SIBLING_PROMPTS = Path(__file__).resolve().parents[4] / "awesome-novel-prompts" / "prompts"

pytestmark = pytest.mark.usefixtures("_isolated_prompt_env")


@pytest.fixture
def _isolated_prompt_env(monkeypatch):
    """隔离 env 与 frozen 标志，防用例间互相污染。"""
    monkeypatch.delenv(prompts.DEV_DIR_ENV, raising=False)
    monkeypatch.delenv(prompts.FORCE_PACK_ENV, raising=False)
    real_frozen = getattr(sys, "frozen", False)
    if "frozen" in sys.__dict__ or hasattr(sys, "frozen"):
        monkeypatch.setattr(sys, "frozen", False, raising=False)
    yield
    if real_frozen is False and hasattr(sys, "frozen"):
        monkeypatch.delattr(sys, "frozen", raising=False)


def _write_template(tmp_path: Path, name: str, body: str) -> Path:
    f = tmp_path / f"{name}.prompt"
    f.write_text(body, encoding="utf-8")
    return f


ANNOTATED = (
    "## ★★ awesome-novel-prompts 纳管注释（sync.py 生成 · 发布打包时剥除）★★\n"
    "## 用途｜测试模板\n"
    "## 触发｜不应进入模型输入\n"
    "## ★★ 纳管注释结束 ★★\n"
    "<<system>>\n你是测试助手。\n<<user>>\n输入：{material}\n"
)


# ── 解析序②：dev-dir ─────────────────────────────────────────────────────────


class TestDevTemplateDir:
    def test_env_dir_takes_priority(self, tmp_path, monkeypatch):
        _write_template(tmp_path, "x", "<<system>>\nA\n<<user>>\nB")
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        assert dev_template_dir() == str(tmp_path)
        assert load("x") == "<<system>>\nA\n<<user>>\nB"

    def test_fallback_to_bundled_dir(self):
        dev_template_dir.cache_clear() if hasattr(dev_template_dir, "cache_clear") else None
        assert dev_template_dir() == prompts._PROMPTS_DIR

    def test_missing_env_dir_is_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path / "nope"))
        assert dev_template_dir() is None

    def test_force_disables(self, tmp_path, monkeypatch):
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        monkeypatch.setenv(prompts.FORCE_PACK_ENV, "force")
        assert dev_template_dir() is None

    def test_frozen_disables(self, tmp_path, monkeypatch):
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        assert dev_template_dir() is None

    def test_pack_hops_first_even_with_dev_dir(self, tmp_path, monkeypatch):
        """已装包优先：pack 命中时不读 dev 目录。"""
        _write_template(tmp_path, "polish_text", "DEV-ONLY-TEXT")

        import prompt_pack as pp

        monkeypatch.setattr(
            pp, "read_template", lambda name: "PACK-TEXT", raising=False
        )
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        assert load("polish_text") == "PACK-TEXT"


# ── 注释剥除收口 ──────────────────────────────────────────────────────────────


class TestCommentStripping:
    def test_load_strips_annotation(self, tmp_path, monkeypatch):
        _write_template(tmp_path, "t", ANNOTATED)
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        out = load("t")
        assert "纳管注释" not in out
        assert "★★" not in out
        assert out.startswith("<<system>>")

    def test_load_layers_strips(self, tmp_path, monkeypatch):
        _write_template(tmp_path, "t", ANNOTATED)
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        system, user = load_layers("t")
        assert system == "你是测试助手。"
        assert user == "输入：{material}"
        assert "★★" not in system + user

    def test_fragment_path_strips(self, tmp_path, monkeypatch):
        """片段加载（volumes/ai_plan.load_fragment）产物不含注释。"""
        from volumes.ai_plan import load_fragment

        _write_template(tmp_path, "frag", "## 注释行\n## 另一行\n1. 规则一\n2. 规则二\n")
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        assert load_fragment("frag") == "1. 规则一\n2. 规则二"

    def test_rules_sections_strips(self, tmp_path, monkeypatch):
        """_rules_sections（volume_rules → expand/check system）不含注释。"""
        from volumes.ai_plan import _rules_sections

        body = (
            "## ★★ 纳管注释 ★★\n"
            "## 备注｜触发端点\n"
            "【八条硬规则】\n1. 规则\n"
            "【体检判据】\n对主线：检查\n"
        )
        _write_template(tmp_path, "volume_rules", body)
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        rules, criteria = _rules_sections()
        assert rules.startswith("【八条硬规则】")
        assert criteria.startswith("【体检判据】")
        assert "★" not in rules + criteria

    def test_style_format_caller_strips(self, tmp_path, monkeypatch):
        """裸 load() 的 .format 消费方（settings/ai_router style 家族形态）不含注释。"""
        body = (
            "## ★★ 纳管注释 ★★\n"
            "## 备注｜全文入 user 消息\n"
            "你是文风分析师。\n样本：{sample}\n"
        )
        _write_template(tmp_path, "style_distill_step1", body)
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        out = load("style_distill_step1").format(sample="正文样本")
        assert "★★" not in out
        assert out == "你是文风分析师。\n样本：正文样本"

    def test_sibling_source_matches_bundled(self, monkeypatch):
        """两源对拍：sibling（带注释）剥注释后与包内目录逐字一致（抽样）。"""
        if not SIBLING_PROMPTS.is_dir():
            pytest.skip("sibling 提示词仓不在位（非 sibling 布局）")
        for name in ("polish_text", "volume_rules", "write_chapter"):
            monkeypatch.setenv(prompts.DEV_DIR_ENV, str(SIBLING_PROMPTS))
            from_sib = load(name)
            monkeypatch.delenv(prompts.DEV_DIR_ENV)
            from_bundled = load(name)
            assert from_sib == from_bundled, name


# ── 包状态同源 ────────────────────────────────────────────────────────────────


class TestPackStatusParity:
    def test_dev_dir_ready(self, tmp_path, monkeypatch):
        _write_template(tmp_path, "t", ANNOTATED)
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        from prompt_pack import sync as pack_sync

        pack_sync.reset_state()
        assert pack_sync.get_status()["phase"] == "ready"

    def test_no_source_missing(self, monkeypatch):
        monkeypatch.setenv(prompts.FORCE_PACK_ENV, "force")
        from prompt_pack import sync as pack_sync

        pack_sync.reset_state()
        assert pack_sync.get_status()["phase"] == "missing"

    def test_empty_dev_dir_not_ready(self, tmp_path, monkeypatch):
        """空目录（无 .prompt）不算可用来源。"""
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(empty))
        from prompt_pack import sync as pack_sync

        pack_sync.reset_state()
        assert pack_sync.get_status()["phase"] == "missing"


# ── 兼容回归 ──────────────────────────────────────────────────────────────────


class TestCompat:
    def test_missing_template_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        with pytest.raises(PromptPackMissing):
            load("no_such_template_xyz")

    @pytest.mark.parametrize(
        "bad", ["../../etc/passwd", "/etc/passwd", "sub/file", ""]
    )
    def test_unsafe_names_rejected(self, bad):
        with pytest.raises(ValueError, match="Invalid prompt name"):
            load(bad)

    def test_load_layers_compat_unlayered(self, tmp_path, monkeypatch):
        """未分层文件返回 ("", 全文剥注释)。"""
        _write_template(tmp_path, "plain", "## 头注释\n纯文本模板")
        monkeypatch.setenv(prompts.DEV_DIR_ENV, str(tmp_path))
        assert load_layers("plain") == ("", "纯文本模板")
