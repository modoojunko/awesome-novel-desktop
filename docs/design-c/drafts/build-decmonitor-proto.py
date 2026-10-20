#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-decmonitor-proto.py —— 拆书运行监控原型：**当前真实系统**抓取物逐字注入。

抓取（2026-10-19，独立栈＝worktree@分支 c-deconstruct-monitor：vite:5291 →
uvicorn:8101，DATA_ROOT=/tmp/decmon-data 私有＋DECONSTRUCT_DISPATCHER_OFF=1，
免 OAuth＝config.json＋localStorage 同 token；种子＝deconstruct_jobs＋
deconstruct_units 真形状直插，Playwright 真渲染）产物在 monitor-captures/：
  real.css         全部真实样式（dev 注入 <style> 按路由累积去重串联，无外部 url 引用）
  dom-detail.html  运行态详情页 .app-shell（真实监控面板：mon-sum/mon-pbar/mon-dims/
                   mon-speed/mon-recent/测试模型按钮——分支已实现组件的真渲染）
  shot-detail.png  整页截图（自检用）

注入（占位符替换、幂等可重放；样式与宿主 HTML 一字不改）：
  /*__INJECT_STYLE_REAL__*/  ← real.css 整体逐字
  <!--__HOST_DETAIL__-->     ← dom-detail.html 整体逐字

刷新抓取（脚本已入库同目录 monitor-captures/）：
  1. 起独立栈：uvicorn:8101（env 见 seed.py 头注释）boot 一次 →
  2. `python3 monitor-captures/seed.py`（后端 boot 后再种——DB 世代守卫）→
  3. 起 vite:5291（VITE_API_PROXY=http://127.0.0.1:8101）→
  4. `node monitor-captures/capture-detail.cjs` →
  5. 重跑本脚本。

用法：python3 docs/design-c/drafts/build-decmonitor-proto.py
"""
import io
import os

DRAFTS = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(DRAFTS, "monitor-captures")
SRC = os.path.join(DRAFTS, "ai-novel-c端-拆书监控-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-拆书监控-原型.html")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def main():
    src = read(SRC)
    css = read(os.path.join(CAPS, "real.css")).rstrip("\n")
    host = read(os.path.join(CAPS, "dom-detail.html")).strip()
    assert "url(" not in css, "real.css 含外部 url 引用——自包含被破坏"
    out = src.replace("/*__INJECT_STYLE_REAL__*/", css, 1)
    out = out.replace("<!--__HOST_DETAIL__-->", host, 1)
    assert "__INJECT_" not in out and "__HOST_" not in out, "占位符未清零"
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(out)
    print("built", OUT, len(out), "bytes")


if __name__ == "__main__":
    main()
