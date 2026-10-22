#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-prose-paper-proto.py —— 正文纸张原型：当前真实系统抓取物逐字注入（v3）。

抓取（2026-10-22，独立栈＝main d4bf73fa：vite:5293 → uvicorn:8103，
DATA_ROOT=/tmp/prose-paper-data，Playwright 真渲染）产物在 prose-paper-captures/：
  real.css   全部真实样式（282KB，无外部 url 引用）
  dom-read.html  正文页签·阅读态真实 .app-shell
  dom-edit.html  正文页签·编辑态真实 .app-shell
  shot-*.png     抓取时截图，仅评审参照，不参与构建

注入（占位符替换、幂等可重放；样式与宿主 HTML 一字不改）：
  /*__INJECT_STYLE_REAL__*/  ← real.css 整体逐字
  <!--__HOST_READ__-->        ← dom-read.html（装进 <template>，运行时挂载）
  <!--__HOST_EDIT__-->        ← dom-edit.html
graft（新增件）全在源模板：pp- 前缀样式＋运行时注入脚本（抓取 DOM 零改动）。

用法：python3 docs/design-c/drafts/build-prose-paper-proto.py
"""
import io
import os

DRAFTS = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(DRAFTS, "prose-paper-captures")
SRC = os.path.join(DRAFTS, "ai-novel-c端-正文纸张-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-正文纸张-原型.html")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def real_css():
    return read(os.path.join(CAPS, "real.css"))


def host(name):
    return read(os.path.join(CAPS, name))


def main():
    inject = {
        "/*__INJECT_STYLE_REAL__*/": (
            "/* ═══ 真实样式逐字注入：prose-paper-captures/real.css（2026-10-22 自真跑系统抓取，"
            "main d4bf73fa；一字未改） ═══ */\n" + real_css().rstrip("\n")
        ),
        "<!--__HOST_READ__-->": host("dom-read.html").strip(),
        "<!--__HOST_EDIT__-->": host("dom-edit.html").strip(),
    }
    html = read(SRC)
    for ph in inject:
        assert ph in html, "placeholder missing: " + ph
    for ph, body in inject.items():
        html = html.replace(ph, body)
    assert "__INJECT" not in html and "__HOST_" not in html, "placeholder left in output"

    # 宿主装进 <template>：抓取 DOM 里不得出现 </script>（否则会提前截断脚本块）
    for name in ("dom-read.html", "dom-edit.html"):
        assert "</script" not in host(name).lower(), name + " 含 </script>，不能放进 <template>"

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("injected OK -> %s (%d bytes)" % (OUT, len(html.encode("utf-8"))))
    for ph, body in inject.items():
        label = ph.strip("/*").strip("<>").strip("/")
        print("  %-28s %9d chars" % (label, len(body)))


if __name__ == "__main__":
    main()
