#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-import-own-book.py —— 导入自有书原型：**当前真实系统**抓取物逐字注入（v3，真界面基线）。

抓取（2026-10-17，独立栈＝worktree@origin/main 1e53d6eb：vite:5291 → uvicorn:8101，
DATA_ROOT=/tmp/ownbook-data，Playwright 真渲染）产物在 import-own-book-captures/：
  real.css           全部真实样式（dev 注入的 <style> 串联，262KB，无外部 url 引用）
  dom-novels.html    书架页 .app-shell（真实顶栏：写作工具▾＋账号菜单；真实 notice；真实书卡）
  dom-tools-rows.html 写作工具 · 任务清单页 .app-shell（真实任务行）
  dom-settings.html  书内设定页 .app-shell（真实三栏设定壳＋8 个 s-item「未填」）
  dom-write.html     书内写作页 .app-shell（真实目录/编辑器/右栏）
  import-modal.html  真实导入弹窗壳（.scrim/.modal/.mcard/.mcard-head，serif 标题＋真实关闭图标）

注入（占位符替换、幂等可重放；样式与宿主 HTML 一字不改）：
  /*__INJECT_STYLE_REAL__*/   ← real.css 整体逐字
  /*__INJECT_SCRIPT_ICONS__*/ ← 图标表 P + render()（pages/works.html 同源图标表，仅供 graft 件用）
  <!--__HOST_S1__..__HOST_S5__--> ← 上述 DOM 片段整体逐字
graft（新增件）全在源模板：gl- 前缀样式＋演示内容＋运行时注入脚本（把 graft 节点
放进真实宿主的挂载点，抓取 HTML 本身零改动）。

刷新抓取：起同款独立栈后重跑 /tmp/capture-ownbook.cjs + /tmp/capture-settings.cjs
（脚本见本文件目录 git 历史或流程整理 §10）。

用法：python3 docs/design-c/prototypes/build-import-own-book.py
"""
import io
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PAGES = os.path.join(ROOT, "docs", "design-c", "pages")
CAPS = os.path.join(HERE, "import-own-book-captures")
SRC = os.path.join(HERE, "import-own-book.src.html")
OUT = os.path.join(HERE, "import-own-book.html")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def real_css():
    return read(os.path.join(CAPS, "real.css")).rstrip("\n")


def host(name):
    return read(os.path.join(CAPS, name)).strip()


def icons_js_of():
    """图标表 P + render()：逐字取自 pages/works.html（与真机 Ico 组件同源图标表），供 graft 件渲染。"""
    html = read(os.path.join(PAGES, "works.html"))
    m = re.search(r"var P = (\{.*?\});\s*\n\s*function render\(el\) \{(.*?)\n  \}", html, re.S)
    assert m, "icon map not found in works.html"
    return (
        "var P = " + m.group(1) + ";\n"
        "  function render(el) {" + m.group(2) + "\n  }\n"
        "  window.__renderIcons = function (root) { (root || document).querySelectorAll('i[data-ico]').forEach(render); };\n"
        "  window.__renderIcons();\n"
    )


def main():
    inject = {
        "/*__INJECT_STYLE_REAL__*/": (
            "/* ═══ 真实样式逐字注入：import-own-book-captures/real.css（2026-10-17 自真跑系统抓取，"
            "worktree@origin/main 1e53d6eb；一字未改） ═══ */\n" + real_css()
        ),
        "/*__INJECT_SCRIPT_ICONS__*/": icons_js_of(),
        "<!--__HOST_S1__-->": host("dom-novels.html"),
        "<!--__HOST_S2__-->": host("dom-tools-rows.html"),
        "<!--__HOST_S3__-->": host("dom-task-done-shell.html"),
        "<!--__HOST_S4__-->": host("dom-settings.html"),
        "<!--__HOST_S5__-->": host("dom-write.html"),
        "<!--__HOST_S2_DETAIL__-->": host("main-task-running.html"),
        "<!--__HOST_S3_EXIT__-->": host("dom-exit-modal.html"),
    }

    html = read(SRC)
    for ph in inject:
        assert ph in html, "placeholder missing in src: " + ph
    for ph, body in inject.items():
        html = html.replace(ph, body)
    assert "__INJECT" not in html and "__HOST_S" not in html, "placeholder left in output"

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("injected OK -> %s (%d bytes)" % (OUT, len(html)))
    for ph, body in inject.items():
        print("  %-36s %7d chars" % (ph.strip("/*").strip("<>"), len(body)))


if __name__ == "__main__":
    main()
