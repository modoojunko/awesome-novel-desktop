#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-thinkproto-proto.py —— 思考呈现原型自检：
① 真实样式/宿主逐字保真（captures 内容在产物中一字不差）
② graft 类溯源：新增 class 只允许 tk-/proto-/tkdemo 白名单前缀（宿主 DOM 出现过的类不受限）
③ 原型文案实现词汇黑名单（只扫 graft 样式/脚本段，宿主原样不受限）
"""
import io
import os
import re
import sys

DRAFTS = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(DRAFTS, "thinkproto-captures")
SRC = os.path.join(DRAFTS, "ai-novel-c端-思考呈现-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-思考呈现-原型.html")

HOSTS = [
    "dom-workbench-editing.html",
    "dom-wait-thinking.html",
    "dom-mid-writing.html",
    "dom-done-editing.html",
    "dom-workbench-reading.html",
]
BLACKLIST = [
    "指纹", "基线打分", "权重", "额度", "探针", "守卫", "delta", "SSE",
    "tokens", "reasoning", "thinking_delta", "api_format", "encode",
]


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def main():
    out = read(OUT)
    src = read(SRC)
    fails = []

    # ① 逐字保真
    css = read(os.path.join(CAPS, "css-workbench-editing.css")).strip()
    if css not in out:
        fails.append("real.css 不在产物中（逐字对拍失败）")
    for h in HOSTS:
        body = read(os.path.join(CAPS, h)).strip()
        if body not in out:
            fails.append("宿主不保真: " + h)

    # ② graft 类溯源：产物中出现的 class − 真实 DOM 出现过的 class − 白名单前缀 = 违例
    real_classes = set()
    for h in HOSTS:
        real_classes |= set(re.findall(r'class="([^"]+)"', read(os.path.join(CAPS, h))))
    real_flat = set(c for chunk in real_classes for c in chunk.split())
    out_classes = set()
    for m in re.findall(r'class="([^"]+)"', out):
        out_classes |= set(m.split())
    # JS 里动态拼的类名（className= / class= 模板串）
    for m in re.findall(r'className\s*=\s*"([^"]+)"', out):
        out_classes |= set(m.split())
    for m in re.findall(r'class=\\?"([^"\\]+)\\?"', out):
        out_classes |= set(m.split())
    allowed_prefixes = ("tk-", "proto-")
    unknown = {
        c for c in out_classes - real_flat
        if not c.startswith(allowed_prefixes)
    }
    if unknown:
        fails.append("来历不明的新类: " + ", ".join(sorted(unknown)))

    # ③ 实现词汇黑名单（只扫 graft 段：src 中 </style> 之后的 <style> 块＋<script> 块）
    graft = src[src.find("graft：思考呈现"):]
    low = graft.lower()
    for w in BLACKLIST:
        if w.lower() in low:
            fails.append("graft 文案含实现词汇: " + w)

    if fails:
        print("CHECK FAIL")
        for f in fails:
            print("  -", f)
        sys.exit(1)
    print("CHECK OK — 逐字保真×%d、类溯源（+%d graft 类）、文案黑名单 全过" % (
        len(HOSTS) + 1, len(out_classes - real_flat)))


if __name__ == "__main__":
    main()
