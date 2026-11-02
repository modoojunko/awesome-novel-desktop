"""基线包闸门双端 parity（c-kb-baseline C1）。

单源判据＝`tests/fixtures/kb_baseline_gate_cases.json`：
- C 端：kb.gates.check_baseline_entry（同步器 _parse_entries 直接调用）
- 内容仓：awesome-novel-knowledge/tools/validate.py（CI 跑同一 fixture）

内容仓不在本机（主库 CI 单仓 checkout）时跳过跨仓对拍——口径仍是「缺源＝跳过，
不是伪装通过」（同 PROMPT_PACK_DEV_DIR 先例）。两仓都在时还比对 fixture 字节，
防一侧改了判据忘记同步。
"""

import importlib.util
import json
import os
from pathlib import Path

import pytest

from kb.gates import check_baseline_entry

FIXTURE = Path(__file__).parent / "fixtures" / "kb_baseline_gate_cases.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_vocab_与_fixture_一致():
    from kb.concepts import CHAPTER_POS, EMOTIONS, SCENES, THEMES

    v = _fixture()["vocab"]
    assert list(THEMES) == v["themes"]
    assert list(SCENES) == v["scenes"]
    assert list(EMOTIONS) == v["emotions"]
    assert list(CHAPTER_POS) == v["chapter_pos"]


def test_fixture_每例与_C端判据一致():
    doc = _fixture()
    assert doc["cases"]
    for case in doc["cases"]:
        got = check_baseline_entry(case["entry"])
        assert got == case["error"], f"{case['name']}: 期望 {case['error']}，实际 {got}"


def test_parse_entries_按同一判据计数():
    from kb.baseline import _parse_entries

    doc = _fixture()
    good = [c["entry"] for c in doc["cases"] if c["error"] is None]
    bad = [c["entry"] for c in doc["cases"] if c["error"] is not None]
    raw = "\n".join(json.dumps(e, ensure_ascii=False) for e in good + bad).encode()
    ok, n_bad = _parse_entries(raw)
    assert len(ok) == len(good)
    assert n_bad == len(bad)
    assert all(e["instruction"] == e["instruction"].strip() for e in ok)


def _content_repo() -> Path | None:
    env = os.environ.get("KNOWLEDGE_REPO_DIR")
    cand = [Path(env)] if env else []
    cand += [
        Path(__file__).resolve().parents[3] / "awesome-novel-knowledge",
        Path("/Users/modoojunko/Desktop/coding/awesome-novel-knowledge"),
    ]
    for p in cand:
        if p and (p / "tools" / "validate.py").is_file():
            return p
    return None


def test_内容仓_validate_同集对拍():
    repo = _content_repo()
    if repo is None:
        pytest.skip("内容仓 awesome-novel-knowledge 不在本机（单仓 checkout）——跨仓对拍跳过")

    spec = importlib.util.spec_from_file_location("kb_content_validate", repo / "tools" / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    remote_fixture = repo / "tests" / "fixtures" / "kb_baseline_gate_cases.json"
    assert remote_fixture.is_file(), "内容仓缺同份 fixture——parity 口径断链"
    assert json.loads(remote_fixture.read_text(encoding="utf-8")) == _fixture(), (
        "两仓 fixture 不一致：改判据后必须同步另一仓"
    )

    for case in _fixture()["cases"]:
        got = mod.validate_one(case["entry"])
        assert got == case["error"], f"{case['name']}: 内容仓 {got} ≠ C 端 {case['error']}"


def test_内容仓_现有条目全过_C端判据():
    """内容仓 knowledge/*.jsonl 的每个条目在 C 端判据下也必须合格（发布前真空转）。"""
    repo = _content_repo()
    if repo is None:
        pytest.skip("内容仓不在本机——跳过")

    total = 0
    for path in sorted(repo.glob("knowledge/*/*.jsonl")):
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            total += 1
            entry = json.loads(raw)
            assert check_baseline_entry(entry) is None, f"{path.name}:{lineno} {check_baseline_entry(entry)}"
    assert total > 0
