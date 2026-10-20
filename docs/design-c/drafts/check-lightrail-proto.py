#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-lightrail-proto.py —— 轻量开书双路径原型自检（三项，逐条过）。

① HTML 结构：python html.parser 校验标签闭合、切屏 ID 对齐（demo-bar data-s ↔ section#id）；
② class 可溯源：产物里出现的每一个非 gl- 的 class 名，能在 pages/*.html 的 <style> 块
   或 client/frontend/src/design/*.css 里找到定义（找不到的逐个报出）；
③ CSS 逐字：抽产物里注入的 CSS 段与原文 diff（pages/*.html <style> 段 + 补注入的
   design/book.css 章档段），逐字一致（≥3 段）。

用法：python3 docs/design-c/drafts/check-lightrail-proto.py
"""
import importlib.util
import io
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PAGES = os.path.join(ROOT, "docs", "design-c", "pages")
DESIGN = os.path.join(ROOT, "client", "frontend", "src", "design")
OUT = os.path.join(HERE, "ai-novel-c端-轻量开书双路径-原型.html")

# 复用构建脚本的切段函数，保证「注入的就是被 diff 的」
spec = importlib.util.spec_from_file_location("lightrail_build", os.path.join(HERE, "build-lightrail-proto.py"))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "path", "circle", "rect", "line", "polyline", "polygon"}


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


# ── ① html.parser 标签闭合 + 切屏 ID 对齐 ──────────────────────────────────
class Checker(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.ids = set()
        self.screen_btns = set()
        self.classes = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if a.get("data-s"):
            self.screen_btns.add(a["data-s"])
        if a.get("class"):
            self.classes.update(a["class"].split())
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append("多余的结束标签 </%s> @%s" % (tag, self.getpos()))
            return
        top, pos = self.stack.pop()
        if top != tag:
            self.errors.append("标签不匹配：<%s> @%s 被 </%s> @%s 关闭" % (top, pos, tag, self.getpos()))


def check_html(html):
    p = Checker()
    p.feed(html)
    p.close()
    ok = True
    if p.errors:
        ok = False
        for e in p.errors[:20]:
            print("  ✗", e)
    if p.stack:
        ok = False
        for tag, pos in p.stack[:20]:
            print("  ✗ 未闭合 <%s> @%s" % (tag, pos))
    if not p.screen_btns:
        ok = False
        print("  ✗ demo-bar 未找到任何 data-s 切屏按钮")
    for s in sorted(p.screen_btns):
        if s not in p.ids:
            ok = False
            print("  ✗ 切屏按钮 data-s=%s 找不到对应 section#%s" % (s, s))
    for s in ["s1", "s2", "s3", "s4", "s5", "s6", "s7"]:
        if s not in p.ids:
            ok = False
            print("  ✗ 缺屏 <section id=\"%s\">" % s)
    print("  切屏按钮 %s ↔ 屏 id 对齐：%s" % (sorted(p.screen_btns), "OK" if ok else "FAIL"))
    return ok, p.classes


# ── ② class 可溯源 ────────────────────────────────────────────────────────
def class_defs():
    defs = set()
    for f in sorted(os.listdir(DESIGN)):
        if f.endswith(".css"):
            defs.update(re.findall(r"\.([A-Za-z0-9_-]+)", read(os.path.join(DESIGN, f))))
    for f in sorted(os.listdir(PAGES)):
        if f.endswith(".html"):
            m = re.search(r"<style>(.*)</style>", read(os.path.join(PAGES, f)), re.S)
            if m:
                defs.update(re.findall(r"\.([A-Za-z0-9_-]+)", m.group(1)))
    return defs


def check_classes(used, defs):
    missing = sorted(c for c in used if not c.startswith("gl-") and c not in defs)
    if missing:
        for c in missing:
            print("  ✗ 找不到定义的 class：%s" % c)
        return False
    print("  %d 个 class 全部可溯源（gl- graft %d 个不计）：%s"
          % (len(used), sum(1 for c in used if c.startswith("gl-")), sorted(c for c in used if c.startswith("gl-"))))
    return True


# ── ③ 注入 CSS 与 pages/ 原文 diff 逐字一致 ────────────────────────────────
def check_css_verbatim(html):
    pairs = [
        ("base.css", "works.html"),
        ("list.css", "works.html"),
        ("book.css", "book-write.html"),
        ("model-config.css", "config.html"),
    ]
    ok = True
    checked = 0
    for css_name, page in pairs:
        want = build.seg_of(build.style_of(page), css_name, page)
        m = re.search(r"/\* ═══ 来自 \S*?%s（真实样式，逐字注入）═══ \*/" % re.escape(css_name), html)
        if not m:
            ok = False
            print("  ✗ 产物缺注入段：%s（来自 %s）" % (css_name, page))
            continue
        # 段边界：下一个源文件标记 / 补注入段起点 / graft 块起点 / </style>
        nxt = re.search(r"/\* ═══ 来自 |/\* ═══ 补注入真实样式段|/\* ══════════ 新增 graft", html[m.end():])
        end = m.end() + nxt.start() if nxt else html.find("</style>", m.start())
        got = html[m.start():end].rstrip("\n")
        if got == want:
            checked += 1
            print("  ✓ %s ← pages/%s：逐字一致（%d chars）" % (css_name, page, len(want)))
        else:
            ok = False
            i = next((k for k in range(min(len(got), len(want))) if got[k] != want[k]), min(len(got), len(want)))
            print("  ✗ %s ← pages/%s：第 %d 字符起不一致（%r vs %r）" % (css_name, page, i, want[i:i + 40], got[i:i + 40]))
    # 补注入段（pages/ 快照未含）：与 client/frontend/src/design/book.css 原文逐字比对
    arch_seg, ds_seg = build.book_dossier_css()
    for name, seg in [(".arch-stages 段", arch_seg), (".ds-* 章档段", ds_seg)]:
        if seg in html:
            checked += 1
            print("  ✓ %s ← design/book.css：逐字一致（%d chars）" % (name, len(seg)))
        else:
            ok = False
            print("  ✗ %s ← design/book.css：产物中找不到逐字原文" % name)
    if checked < 3:
        ok = False
        print("  ✗ 逐字一致的注入段不足 3 段（仅 %d）" % checked)
    return ok


def main():
    html = read(OUT)
    print("[1/3] HTML 结构（html.parser）＋切屏 ID 对齐")
    ok1, used = check_html(html)
    print("[2/3] class 可溯源（pages/ style 块 + design/*.css）")
    ok2 = check_classes(used, class_defs())
    print("[3/3] 注入 CSS 与 pages/ 原文 diff")
    ok3 = check_css_verbatim(html)
    res = ok1 and ok2 and ok3
    print("── 自检结果：%s" % ("三项全过 PASS" if res else "FAIL"))
    sys.exit(0 if res else 1)


if __name__ == "__main__":
    main()
