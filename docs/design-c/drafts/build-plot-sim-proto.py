#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-plot-sim-proto.py —— 剧情推演重设计原型：真实样式逐字注入。

范式同 build-lightrail-proto.py（占位符替换、幂等可重放）：
  源模板  drafts/ai-novel-c端-剧情推演重设计-原型.src.html（留占位符）
  产物    drafts/ai-novel-c端-剧情推演重设计-原型.html（自包含单文件）

注入内容逐字取自真实样式（不手写、不近似）：
  base.css / book.css ← pages/book-write.html <style>（工作台壳＋弹窗 .mcard.wb-style 用）
按 css 文件名切「/* ═══ 来自 …/<name>（真实样式，逐字注入）═══ */」标记段，段内逐字，
不改一字；新增件样式在源模板的 ps- graft 块里，不经本脚本。
图标表与弹层脚本已随底座 body 逐字复制进源模板，不经本脚本。

用法：python3 docs/design-c/drafts/build-plot-sim-proto.py
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PAGES = os.path.join(ROOT, "docs", "design-c", "pages")
DRAFTS = os.path.join(ROOT, "docs", "design-c", "drafts")
SRC = os.path.join(DRAFTS, "ai-novel-c端-剧情推演重设计-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-剧情推演重设计-原型.html")
PAGE = "book-write.html"


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def style_of(page):
    html = read(os.path.join(PAGES, page))
    m = re.search(r"<style>(.*)</style>", html, re.S)
    assert m, "no <style> in " + page
    return m.group(1)


def seg_of(style, css_name, page):
    """切出「/* ═══ 来自 …/<css_name>（真实样式，逐字注入）═══ */」标记段（含尾部非基线段）。"""
    m = re.search(r"/\* ═══ 来自 \S*?%s（真实样式，逐字注入）═══ \*/" % re.escape(css_name), style)
    assert m, "%s segment not found in %s" % (css_name, page)
    nxt = re.compile(r"/\* ═══ 来自 ").search(style, m.end())
    return style[m.start(): nxt.start() if nxt else len(style)].rstrip("\n")


def main():
    style = style_of(PAGE)
    inject = {
        "/*__INJECT_STYLE_BASE__*/": seg_of(style, "base.css", PAGE),
        "/*__INJECT_STYLE_BOOK__*/": seg_of(style, "book.css", PAGE),
    }
    html = read(SRC)
    for ph in inject:
        assert ph in html, "placeholder missing in src: " + ph
    for ph, body in inject.items():
        html = html.replace(ph, body)
    assert "__INJECT" not in html, "placeholder left in output"

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("injected OK -> %s (%d bytes)" % (OUT, len(html)))
    for ph, body in inject.items():
        print("  %-32s %6d chars" % (ph.strip("/*").rstrip("*/"), len(body)))


if __name__ == "__main__":
    main()
