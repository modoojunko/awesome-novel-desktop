"""正文检测问题行工具（c-agent-prose-checks）：人味现算＋朱雀读档，按需查不注入。

样式对齐 test_assistant_page_context：直调工具函数＋ToolContext，monkeypatch
数据源（章存储/朱雀存档），不起 HTTP、不碰真实库。
"""

import pytest

from assistant.scopes import tools_for_thread
from assistant.tools import ToolContext, _read_prose_checks

# 两处问题：段 0 破折号（一票否决）＋段 1 相邻段首同词（提示）。
# 句长刻意错开，避免撞「句长趋同」窗口——本文件钉工具格式化，不测引擎规则。
PROSE = (
    "他站住了，没动——手里的纸袋还没拆。\n"
    "他站在门口，听楼上的水声。\n"
    "她把那扇窗推开，风灌进来，桌上的纸签翻了两下，又落回原处。\n"
    "窗外有人在喊，声音散在半空。"
)
CLEAN = "她把窗推开，风灌进来。\n海面上有船进港，汽笛拖得很长。"


def _patch_chapter(monkeypatch, prose=CLEAN, title="短刃震颤引血族"):
    import chapters.store as cs

    async def _fake(root_path, ref):
        return {"title": title, "outline": "", "prose": prose}

    monkeypatch.setattr(cs, "load_chapter", _fake)


def _patch_zhuque(monkeypatch, stored):
    import zhuque.service as zs

    async def _fake(session, *, project_id, chapter_ref):
        if isinstance(stored, Exception):
            raise stored
        return stored

    monkeypatch.setattr(zs, "get_stored_result", _fake)


def _ctx(**kw):
    return ToolContext(novel_id="n1", root_path="/root", user_id="u1", **kw)


@pytest.mark.asyncio
async def test_renwei_findings_formatted_with_para_text(monkeypatch):
    _patch_chapter(monkeypatch, PROSE)
    _patch_zhuque(monkeypatch, {"stored": False})
    res = await _read_prose_checks(_ctx(), "vol-1-ch-7")
    assert res.ok is True
    assert res.card is None
    assert "《短刃震颤引血族》（vol-1-ch-7）" in res.summary
    assert "按已保存正文现算" in res.summary
    assert "一票否决 1 · 提示 1" in res.summary
    assert "第1段〔一票否决〕破折号" in res.summary
    # 原句整句给模型：不用作家贴屏上那几行
    assert "他站住了，没动——手里的纸袋还没拆。" in res.summary
    assert "第2段〔提示〕相邻段首同词" in res.summary
    assert "为什么：" in res.summary and "改法：" in res.summary
    assert "朱雀检测：这章没有存档" in res.summary


@pytest.mark.asyncio
async def test_screen_prose_wins_for_focus_chapter(monkeypatch):
    _patch_chapter(monkeypatch, CLEAN)
    _patch_zhuque(monkeypatch, {"stored": False})
    ctx = _ctx(focus_ref="vol-1-ch-7", page_prose=PROSE)
    res = await _read_prose_checks(ctx)  # 缺省＝当前章
    assert "按屏上当前正文现算（可能有未保存改动）" in res.summary
    assert "破折号" in res.summary


@pytest.mark.asyncio
async def test_cross_chapter_ignores_screen_prose(monkeypatch):
    _patch_chapter(monkeypatch, CLEAN)
    _patch_zhuque(monkeypatch, {"stored": False})
    ctx = _ctx(focus_ref="vol-1-ch-7", page_prose=PROSE)
    res = await _read_prose_checks(ctx, "vol-1-ch-2")
    # 跨章问别章：屏上文本只属于 focus_ref，不能冒充别章
    assert "按已保存正文现算" in res.summary
    assert "没查出问题行" in res.summary
    assert "破折号" not in res.summary


