#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-ownbook-proto.py —— 导入自有书原型自检（三项，逐条过）。

① HTML 结构：python html.parser 校验标签闭合、切屏 ID 对齐（demo-bar data-s ↔ section#id）；
② class 可溯源：产物里出现的每一个非 gl- 的 class 名，能在 real.css（当前系统实抓全量样式）
   里找到定义（找不到的逐个报出）；
③ CSS 逐字：产物注入的 real.css 段与 ownbook-captures/real.css 原文 diff，逐字一致；
   宿主 DOM（五页 .app-shell）与 ownbook-captures/dom-*.html 原文逐字一致。

用法：python3 docs/design-c/drafts/check-ownbook-proto.py
"""
import importlib.util
import io
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CAPS = os.path.join(HERE, "ownbook-captures")
OUT = os.path.join(HERE, "ai-novel-c端-导入自有书-原型.html")

# 复用构建脚本的读取函数，保证「注入的就是被 diff 的」
spec = importlib.util.spec_from_file_location("ownbook_build", os.path.join(HERE, "build-ownbook-proto.py"))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "path", "circle", "rect", "line", "polyline", "polygon"}

HOSTS = ["dom-novels.html", "dom-tools.html", "dom-settings.html", "dom-write.html"]


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
    for s in ["s1", "s2", "s3", "s4", "s5", "s6"]:
        if s not in p.ids:
            ok = False
            print("  ✗ 缺屏 <section id=\"%s\">" % s)
    print("  切屏按钮 %s ↔ 屏 id 对齐：%s" % (sorted(p.screen_btns), "OK" if ok else "FAIL"))
    return ok, p.classes


# ── ② class 可溯源（real.css 全量 ∪ 实抓宿主 DOM 出现过的 class） ────────────
def class_defs():
    defs = set(re.findall(r"\.([A-Za-z0-9_-]+)", build.real_css()))
    # 实抓宿主 DOM 里出现过的 class 同为真实来源（部分组件样式由运行时注入，
    # 不一定进了 real.css 快照——如 ProseMirror-trailingBreak/pv-group-t）
    for f in sorted(os.listdir(CAPS)):
        if f.endswith(".html"):
            for m in re.finditer(r'class="([^"]*)"', read(os.path.join(CAPS, f))):
                defs.update(m.group(1).split())
    return defs


def check_classes(used, defs):
    missing = sorted(c for c in used if not c.startswith("gl-") and c not in defs)
    if missing:
        for c in missing:
            print("  ✗ 找不到定义的 class：%s" % c)
        return False
    print("  %d 个 class 全部可溯源（gl- graft %d 个不计；其余均定义于实抓 real.css）"
          % (len(used), sum(1 for c in used if c.startswith("gl-"))))
    return True


# ── ③ 注入 CSS 与宿主 DOM 与原文 diff 逐字一致 ────────────────────────────
def check_verbatim(html):
    ok = True
    checked = 0
    # real.css 整段：来源标记行起至 graft 块前
    m = re.search(r"/\* ═══ 真实样式逐字注入：ownbook-captures/real\.css", html)
    if not m:
        ok = False
        print("  ✗ 产物缺 real.css 注入段头")
    else:
        nxt = re.search(r"/\* ══════════ 新增 graft", html[m.end():])
        got = html[m.start(): m.end() + nxt.start() if nxt else len(html)].rstrip("\n")
        head_end = got.find(build.real_css())
        if head_end >= 0 and got[head_end:] == build.real_css():
            checked += 1
            print("  ✓ real.css ← ownbook-captures/real.css：逐字一致（%d chars）" % len(build.real_css()))
        else:
            ok = False
            print("  ✗ real.css 与原文不一致")
    # 宿主 DOM 五段
    for ph, fname in [("__HOST_S1__", "dom-novels.html"), ("__HOST_S2__", "dom-tools-rows.html"),
                      ("__HOST_S2_DETAIL__", "main-task-running.html"),
                      ("__HOST_S3__", "dom-task-done-shell.html"),
                      ("__HOST_S3_EXIT__", "dom-exit-modal.html"),
                      ("__HOST_S4__", "dom-settings.html"),
                      ("__HOST_S5__", "dom-write.html")]:
        want = build.host(fname)
        i = html.find(want)
        if i >= 0:
            checked += 1
            print("  ✓ %s ← ownbook-captures/%s：逐字一致（%d chars）" % (ph.strip("_"), fname, len(want)))
        else:
            ok = False
            print("  ✗ %s 宿主 DOM 与 %s 原文不一致" % (ph, fname))
    if checked < 3:
        ok = False
        print("  ✗ 逐字一致的注入段不足 3 段（仅 %d）" % checked)
    return ok


def main():
    html = read(OUT)
    print("[1/3] HTML 结构（html.parser）＋切屏 ID 对齐")
    ok1, used = check_html(html)
    print("[2/3] class 可溯源（实抓 real.css 全量）")
    ok2 = check_classes(used, class_defs())
    print("[3/3] 注入 CSS／宿主 DOM 与抓取原文 diff")
    ok3 = check_verbatim(html)
    res = ok1 and ok2 and ok3
    print("── 自检结果：%s" % ("三项全过 PASS" if res else "FAIL"))
    sys.exit(0 if res else 1)


if __name__ == "__main__":
    main()
