#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-thinkproto-proto.py —— 思考呈现原型（正文工作台）：
**当前真实系统**抓取物逐字注入（v3，真界面基线）。

抓取（2026-10-20，独立栈＝worktree@origin/main 933cd79b：vite:5317 → uvicorn:8317，
DATA_ROOT=/tmp/proto-think-data，假 MiniMax(anthropic 流式:8318) 驱动真实生成 UI，
Playwright 真渲染）产物在 thinkproto-captures/：
  css-workbench-editing.css   全部真实样式（dev 注入 <style> 串联，五态抓取 md5 一致）
  dom-workbench-editing.html  编辑态 .app-shell（正文＋工具行）
  dom-wait-thinking.html      生成中·思考期（gen-line「模型思考中，等待首字 · 9s」）
  dom-mid-writing.html        生成中·写作期（正文流式写入中，顶条「AI 正在生成…·停止」）
  dom-done-editing.html       生成完成编辑态（含「字数未达标」条）
  dom-workbench-reading.html  阅读态

注入（占位符替换、幂等可重放；样式与宿主 HTML 一字不改）：
  /*__INJECT_STYLE_REAL__*/   ← real.css 整体逐字
  <!--__HOST_EDITING__-->     ← dom-workbench-editing.html 逐字
  <!--__HOST_THINKING__-->    ← dom-wait-thinking.html 逐字
  <!--__HOST_WRITING__-->     ← dom-mid-writing.html 逐字
  <!--__HOST_DONE__-->        ← dom-done-editing.html 逐字
  <!--__HOST_READING__-->     ← dom-workbench-reading.html 逐字
graft（tk- 前缀＋proto- 演示条）全在源模板。

用法：python3 docs/design-c/drafts/build-thinkproto-proto.py
"""
import io
import os

DRAFTS = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(DRAFTS, "thinkproto-captures")
SRC = os.path.join(DRAFTS, "ai-novel-c端-思考呈现-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-思考呈现-原型.html")

INJECTS = [
    ("/*__INJECT_STYLE_REAL__*/", "css-workbench-editing.css"),
    ("<!--__HOST_EDITING__-->", "dom-workbench-editing.html"),
    ("<!--__HOST_THINKING__-->", "dom-wait-thinking.html"),
    ("<!--__HOST_WRITING__-->", "dom-mid-writing.html"),
    ("<!--__HOST_DONE__-->", "dom-done-editing.html"),
    ("<!--__HOST_READING__-->", "dom-workbench-reading.html"),
]


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def main():
    html = read(SRC)
    for ph, fname in INJECTS:
        assert ph in html, "placeholder missing in src: " + ph
        body = read(os.path.join(CAPS, fname)).strip()
        html = html.replace(ph, body)
    assert "__INJECT" not in html and "__HOST_" not in html, "placeholder left in output"
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("injected OK -> %s (%d bytes)" % (OUT, len(html)))
    for ph, fname in INJECTS:
        print("  %-28s %8d chars  %s" % (ph.strip("<!->"), len(read(os.path.join(CAPS, fname))), fname))


if __name__ == "__main__":
    main()
