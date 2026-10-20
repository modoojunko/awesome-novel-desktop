#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-modelconfig-proto.py —— 模型配置原型（Gemini 与 OpenCode Go）：
**当前真实系统**抓取物逐字注入（v3，真界面基线）。

抓取（2026-10-20，独立栈＝worktree@main 8bbf9459：vite:5291 → uvicorn:8101，
DATA_ROOT=/tmp/proto-mc-data，Playwright 真渲染）产物在 modelconfig-captures/：
  real.css              全部真实样式（dev 注入 <style> 串联，276KB，无外部 url 引用）
  dom-config-list.html  /config 列表态 .app-shell（两条种子配置真实渲染）
  dom-modal-empty.html  「添加 API Key」弹窗空表单（body 级宿主：弹窗为 portal）
  dom-modal-vendor.html 弹窗 GLM 选中态（预填/思考段参照）
  dom-modal-compat.html 弹窗「OpenAI 兼容」选中态（存量 Gemini 手工引导文案）

注入（占位符替换、幂等可重放；样式与宿主 HTML 一字不改）：
  /*__INJECT_STYLE_REAL__*/   ← real.css 整体逐字
  <!--__HOST_EMPTY__-->       ← dom-modal-empty.html（body 内容逐字）
graft（新增件）全在源模板：gl- 前缀样式＋运行时注入脚本（重置＝还原 pristine）。

用法：python3 docs/design-c/drafts/build-modelconfig-proto.py
"""
import io
import os

DRAFTS = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(DRAFTS, "modelconfig-captures")
SRC = os.path.join(DRAFTS, "ai-novel-c端-模型配置-Gemini与OpenCodeGo-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-模型配置-Gemini与OpenCodeGo-原型.html")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def main():
    inject = {
        "/*__INJECT_STYLE_REAL__*/": (
            "/* ═══ 真实样式逐字注入：modelconfig-captures/real.css（2026-10-20 自真跑系统抓取，"
            "worktree@main 8bbf9459；一字未改） ═══ */\n" + read(os.path.join(CAPS, "real.css")).rstrip("\n")
        ),
        "<!--__HOST_EMPTY__-->": read(os.path.join(CAPS, "dom-modal-empty.html")).strip(),
    }
    html = read(SRC)
    for ph in inject:
        assert ph in html, "placeholder missing in src: " + ph
    for ph, body in inject.items():
        html = html.replace(ph, body)
    assert "__INJECT" not in html and "__HOST_" not in html, "placeholder left in output"

    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("injected OK -> %s (%d bytes)" % (OUT, len(html)))
    for ph, body in inject.items():
        print("  %-30s %8d chars" % (ph.strip("/*").strip("<>"), len(body)))


if __name__ == "__main__":
    main()
