#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-cover-art-proto.py —— 封面与角色头像原型：当前真实系统抓取物逐字注入（v3）。

抓取（2026-10-22，独立栈＝main d4bf73fa：vite:5291 → uvicorn:8101，
DATA_ROOT=/tmp/cover-proto-data，Playwright 真渲染）产物在 cover-art-captures/：
  real-all.css            全部真实样式（305KB，无外部 url 引用）
  dom-novels.html         书架页 .app-shell（真顶栏/书卡/状态栏）
  dom-settings-chars.html 书内设定 → 角色 .app-shell（真三栏＋角色列表＋陈屿详情）
  shot-*.png              抓取时截图，仅评审参照，不参与构建
  assets/*.svg            演示画面（gen-cover-art-assets.py 生成；非真实模型输出）

注入（占位符替换、幂等可重放；样式与宿主 HTML 一字不改）：
  /*__INJECT_STYLE_REAL__*/  ← real-all.css 整体逐字
  <!--__HOST_SHELF__-->      ← dom-novels.html
  <!--__HOST_CHARS__-->      ← dom-settings-chars.html
  <!--__HOST_CONFIG__-->     ← modelconfig-captures/dom-config-list.html
  /*__ASSETS_JSON__*/        ← assets/*.svg → data:image/svg+xml;base64 映射
graft（新增件）全在源模板：gl- 前缀样式＋运行时注入脚本（抓取 DOM 零改动）。

用法：python3 docs/design-c/drafts/build-cover-art-proto.py
"""
import base64
import io
import json
import os

DRAFTS = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(DRAFTS, "cover-art-captures")
ASSETS = os.path.join(CAPS, "assets")
SRC = os.path.join(DRAFTS, "ai-novel-c端-封面与角色头像-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-封面与角色头像-原型.html")
CONFIG_DOM = os.path.join(CAPS, "dom-config-list.html")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def real_css():
    return read(os.path.join(CAPS, "real-all.css"))


def host(name):
    return read(os.path.join(CAPS, name))


def assets_js():
    out = {}
    for name in sorted(os.listdir(ASSETS)):
        if not name.endswith(".svg"):
            continue
        raw = open(os.path.join(ASSETS, name), "rb").read()
        out[name[:-4]] = "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")
    return json.dumps(out, ensure_ascii=False, indent=2)


def main():
    inject = {
        "/*__INJECT_STYLE_REAL__*/": (
            "/* ═══ 真实样式逐字注入：cover-art-captures/real-all.css（2026-10-22 自真跑系统抓取，"
            "main d4bf73fa；一字未改） ═══ */\n" + real_css().rstrip("\n")
        ),
        "<!--__HOST_SHELF__-->": host("dom-novels.html").strip(),
        "<!--__HOST_CHARS__-->": host("dom-settings-chars.html").strip(),
        "<!--__HOST_CONFIG__-->": read(CONFIG_DOM).strip(),
        "/*__ASSETS_JSON__*/": assets_js(),
    }
    html = read(SRC)
    for ph in inject:
        assert ph in html, "placeholder missing: " + ph
    for ph, body in inject.items():
        html = html.replace(ph, body)
    assert "__INJECT" not in html and "__HOST_" not in html and "__ASSETS_JSON__" not in html, "placeholder left in output"

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("injected OK -> %s (%d bytes)" % (OUT, len(html.encode("utf-8"))))
    for ph, body in inject.items():
        label = ph.strip("/*").strip("<>").strip("/")
        print("  %-28s %9d chars" % (label, len(body)))


if __name__ == "__main__":
    main()
