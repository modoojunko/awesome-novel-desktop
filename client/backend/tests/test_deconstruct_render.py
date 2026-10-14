"""图谱渲染单元（deconstruct/render.py）——注入安全与确定性。

判例：查看器在用户浏览器打开＝注入面——JSON 岛内 `<` 必须 \u003c 转义；模板文本一律 esc()；
对抗夹具（</script>、<img onerror>、U+2028）进图后不得以可执行形态出现在产物里。
"""

from __future__ import annotations

import json
import re

from deconstruct.graph import assemble
from deconstruct.render import render_html, render_svg

_EVIL = "</script><img src=x onerror=alert(1)>"


def _graph():
    cards = {
        "1": {"summary": "开场", "characters": [{"name": _EVIL, "role": "主角", "traits": "", "alias": ""}],
              "places": [{"name": "竹湾渡口", "parent": "", "note": ""}],
              "presence": [{"who": _EVIL, "where": "竹湾渡口"}],
              "intro": [], "genre": [], "world": [], "relations": [], "mainplot": [],
              "structure": [], "style": [], "techniques": [], "foreshadow": []},
    }
    products = {
        "characters": {"data": {"characters": [{"name": _EVIL, "role": "主角", "plot": "p" + _EVIL, "evidence_ch": "第1章"}]}},
        "intro": {"data": {"intro": "恶人开场\u2028第二行"}},
    }
    return assemble(book_name="《恶书》" + _EVIL, chapter_count=1, words=10, cards=cards,
                    products=products, place_merge=None, source_text="第1章 开场\n" + _EVIL + "出现。")


def test_render_html_island_roundtrip_and_escape():
    g = _graph()
    html = render_html(g)
    start = html.index('<script id="graphdata" type="application/json">') + len(
        '<script id="graphdata" type="application/json">')
    end = html.index("</script>", start)
    island = html[start:end]
    assert "<" not in island, "JSON 岛内不得残留裸 <（</script> 逃逸面）"
    assert "\\u003c" in island
    assert json.loads(island) == g
    assert "<img" not in html  # 对抗串不得以标签形态出现
    assert "\u2028" not in island  # U+2028 行分隔符已转义
    assert "\\u2028" in island


def test_render_html_title_escaped():
    g = _graph()
    html = render_html(g)
    assert html.count("<title>") == 1
    m = re.search(r"<title>(.*?)</title>", html)
    assert "<" not in m.group(1) and "&lt;" in m.group(1)


def test_template_has_no_prototype_chrome():

    from deconstruct.render import _TEMPLATE

    with open(_TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    for bad in ("原型", "v7", "v6", "尚未产出", "TODO"):
        assert bad not in tpl, f"生产模板残留原型文案：{bad}"


def test_render_svg_deterministic_and_escaped():
    g = _graph()
    a, b = render_svg(g), render_svg(g)
    assert a == b, "同输入必须同字节（禁 wall-clock）"
    assert a.startswith("<svg") and a.rstrip().endswith("</svg>")
    assert "<img" not in a
    assert "&lt;/script&gt;" in a  # 节点名以转义形态呈现
    assert "地点账" in a and "竹湾渡口" in a
    assert "deconstruct-graph/6" in a


def test_template_inline_js_syntax():
    """模板内联 JS 语法检查（环境无 node 时跳过——前端 CI 另有把关）。"""
    import os as _os
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("node"):
        return

    from deconstruct.render import _TEMPLATE

    with open(_TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    js = re.findall(r"<script>(.*?)</script>", tpl, re.DOTALL)[-1]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True, check=False)
        assert r.returncode == 0, r.stderr[:500]
    finally:
        _os.unlink(path)
