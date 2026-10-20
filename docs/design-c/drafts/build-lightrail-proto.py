#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-lightrail-proto.py —— 轻量开书双路径原型：真实样式/图标表逐字注入。

范式抄 /tmp/build-onboard-proto.py（占位符替换、幂等可重放）：
  源模板  drafts/ai-novel-c端-轻量开书双路径-原型.src.html（留占位符）
  产物    drafts/ai-novel-c端-轻量开书双路径-原型.html（自包含单文件）

注入内容全部逐字取自真实样式/脚本（不手写、不近似）：
  base.css / list.css   ← pages/works.html <style>（书架壳用）
  book.css              ← pages/book-write.html <style>（工作台壳用）
  model-config.css      ← pages/config.html <style>（模型配置表单用）
  章档段 .arch-stages / .ds-* ← client/frontend/src/design/book.css
    （pages/*.html 快照 2026-09-25 早于 c-chapter-dossier，未含该段，故从真实 css 逐字补注入）
  图标表 P + render()   ← pages/works.html 脚本（暴露 window.__renderIcons）
按 css 文件名切「/* ═══ 来自 …/<name>（真实样式，逐字注入）═══ */」标记段，段内逐字，
不改一字；新增件样式在源模板的 gl- graft 块里，不经本脚本。

用法：python3 docs/design-c/drafts/build-lightrail-proto.py
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PAGES = os.path.join(ROOT, "docs", "design-c", "pages")
DRAFTS = os.path.join(ROOT, "docs", "design-c", "drafts")
SRC = os.path.join(DRAFTS, "ai-novel-c端-轻量开书双路径-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-轻量开书双路径-原型.html")


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


def icons_js_of():
    """图标表 P + render()：逐字取自 pages/works.html 脚本，暴露 window.__renderIcons。"""
    html = read(os.path.join(PAGES, "works.html"))
    m = re.search(r"var P = (\{.*?\});\s*\n\s*function render\(el\) \{(.*?)\n  \}", html, re.S)
    assert m, "icon map not found in works.html"
    return (
        "var P = " + m.group(1) + ";\n"
        "  function render(el) {" + m.group(2) + "\n  }\n"
        "  window.__renderIcons = function (root) { (root || document).querySelectorAll('i[data-ico]').forEach(render); };\n"
        "  window.__renderIcons();\n"
    )


def book_dossier_css():
    """章档段（.arch-stages 归档三段条 / .ds-* 章档四域表）：pages/*.html 快照（2026-09-25）
    早于 c-chapter-dossier，未含该段——逐字补注入 client/frontend/src/design/book.css 原文，
    不手写、不近似。返回 (arch_stages_seg, ds_seg)。"""
    css = read(os.path.join(ROOT, "client", "frontend", "src", "design", "book.css"))
    a = re.search(
        r"/\* 归档卡三段进度（c-ops-archive-stages）：提取 → 确认 → 完成 \*/.*?"
        r"\.arch-stages \.is-skip \.as-dot \{ background: var\(--muted\); \}",
        css, re.S)
    assert a, "arch-stages segment not found in design/book.css"
    b = re.search(r"/\* ─── 章档页签（c-chapter-dossier.*?(?=\n\n/\* ═══ )", css, re.S)
    assert b, "dossier segment not found in design/book.css"
    return a.group(0), b.group(0)


def main():
    works_style = style_of("works.html")        # base.css + list.css
    bookw_style = style_of("book-write.html")   # base.css + book.css
    config_style = style_of("config.html")      # base.css + model-config.css
    arch_seg, ds_seg = book_dossier_css()       # design/book.css 章档段（pages 快照未含，逐字补注入）

    inject = {
        "/*__INJECT_STYLE_BASE__*/": seg_of(works_style, "base.css", "works.html"),
        "/*__INJECT_STYLE_LIST__*/": seg_of(works_style, "list.css", "works.html"),
        "/*__INJECT_STYLE_BOOK__*/": seg_of(bookw_style, "book.css", "book-write.html"),
        "/*__INJECT_STYLE_MODELCONFIG__*/": seg_of(config_style, "model-config.css", "config.html"),
        "/*__INJECT_STYLE_BOOK_DOSSIER__*/":
            "/* ═══ 补注入真实样式段：pages/*.html 快照（2026-09-25）未含 c-chapter-dossier，\n"
            "   以下两段逐字取自 client/frontend/src/design/book.css（未手写、未近似） ═══ */\n"
            + arch_seg + "\n\n" + ds_seg,
        "/*__INJECT_SCRIPT_ICONS__*/": icons_js_of(),
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