@pytest.mark.asyncio
async def test_unsaved_but_no_screen_text_is_labelled(monkeypatch):
    _patch_chapter(monkeypatch, CLEAN)
    _patch_zhuque(monkeypatch, {"stored": False})
    ctx = _ctx(page_unsaved=("正文未保存",))
    res = await _read_prose_checks(ctx, "vol-1-ch-2")
    assert "结果可能与屏上标注不一致" in res.summary


@pytest.mark.asyncio
async def test_missing_ref_asks_for_chapter(monkeypatch):
    res = await _read_prose_checks(_ctx())
    assert res.ok is False
    assert "没指明" in res.summary


@pytest.mark.asyncio
async def test_empty_prose_is_soft(monkeypatch):
    _patch_chapter(monkeypatch, "")
    _patch_zhuque(monkeypatch, {"stored": False})
    res = await _read_prose_checks(_ctx(), "vol-1-ch-2")
    assert res.ok is True
    assert "正文还是空的" in res.summary


@pytest.mark.asyncio
async def test_zhuque_archive_fresh_lists_flagged_lines(monkeypatch):
    from zhuque.segmentation import fingerprint

    _patch_chapter(monkeypatch, CLEAN)
    _patch_zhuque(monkeypatch, {
        "stored": True,
        "prose_hash": fingerprint(CLEAN),
        "checked_at": "2026-11-23T08:00:00",
        "result": {"segments": [
            {"paragraph_index": 0, "label": 1, "confidence": 0.8},
            {"paragraph_index": 1, "label": 2, "confidence": 0.7},
        ]},
    })
    res = await _read_prose_checks(_ctx(), "vol-1-ch-2")
    assert "与当前正文一致" in res.summary
    assert "第1段〔AI〕：「她把窗推开，风灌进来。」" in res.summary
    assert "第2段〔疑似〕：「海面上有船进港，汽笛拖得很长。」" in res.summary


@pytest.mark.asyncio
async def test_zhuque_stale_archive_hides_quotes(monkeypatch):
    _patch_chapter(monkeypatch, CLEAN)
    _patch_zhuque(monkeypatch, {
        "stored": True,
        "prose_hash": "deadbeef",
        "checked_at": "2026-11-22T21:00:00",
        "result": {"segments": [{"paragraph_index": 0, "label": 1, "confidence": 0.8}]},
    })
    res = await _read_prose_checks(_ctx(), "vol-1-ch-2")
    assert "结果已过期" in res.summary
    assert "原句不可靠" in res.summary
    # 过期档段号/原句都可能对不上，不出原句防误导
    assert "「她把窗推开" not in res.summary


@pytest.mark.asyncio
async def test_zhuque_read_failure_is_soft(monkeypatch):
    _patch_chapter(monkeypatch, CLEAN)
    _patch_zhuque(monkeypatch, RuntimeError("boom"))
    res = await _read_prose_checks(_ctx(), "vol-1-ch-2")
    assert res.ok is True
    assert "读存档失败" in res.summary
    assert "没查出问题行" in res.summary  # 人味主体不受影响


@pytest.mark.asyncio
async def test_budget_truncates_from_first_overflow(monkeypatch):
    many = "\n".join(f"第{i}段他站着——手里有东西。" for i in range(30))
    _patch_chapter(monkeypatch, many)
    _patch_zhuque(monkeypatch, {"stored": False})
    res = await _read_prose_checks(_ctx(), "vol-1-ch-2")
    assert "第1段〔一票否决〕破折号" in res.summary  # 首条明细在
    assert "（后面" in res.summary and "先不展开" in res.summary
    # 预算放不下即整体停：不跳过首条去捞后面的行，末段明细不出现
    assert "第30段〔" not in res.summary


def test_scopes_mount_prose_and_style_domains():
    assert "read_prose_checks" in tools_for_thread("ch:prose")
    assert "read_prose_checks" in tools_for_thread("ch:style")
    # 非正文/文风域不挂（设定页看检测问题行请切回正文页签）
    assert "read_prose_checks" not in tools_for_thread("set:world")
    assert "read_prose_checks" not in tools_for_thread("ch:og")
