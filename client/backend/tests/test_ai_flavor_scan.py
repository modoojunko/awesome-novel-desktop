"""AI 味检查（c-deai-wizard）：规则扫描／问题段合并／polish 快扫 单元测试。

纯函数为主（scan_prose / build_problem_segments / quick_verdict）；
端点冒烟走既有 test client 夹具（同 test_plot_ai 范式）。
"""

import pytest

from write.ai_flavor_scan import (
    RULE_LABELS,
    build_problem_segments,
    quick_verdict,
    scan_prose,
)

# ── scan_prose：规则逐条 ────────────────────────────────────────────────


def _rules(report):
    return {f["rule"] for f in report["findings"]}


def test_multi_period_detected_on_long_para():
    long = "他" * 20 + "。他" * 5 + "。"  # 6 处句号、36 字（≥30 才判）
    r = scan_prose(long)
    assert "multi_period" in _rules(r)
    f = next(x for x in r["findings"] if x["rule"] == "multi_period")
    assert f["count"] >= 3 and f["severity"] == "advisory"


def test_multi_period_not_fired_on_short_dialogue():
    r = scan_prose("“走。”")
    assert "multi_period" not in _rules(r)


def test_para_head_repeat_adjacent_same_word():
    prose = "林野把门关上。\n林野把灯吹灭。"
    r = scan_prose(prose)
    assert "para_head_repeat" in _rules(r)


def test_para_head_repeat_alternate_ok():
    r = scan_prose("林野把门关上。\n他把灯吹灭。")
    assert "para_head_repeat" not in _rules(r)


def test_canned_reaction():
    r = scan_prose("他愣了一下，把杯子放下。")
    assert "canned_reaction" in _rules(r)


def test_not_a_but_b_family():
    for s in ("这不是钱的问题，而是命的问题。", "不是A，是B。"):
        assert "not_a_but_b" in _rules(scan_prose(s))


def test_trailing_tag_and_sandwich():
    assert "trailing_tag" in _rules(scan_prose("“走。”他说。"))
    assert "quote_sandwich" in _rules(scan_prose("“走。”他说，“快点。”"))


def test_dash_and_halfwidth_and_nested_quote():
    assert "dash_ban" in _rules(scan_prose("他走了——再没回来。"))
    assert "halfwidth_punct" in _rules(scan_prose("他说,走吧。"))
    assert "nested_quotes" in _rules(scan_prose("他说：“我听见“走”一声。”"))


def test_count_words_claim_not_autofixable():
    r = scan_prose("这五个字，他念了三遍。")
    f = next(x for x in r["findings"] if x["rule"] == "count_words_claim")
    assert f["severity"] == "blocking" and f["autofixable"] is False


def test_empty_prose_clean_and_metrics_none():
    r = scan_prose("")
    assert r["findings"] == [] and r["para_count"] == 0
    assert r["metrics"]["comma_period_ratio"] is None


def test_rule_labels_cover_all_findings():
    prose = (
        "他愣了一下。“走。”他说。\n林野把门关上。\n林野把灯吹灭。\n"
        "他走了——再没回来。\n这五个字，他念了三遍。"
    )
    r = scan_prose(prose)
    for f in r["findings"]:
        assert f["rule"] in RULE_LABELS


# ── build_problem_segments：双源合并 ────────────────────────────────────

PARAS = ["第一段。", "第二段独白。", "第三段。"]


def test_merge_both_sources_dedupe_by_para():
    report = {"findings": [{"rule": "multi_period", "para": 1, "severity": "advisory"}]}
    segs = [
        {"paragraph_index": 1, "label": 2, "confidence": 0.71},
        {"paragraph_index": 2, "label": 2, "confidence": 0.52},
        {"paragraph_index": 0, "label": 0, "confidence": 0.1},
    ]
    out = build_problem_segments(PARAS, report, segs)
    assert [p["para"] for p in out] == [1, 2]  # 段 0 人工＋无规则 → 不进清单
    assert out[0]["source"] == "both"
    assert out[0]["confidence"] == pytest.approx(0.71)
    assert out[1]["source"] == "detector"


