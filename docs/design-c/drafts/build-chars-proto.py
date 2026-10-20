#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-chars-proto.py —— 角色列表（批量添加 / 拖拽排序 / 搜索）原型：真实样式逐字注入。

范式抄 build-lightrail-proto.py（占位符替换、幂等可重放）：
  源模板  drafts/ai-novel-c端-角色批量添加与拖拽排序-原型.src.html（留占位符）
  产物    drafts/ai-novel-c端-角色批量添加与拖拽排序-原型.html（自包含单文件）

注入内容逐字取自真实样式（不手写、不近似）：
  base.css / list.css / book.css ← client/frontend/src/design/*.css 全文逐字
  （角色列表/角色卡/认知六层/弹窗 .mcard.wb-style 的真实样式都在这三份里）
新增件样式在源模板的 gl- graft 块里，不经本脚本。

用法：python3 docs/design-c/drafts/build-chars-proto.py
"""
import io
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DESIGN = os.path.join(ROOT, "client", "frontend", "src", "design")
DRAFTS = os.path.join(ROOT, "docs", "design-c", "drafts")
SRC = os.path.join(DRAFTS, "ai-novel-c端-角色批量添加与拖拽排序-原型.src.html")
OUT = os.path.join(DRAFTS, "ai-novel-c端-角色批量添加与拖拽排序-原型.html")

INJECT = [
    ("/*__INJECT_STYLE_BASE__*/", "base.css"),
    ("/*__INJECT_STYLE_LIST__*/", "list.css"),
    ("/*__INJECT_STYLE_BOOK__*/", "book.css"),
]


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def main():
    html = read(SRC)
    for token, css_name in INJECT:
        assert token in html, "placeholder missing: " + token
        body = read(os.path.join(DESIGN, css_name)).rstrip("\n")
        seg = "/* ═══ 来自 client/frontend/src/design/%s（真实样式，逐字注入） ═══ */\n%s" % (css_name, body)
        html = html.replace(token, seg)
    with io.open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("built:", OUT, "(%d bytes)" % len(html.encode("utf-8")))


if __name__ == "__main__":
    main()
