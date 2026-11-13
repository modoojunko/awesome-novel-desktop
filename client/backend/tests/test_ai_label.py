"""AI 生成显式标识（标识办法第四条）：成稿下载/作品包/章节归档三出口全覆盖。"""

from __future__ import annotations

import io

from ai_label import AI_NOTICE, with_ai_notice
from manuscript.content import Manuscript, ManuscriptChapter, ManuscriptVolume
from manuscript.render import render_docx, render_md, render_txt


def _mini_ms() -> Manuscript:
    return Manuscript(title="书名", volumes=[ManuscriptVolume(
        no=1, title="卷名", chapters=[ManuscriptChapter(no=1, title="第一章", prose="正文一段。")],
    )])


def test_md_txt尾部带标识且幂等():
    md = render_md(_mini_ms())
    txt = render_txt(_mini_ms())
    assert AI_NOTICE in md and AI_NOTICE in txt
    assert with_ai_notice(md) == md  # 幂等：不重复叠加


def test_docx尾段带标识():
    try:
        import docx  # noqa: F401
    except ImportError:
        import pytest

        pytest.skip("docx 组件不可用")
    data = render_docx(_mini_ms())
    document = docx.Document(io.BytesIO(data))
    texts = [p.text for p in document.paragraphs]
    assert AI_NOTICE in texts


def test_project_zip带AI_GENERATED与ai_notice字段():
    """export_project 的 zip 契约：AI-GENERATED.txt 在包内，project.json 带 ai_notice。

    export_project 路由重 IO，这里钉住它引用的常量与写入键名防漂移：
    - novels/router.py 必须从 ai_label.AI_NOTICE 取文案（不得另起炉灶）
    - 固定文件名 AI-GENERATED.txt
    """
    import inspect

    import novels.router as nr

    src = inspect.getsource(nr)
    assert "AI-GENERATED.txt" in src
    assert "from ai_label import AI_NOTICE" in src
    assert '"ai_notice": AI_NOTICE' in src


def test_with_ai_notice_空白容忍与自定义():
    assert with_ai_notice("正文。\n") == "正文。\n\n" + AI_NOTICE + "\n"
    custom = "自定义声明"
    out = with_ai_notice("正文。", notice=custom)
    assert custom in out and AI_NOTICE not in out
