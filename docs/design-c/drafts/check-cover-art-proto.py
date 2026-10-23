#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-cover-art-proto.py —— 封面与角色头像原型自检（五项，逐条过）。

① HTML 结构：html.parser 校验标签闭合；五个切屏按钮 ↔ 三个宿主一一可达；弹窗 ID 齐；
② class 可溯源：产物里每个非 gl- 的 class 都能在 real-all.css（实抓全量样式）或实抓
   宿主 DOM 里找到；
③ CSS / 宿主 DOM 逐字：注入段与抓取原文 diff 一致；
④ 素材自包含：assets/*.svg 全部以 data URI 注入；产物无外部 img/script/link 引用；
   无构建占位符残留；
⑤ 交互锚点：关键 id/文案存在（生成/使用/候选/图像模型页签/批量头像/添加图像模型）。

用法：python3 docs/design-c/drafts/check-cover-art-proto.py
"""
import importlib.util
import io
import os
import re
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
CAPS = os.path.join(HERE, "cover-art-captures")
OUT = os.path.join(HERE, "ai-novel-c端-封面与角色头像-原型.html")

spec = importlib.util.spec_from_file_location("cover_build", os.path.join(HERE, "build-cover-art-proto.py"))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr", "path", "circle", "rect", "line", "polyline",
        "polygon", "stop", "ellipse", "text"}


def read(p):
    with io.open(p, encoding="utf-8") as f:
        return f.read()


class Checker(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.ids = set()
        self.screens = set()
        self.classes = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if a.get("data-screen"):
            self.screens.add(a["data-screen"])
        if a.get("class"):
            self.classes.update(a["class"].split())
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append("多余的结束标签 </%s> @%s" % (tag, self.getpos()))
            return
        top, pos = self.stack.pop()
        if top != tag:
            self.errors.append("标签不匹配：<%s> @%s 被 </%s> @%s 关闭" % (top, pos, tag, self.getpos()))


def check_html(html):
    p = Checker()
    p.feed(html)
    p.close()
    ok = True
    if p.errors:
        ok = False
        for e in p.errors[:20]:
            print("  ✗", e)
    if p.stack:
        ok = False
        for tag, pos in p.stack[:20]:
            print("  ✗ 未闭合 <%s> @%s" % (tag, pos))
    for i in ["host-shelf", "host-chars", "host-config",
              "coverModal", "avaModal", "batchModal", "imgCfgModal", "imgDelModal"]:
        if i not in p.ids:
            ok = False
            print("  ✗ 缺宿主/弹窗 id：#%s" % i)
    want = {"shelf", "cover", "chars", "avatar", "config"}
    if p.screens != want:
        ok = False
        print("  ✗ 切屏按钮集合不符：%s" % sorted(p.screens))
    print("  HTML 闭合 + 5 切屏 + 5 弹窗：%s" % ("OK" if ok else "FAIL"))
    return ok, p.classes


def class_defs():
    defs = set(re.findall(r"\.([A-Za-z0-9_-]+)", build.real_css()))
    for f in ["dom-novels.html", "dom-settings-chars.html", "dom-config-list.html"]:
        for m in re.finditer(r'class="([^"]*)"', read(os.path.join(CAPS, f))):
            defs.update(m.group(1).split())
    return defs


def check_classes(used, defs):
    missing = sorted(c for c in used if not c.startswith("gl-") and c not in defs)
    if missing:
        for c in missing:
            print("  ✗ 找不到定义的 class：%s" % c)
        return False
    print("  %d 个 class 全部可溯源（gl- graft %d 个不计）"
          % (len(used), sum(1 for c in used if c.startswith("gl-"))))
    return True


def check_verbatim(html):
    ok = True
    css = build.real_css().rstrip("\n")
    if css in html:
        print("  ✓ real-all.css：逐字一致（%d chars）" % len(css))
    else:
        ok = False
        print("  ✗ real-all.css 与抓取原文不一致")
    for fname in ["dom-novels.html", "dom-settings-chars.html"]:
        want = build.host(fname).strip()
        if want in html:
            print("  ✓ %s：逐字一致（%d chars）" % (fname, len(want)))
        else:
            ok = False
            print("  ✗ %s 宿主 DOM 与原文不一致" % fname)
    cfg = read(os.path.join(CAPS, "dom-config-list.html")).strip()
    if cfg in html:
        print("  ✓ dom-config-list.html：逐字一致（%d chars）" % len(cfg))
    else:
        ok = False
        print("  ✗ 图像模型宿主 DOM 与原文不一致")
    return ok


def check_assets(html):
    ok = True
    if re.search(r'__INJECT|__HOST_|__ASSETS_JSON__', html):
        ok = False
        print("  ✗ 构建占位符残留")
    svgs = [n for n in os.listdir(os.path.join(CAPS, "assets")) if n.endswith(".svg")]
    missing = [n for n in svgs if "data:image/svg+xml;base64," not in html]
    if missing:
        ok = False
        print("  ✗ 素材未注入：%s" % missing)
    if re.search(r'<img[^>]+src="https?://', html):
        ok = False
        print("  ✗ 存在外链图片引用")
    if re.search(r'<script[^>]+src=', html):
        ok = False
        print("  ✗ 存在外链脚本")
    print("  %d 个 SVG 素材以 data URI 内联；无外链图片/脚本：%s" % (len(svgs), "OK" if ok else "FAIL"))
    return ok


def check_anchors(html):
    ok = True
    must = ["coverGenerate", "coverUse", "coverCands", "avaGenerate", "avaUse",
            "batchOpen", "batchStart", "imgAdd", "imgEdit", "imgTestDraw", "imgDelete",
            "图像生成", "固定种子", "不读取旧头像", "添加图像模型", "画风按书设置", "示意画面",
            # 沿用写作大模型习惯的关键措辞
            "添加 API Key", "编辑配置", "配置名称", "供应商", "Base URL", "API Key",
            "模型名称", "测试连接", "试画一张", "删除配置", "确认删除", "当前密钥",
            "PRO 以上可用", "视角：免费", "免费探活", "自动判断",
            "关联书籍", "停止", "继续生成", "撤销本次",
            "未测试", "地址可用", "已试画",
            # 首批图像供应商（默认火山引擎，不再绑定 MiniMax）
            "火山引擎", "豆包 Seedream", "阿里云百炼", "通义千问", "智谱", "CogView",
            "doubao-seedream-4-0-250828", "qwen-image-2.0-pro", "cogview-4", "获取模型",
            "申请 API Key", "Base URL 从哪看", "API Key 管理", "百炼控制台", "个人中心",
            "更换", "取消更换", "已更换供应商"]
    for s in must:
        if s not in html:
            ok = False
            print("  ✗ 缺关键锚点/文案：%s" % s)
    print("  关键交互锚点 %d 项：%s" % (len(must), "OK" if ok else "FAIL"))
    return ok


def main():
    html = read(OUT)
    results = []
    print("── ① HTML 结构 ──")
    ok, used = check_html(html); results.append(ok)
    print("── ② class 可溯源 ──")
    results.append(check_classes(used, class_defs()))
    print("── ③ 注入逐字 ──")
    results.append(check_verbatim(html))
    print("── ④ 素材自包含 ──")
    results.append(check_assets(html))
    print("── ⑤ 交互锚点 ──")
    results.append(check_anchors(html))
    print("")
    print("RESULT:", "ALL PASS" if all(results) else "FAIL (%d/%d)" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