def test_merge_low_confidence_detector_ignored():
    segs = [{"paragraph_index": 1, "label": 1, "confidence": 0.3}]
    out = build_problem_segments(PARAS, {"findings": []}, segs)
    assert out == []


# ── quick_verdict：改稿快扫 ─────────────────────────────────────────────


def test_quick_verdict_banned_word_blocking():
    v = quick_verdict("她心头一紧。", "他心头一紧。", banned_words=["心头一紧"])
    assert v["blocking"] is True
    assert any(f["kind"] == "banned_word" for f in v["flags"])


def test_quick_verdict_new_redline_blocking_and_preexisting_advisory():
    # 新增（改前无、改后有）→ blocking；存留（改前就有）→ advisory
    v = quick_verdict("原本就这样。", "新句——另起。", banned_words=[])
    kinds = {f["kind"]: f["level"] for f in v["flags"]}
    assert kinds["dash"] == "block"
    v2 = quick_verdict("原本——就这样。", "仍——保留。", banned_words=[])
    kinds2 = {f["kind"]: f["level"] for f in v2["flags"]}
    assert kinds2["dash"] == "advise"


def test_quick_verdict_quote_parity():
    v = quick_verdict("他说：“走。”", "他说：“走。", banned_words=[])
    assert v["blocking"] is True


def test_quick_verdict_length_band_advisory():
    before = "字" * 100
    after = "字" * 200
    v = quick_verdict(before, after, banned_words=[])
    kinds = {f["kind"] for f in v["flags"]}
    assert "length_swell" in kinds
    assert v["blocking"] is False


def test_quick_verdict_clean_passthrough():
    v = quick_verdict("他走了。", "他回来了。", banned_words=[])
    assert v["blocking"] is False and v["flags"] == []


# ── 端点冒烟（夹具照 test_plot_ai：TestClient＋依赖覆盖） ────────────────

import asyncio
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.deps import require_ai_access as _raa
from auth_local.deps import require_novel_model as _rnm
from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import Chapter, ChapterContent
from models.project import Novel
from models.user import User
from models.volume import Volume

_SCAN_UIDS: dict[str, str] = {}


async def _seed_scan() -> str:
    root = tempfile.mkdtemp(prefix="test_scan_")
    uid = f"sc-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="扫描测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="扫描书", slug=f"sc-{os.path.basename(root)}", root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref="vol-1-ch-1", title="第1章", status="writing", has_prose=True,
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(
            chapter_id=ch.id,
            prose="林野把门关上。\n林野把灯吹灭。\n他愣了一下，把杯子放下。",
        ))
        ch_empty = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=2,
            ref="vol-1-ch-2", title="第2章", status="writing", has_prose=False,
        )
        session.add(ch_empty)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch_empty.id, prose=""))
        await session.commit()
        _SCAN_UIDS[proj.id] = uid
        return proj.id


def _scan_post(nid: str, ref: str = "vol-1-ch-1"):
    c = TestClient(app)
    c.__enter__()
    app.dependency_overrides[get_current_user] = lambda: {"id": _SCAN_UIDS[nid]}
    app.dependency_overrides[_raa] = lambda: True
    app.dependency_overrides[_rnm] = lambda: True
    try:
        return c.post(f"/api/novels/{nid}/chapters/{ref}/ai-flavor-scan", json={})
    finally:
        c.__exit__(None, None, None)


def test_scan_endpoint_ok_shape():
    nid = asyncio.run(_seed_scan())
    r = _scan_post(nid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["detector"]["stored"] is False  # 无存档＝规则模式
    rules = {f["rule"] for f in body["report"]["findings"]}
    assert "para_head_repeat" in rules and "canned_reaction" in rules
    # 双源合并：无存档时只有 rule 来源
    assert all(p["source"] in ("rule", "both") for p in body["problems"])


def test_scan_endpoint_empty_prose_400():
    nid = asyncio.run(_seed_scan())
    r = _scan_post(nid, ref="vol-1-ch-2")  # 空正文 → 400「先写正文」
    assert r.status_code == 400
