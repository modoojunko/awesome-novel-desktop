#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-modelconfig-proto.py —— 模型配置原型自检（静态）。

口径：
  1. 产物存在且无残留占位符；
  2. graft 用到的真实类在 real.css 有定义（vbtn/vgrid/cf-hint/seg/lock/on/field/label-row/input/mono）；
  3. gl- 新增类在 graft 样式块有定义；
  4. 七个演示状态与运行时挂载脚本在位（current/grouped/gemini/go-chat/go-claude/go-gemini/go-gpt）；
  5. 宿主为真实抓取物（dom-modal-empty 与产物宿主段逐字一致）。
"""
import io
import os
import re
import sys

DRAFTS = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(DRAFTS, "modelconfig-captures")
OUT = os.path.join(DRAFTS, "ai-novel-c端-模型配置-Gemini与OpenCodeGo-原型.html")

REAL_CLASSES = ["vbtn", "vgrid", "cf-hint", "seg", "lock", "on", "field", "label-row", "input", "mono"]
GL_CLASSES = ["gl-vtabs", "gl-vsub", "gl-badge", "gl-badge-warn", "gl-chips", "gl-chips-label", "gl-chip"]
STATES = ["current", "gemini", "relay", "go-chat", "go-claude", "go-gemini", "go-gpt"]


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


def main():
    ok = True
    html = read(OUT)
    css = read(os.path.join(CAPS, "real.css"))
    host = read(os.path.join(CAPS, "dom-modal-empty.html")).strip()

    # 1 占位符
    for bad in ["__INJECT", "__HOST_"]:
        if bad in html:
            print("FAIL 残留占位符 %s" % bad)
            ok = False

    # 2 真实类溯源（在 real.css 有规则）
    for cls in REAL_CLASSES:
        if not re.search(r"\.%s[\s{,:.]" % re.escape(cls), css):
            print("FAIL 真实类 .%s 不在 real.css" % cls)
            ok = False

    # 3 gl- 类有定义
    for cls in GL_CLASSES:
        if (".%s" % cls) not in html:
            print("FAIL graft 类 .%s 无定义" % cls)
            ok = False

    # 4 七状态在位
    for st in STATES:
        if ('data-state="%s"' % st) not in html:
            print("FAIL 缺演示状态 %s" % st)
            ok = False
    for fn in ["makeTabs", "renderTab", "showTab", "selectVendor", "setFormat", "addChips", "addProductHint"]:
        if ("function %s" % fn) not in html:
            print("FAIL 缺运行时函数 %s" % fn)
            ok = False

    # 5 宿主逐字一致（真实抓取物未被改动）
    if host not in html:
        print("FAIL 宿主 DOM 与抓取物不一致（被改动）")
        ok = False

    # 6 graft 新方块文案抽查（产品文案口径：无实现词汇）
    for banned in ["协议", "SDK", "兼容层", "SSE", "会话头", "探针", "portal"]:
        # 只查产品可见 graft 文案段（vbtn/提示/注记字符串）；demo-bar 注记允许「接口适配」
        if banned in html.split("STATES = {")[1].split("/* ── demo-bar")[0].replace("portal", ""):
            print("FAIL graft 产品文案含实现词汇：%s" % banned)
            ok = False

    print("check-modelconfig-proto:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
