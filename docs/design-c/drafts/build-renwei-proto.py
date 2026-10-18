#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-renwei-proto.py —— 人味检测原型：真机抓取逐字注入（v3，2026-10-17）。

范式（design-c-proto-real-ui-basis v3）：
  源模板  drafts/ai-novel-c端-人味检测-原型.src.html（留占位符＋<template> 嫁接）
  产物    drafts/ai-novel-c端-人味检测-原型.html（自包含单文件）

注入内容逐字取自真机抓取（ownbook-captures/，独立栈真跑当日系统）：
  real.css       ← 逐路由累积真实样式（整文件逐字）
  dom-write.html ← .app-shell outerHTML（真机壳，逐字）
抓取 DOM 零改动；演示嫁接在源模板 <template> 中运行时挂载，不经本脚本。

配套：check-renwei-demo.py --assert 校验演示正文与内嵌指标数值一致（数字诚实钉）。

用法：python3 docs/design-c/drafts/build-renwei-proto.py
"""
import io
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PAGES = os.path.join(ROOT, "docs", "design-c", "pages")
DRAFTS = os.path.join(ROOT, "docs", "design-c", "drafts")
SRC = os.path.join(DRAFTS, "ai-novel-c端-人味检测-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-人味检测-原型.html")
CAPS = os.path.join(DRAFTS, "ownbook-captures")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def cap(name):
    return read(os.path.join(CAPS, name))


def main():
    inject = {
        "/*__INJECT_REAL_CSS__*/": cap("real.css").strip(),
        "<!--__INJECT_SHELL__-->": cap("dom-write.html").strip(),
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
