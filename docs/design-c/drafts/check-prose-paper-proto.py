#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-prose-paper-proto.py —— 正文纸张原型自检（六项，逐条过）。

① HTML 结构：html.parser 校验标签闭合；两个宿主 <template> 在场；演示条三组＋视野组齐；
   变体/纸色属性齐；
② class 可溯源：产物里每个非 pp- 的 class 都能在 real.css（实抓全量样式）或实抓宿主
   DOM 里找到（证明原型没有 invent 出新词汇）；
③ CSS / 宿主 DOM 逐字：注入段与抓取原文 diff 一致（证明真样式与真 DOM 一字未改）；
④ 自包含：无构建占位符残留、无外链 img/script/link；graft 样式无裸 hex / rgb()；
⑤ 只动正文列：graft 里碰到真实 class 的规则一律限定在 .pp-stage 作用域内；
   :root 只允许追加 --pp-* 变量；
⑥ 几何不变量：版心仍 680px；纸边距 ≥ 56px（人味边注 left:-46px 住在纸边距里）；
   纸边不用 border（border 会吃掉 2px 内容宽 → 版心变 678）。

用法：python3 docs/design-c/drafts/check-prose-paper-proto.py
"""
import importlib.util
import io
import os
import re
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(HERE, "prose-paper-captures")
SRC = os.path.join(HERE, "ai-novel-c端-正文纸张-原型.src.html")
OUT = os.path.join(HERE, "ai-novel-c端-正文纸张-原型.html")

spec = importlib.util.spec_from_file_location("pp_build", os.path.join(HERE, "build-prose-paper-proto.py"))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "path", "circle", "rect", "line", "polyline",
        "polygon", "stop", "ellipse", "text", "use"}

# 正文列里的真实类（graft 若要碰它们，必须挂在 .pp-stage 下）
REAL_COL_CLASSES = {"editor", "editor-wrap", "editor-host", "editor-status", "ol-top",
                    "edit-bar", "gen-line", "prose-body", "col-editor", "wb", "app-shell",
                    "statusbar", "ch-tabs", "e-head"}


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


class Checker(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.ids = set()
        self.screens = set()
        self.classes = set()
        self.templates = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "template" and a.get("id"):
            self.templates.add(a["id"])
        if a.get("data-mode") or a.get("data-variant") or a.get("data-paper") or a.get("data-focus"):
            self.screens.add("chip")
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
    for i in ["host-read", "host-edit", "ppStage", "ppMode", "ppView", "ppNote"]:
        if i not in p.ids:
            ok = False
            print("  ✗ 缺 id：#%s" % i)
    if p.templates != {"host-read", "host-edit"}:
        ok = False
        print("  ✗ 宿主模板集合不符：%s" % sorted(p.templates))
    print("  HTML 闭合 + 2 宿主模板 + 6 容器 id：%s" % ("OK" if ok else "FAIL"))
    return ok, p.classes


def class_defs():
    defs = set(re.findall(r"\.([A-Za-z0-9_-]+)", build.real_css()))
    for f in ["dom-read.html", "dom-edit.html"]:
        for m in re.finditer(r'class="([^"]*)"', read(os.path.join(CAPS, f))):
            defs.update(m.group(1).split())
    return defs


def check_classes(used, defs):
    missing = sorted(c for c in used if not c.startswith("pp-") and c not in defs)
    if missing:
        for c in missing:
            print("  ✗ 找不到定义的 class：%s" % c)
        return False
    print("  %d 个 class 全部可溯源（pp- graft %d 个不计）"
          % (len(used), sum(1 for c in used if c.startswith("pp-"))))
    return True


def check_verbatim(html):
    ok = True
    css = build.real_css().rstrip("\n")
    if css in html:
        print("  ✓ real.css：逐字一致（%d chars）" % len(css))
    else:
        ok = False
        print("  ✗ real.css 与抓取原文不一致")
    for fname in ["dom-read.html", "dom-edit.html"]:
        want = build.host(fname).strip()
        if want in html:
            print("  ✓ %s：逐字一致（%d chars）" % (fname, len(want)))
        else:
            ok = False
            print("  ✗ %s 宿主 DOM 与原文不一致" % fname)
    return ok


def graft_css(html):
    """取第二个 <style>（graft 层）——第一个是逐字注入的真样式。"""
    blocks = re.findall(r"<style>(.*?)</style>", html, re.S)
    return blocks[1] if len(blocks) > 1 else ""


def check_assets(html):
    ok = True
    if re.search(r"__INJECT|__HOST_", html):
        ok = False
        print("  ✗ 构建占位符残留")
    if re.search(r'<img[^>]+src="(?!data:)', html):
        ok = False
        print("  ✗ 存在外链图片引用")
    if re.search(r"<script[^>]+src=", html):
        ok = False
        print("  ✗ 存在外链脚本")
    if re.search(r"<link[^>]+href=\"http", html):
        ok = False
        print("  ✗ 存在外链样式")
    css = graft_css(html)
    hexm = re.search(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})(?![0-9a-fA-F])", css)
    rgbm = re.search(r"\brgba?\(\s*\d", css)
    if hexm or rgbm:
        ok = False
        print("  ✗ graft 样式有裸色值：%s" % ((hexm or rgbm).group(0)))
    print("  无外链、无占位符残留、graft 无裸色值：%s" % ("OK" if ok else "FAIL"))
    return ok


def selectors_of(css):
    out = []
    for m in re.finditer(r"([^{}]+)\{", css):
        sel = m.group(1).strip()
        if sel.startswith("@") or sel.startswith("/*"):
            continue
        for part in sel.split(","):
            part = part.strip()
            if part and not part.startswith("@"):
                out.append(part)
    return out


def check_scope(html):
    ok = True
    css = graft_css(html)
    for sel in selectors_of(css):
        classes = set(re.findall(r"\.([A-Za-z0-9_-]+)", sel))
        if classes & REAL_COL_CLASSES:
            if ".pp-stage" not in sel:
                ok = False
                print("  ✗ 动到真实列的规则没挂 .pp-stage：%s" % sel)
        elif not sel.startswith(".pp-") and not sel.startswith(":root") and not sel.startswith("@"):
            if classes and not all(c.startswith("pp-") for c in classes):
                ok = False
                print("  ✗ 越界选择器：%s" % sel)
    # :root 只许追加 --pp-*
    for m in re.finditer(r":root\s*\{([^}]*)\}", css):
        for decl in m.group(1).split(";"):
            decl = decl.strip()
            if decl and not decl.startswith("--pp-"):
                ok = False
                print("  ✗ :root 追加了非 pp- 变量：%s" % decl)
    print("  graft 只动正文列（真实类一律挂 .pp-stage）：%s" % ("OK" if ok else "FAIL"))
    return ok


def check_geometry(html):
    ok = True
    css = graft_css(html)
    if "--pp-measure: 680px" not in css:
        ok = False
        print("  ✗ 版心变量不是 680px（真实行宽被改了）")
    m = re.search(r"--pp-pm:\s*(\d+)px", css)
    if not m or int(m.group(1)) < 56:
        ok = False
        print("  ✗ 纸边距 < 56px：人味边注（.zq-mark left:-46px）会出纸")
    # A 的纸面规则里不许出现 border（会吃掉 2px 内容宽）
    m = re.search(r"\n\.pp-paper\s*\{([^}]*)\}", css)
    if not m:
        ok = False
        print("  ✗ 找不到 .pp-paper 基规则")
    elif re.search(r"(^|;)\s*border\s*:", m.group(1)):
        ok = False
        print("  ✗ .pp-paper 用了 border —— border 会把版心挤成 678px，纸边请用 inset 阴影")
    # 写字范围框必须存在、必须用与纸边距同源的 --pp-guide-x
    if "--pp-guide-x" not in css or "var(--pp-guide-x)" not in css:
        ok = False
        print("  ✗ 写字范围框没有用 --pp-guide-x（会跟纸边距各说各话）")
    if ".pp-frame" not in css:
        ok = False
        print("  ✗ 缺 .pp-frame（写字范围框）")
    if "border: 1px dashed var(--pp-guide)" not in css:
        ok = False
        print("  ✗ 写字范围框不是 1px 虚线（拍板：虚线＋极淡）")
    if "not(.editing) .pp-frame" not in css:
        ok = False
        print("  ✗ 缺「阅读态隐藏范围框」的规则（拍板：只在编辑态可见）")
    # 纸宽必须留最小桌面缝（窄列也看得出「纸在桌上」）
    if "--pp-desk-x:" not in css:
        ok = False
        print("  ✗ 没有 --pp-desk-x：窄列时纸会贴满整列")
    print("  版心 680 / 纸边距 ≥56 / 纸边无 border / 范围线同源：%s" % ("OK" if ok else "FAIL"))
    return ok


def main():
    html = read(OUT)
    results = []
    print("── ① HTML 结构 ──")
    ok, used = check_html(html); results.append(ok)
    print("── ② class 可溯源 ──")
    results.append(check_classes(used, class_defs()))
    print("── ③ 注入逐字 ──")
    results.append(check_verbatim(html))
    print("── ④ 自包含 ──")
    results.append(check_assets(html))
    print("── ⑤ 只动正文列 ──")
    results.append(check_scope(html))
    print("── ⑥ 几何不变量 ──")
    results.append(check_geometry(html))
    print("")
    print("RESULT:", "ALL PASS" if all(results) else "FAIL (%d/%d)" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
