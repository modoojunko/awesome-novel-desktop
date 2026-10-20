#!/usr/bin/env python3
"""操作手册构建器：单源内容 → 双产物。

输入（本目录）：
  content/*.md  用户手册章节（front-matter: id/title/audience/capabilities/updated）
  kb/*.md       客服知识库条目（front-matter: id/q/keywords/tags/capabilities/related/updated）
                正文固定两节：`## 答案`（用户可复述）＋ `## 客服口径`（内部处理指引）

输出（dist/）：
  manual.html      用户手册单文件（侧栏目录＋本地搜索＋打印样式），可挂 CDN / 随安装包
  kb-export.md     客服知识库·人类可读版（按 tag 分组，含客服口径）
  kb-export.jsonl  客服知识库·机读版（喂 AI 客服/RAG，一条一 JSON）

保鲜门（--check）：
  每篇 front-matter 声明的 capabilities 必须是 openspec/specs/ 下真实存在的 capability——
  spec 改名/退役而手册没跟，构建门直接红。CI 或归档 change 时跑一次即可。

用法：python3 docs/manual/build.py [--check]
依赖：python3 + markdown（pip install markdown）
"""

import base64
import json
import re
import sys
from pathlib import Path

try:
    import markdown as _md
except ImportError:
    print("缺少依赖：pip install markdown", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
SPECS = REPO / "openspec" / "specs"
DIST = ROOT / "dist"

FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
SUPPORT_EMAIL = "support@xingweitouzi.cn"
BUILD_DATE = "2026-10-05"


def parse_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        raise ValueError(f"{path.name}: 缺 front-matter")
    meta = {}
    for line in m.group(1).splitlines():
        if not line.strip() or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip()
    body = text[m.end():]
    meta["_body"] = body
    for required in ("id", "updated"):
        if required not in meta:
            raise ValueError(f"{path.name}: front-matter 缺 {required}")
    meta["capabilities"] = [c.strip() for c in meta.get("capabilities", "").split(",") if c.strip()]
    meta["keywords"] = [c.strip() for c in meta.get("keywords", "").split(",") if c.strip()]
    meta["related"] = [c.strip() for c in meta.get("related", "").split(",") if c.strip()]
    return meta


CALLOUT_RE = re.compile(
    r"<blockquote>\s*<p>(说明|提示|温馨提示|注意)[：:]\s*(.*?)</p>", re.S)
_CALLOUT_CLASS = {"说明": "note", "提示": "tip", "温馨提示": "tip", "注意": "warn"}

TIER_RE = re.compile("【(免费|PRO|MAX)】")
_TIER_CLASS = {"免费": "free", "PRO": "pro", "MAX": "max"}

IMG_RE = re.compile(r'src="(img/[^"]+)"')


def render_md(body: str) -> str:
    html = _md.markdown(body, extensions=["tables", "fenced_code", "sane_lists"])
    # callout 分级：以「说明：/提示：/注意：」开头的引用块自动着色（对齐腾讯云文档写法）
    def _co(m):
        label, rest = m.group(1), m.group(2).strip()
        head = f'<p class="co-t">{label}</p>'
        return f'<blockquote class="co-{_CALLOUT_CLASS[label]}">{head}<p>{rest}</p>'
    html = CALLOUT_RE.sub(_co, html)
    # 档位徽标：【免费】【PRO】【MAX】→ 彩色徽章（权益点贯穿流程的视觉锚）
    html = TIER_RE.sub(lambda m: f'<span class="tier tier-{_TIER_CLASS[m.group(1)]}">{m.group(1)}</span>', html)
    return html


def inline_images(html: str) -> str:
    """把 img/ 引用内嵌为 base64，保住 manual.html 单文件可携带。"""
    def _embed(m):
        path = ROOT / m.group(1)
        if not path.is_file():
            return m.group(0)
        b64 = base64.b64encode(path.read_bytes()).decode()
        return f'src="data:image/png;base64,{b64}"'
    return IMG_RE.sub(_embed, html)


def split_kb_sections(body: str) -> tuple[str, str]:
    """按 `## 答案` / `## 客服口径` 切两节，缺节报错。"""
    m_ans = re.search(r"^## 答案\s*$", body, re.M)
    m_int = re.search(r"^## 客服口径\s*$", body, re.M)
    if not (m_ans and m_int and m_ans.start() < m_int.start()):
        raise ValueError("KB 正文须先 `## 答案` 后 `## 客服口径` 两节")
    return body[m_ans.end():m_int.start()].strip(), body[m_int.end():].strip()


def group_kb(kb: list[dict]) -> dict[str, list[dict]]:
    """按 tag 分组（对齐腾讯云「常见问题按主题分组」）。"""
    grouped: dict[str, list[dict]] = {}
    for k in kb:
        for t in k.get("tags", "").split(","):
            t = t.strip()
            if t:
                grouped.setdefault(t, []).append(k)
    return grouped


def load_dir(sub: str) -> list[dict]:
    docs = [parse_doc(p) for p in sorted((ROOT / sub).glob("*.md"))]
    if not docs:
        raise ValueError(f"{sub}/ 下没有内容文件")
    return docs


# ---------------------------------------------------------------- manual.html

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="author" content="爱小说">
<style>
  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; background: #f6f7f4; }}
  body {{ font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif;
         color: #1f2933; line-height: 1.8; }}
  a {{ color: #14532d; }}
  .layout {{ display: flex; min-height: 100vh; }}
  nav {{ width: 264px; flex: none; background: #ffffff; border-right: 1px solid #e4e7eb;
        padding: 28px 20px; position: sticky; top: 0; height: 100vh; overflow-y: auto; }}
  .brand {{ font-size: 17px; font-weight: 700; color: #14532d; margin-bottom: 4px; }}
  .brand-sub {{ font-size: 12.5px; color: #6b7280; margin-bottom: 18px; }}
  #q {{ width: 100%; padding: 7px 10px; border: 1px solid #d1d5db; border-radius: 8px;
       font-size: 13px; margin-bottom: 14px; }}
  nav ol {{ list-style: none; margin: 0; padding: 0; }}
  nav li {{ margin: 2px 0; }}
  nav a {{ display: block; padding: 7px 10px; border-radius: 8px; text-decoration: none;
          color: #374151; font-size: 14px; }}
  nav a:hover {{ background: #f0f7f1; }}
  nav a.kb {{ color: #6b7280; font-size: 13px; }}
  main {{ flex: 1; min-width: 0; padding: 40px 48px 80px; }}
  .sheet {{ max-width: 780px; margin: 0 auto; }}
  section.doc {{ background: #ffffff; border: 1px solid #e4e7eb; border-radius: 12px;
                padding: 32px 36px 28px; margin-bottom: 28px; }}
  h1 {{ font-size: 24px; margin: 0 0 6px; color: #14532d; }}
  h2 {{ font-size: 18px; margin: 26px 0 8px; padding-left: 10px; border-left: 4px solid #14532d; }}
  h3 {{ font-size: 15.5px; margin: 18px 0 6px; }}
  p, li {{ font-size: 14.5px; }}
  blockquote {{ margin: 12px 0; padding: 10px 14px; background: #f0f7f1;
               border-left: 3px solid #94a3b8; border-radius: 0 8px 8px 0;
               color: #374151; font-size: 13.5px; }}
  blockquote.co-note {{ background: #eff6ff; border-left-color: #3b82f6; }}
  blockquote.co-tip {{ background: #ecfdf5; border-left-color: #10b981; }}
  blockquote.co-warn {{ background: #fbf6e9; border-left-color: #d4b45a; }}
  .co-t {{ font-weight: 600; font-size: 13px; margin: 0 0 2px; }}
  .co-note .co-t {{ color: #1d4ed8; }}
  .co-tip .co-t {{ color: #047857; }}
  .co-warn .co-t {{ color: #92700c; }}
  .tier {{ display: inline-block; padding: 0 7px; border-radius: 999px;
          font-size: 11.5px; font-weight: 700; line-height: 18px;
          vertical-align: 1px; }}
  .tier-free {{ background: #f3f4f6; color: #4b5563; border: 1px solid #d1d5db; }}
  .tier-pro {{ background: #14532d; color: #ffffff; }}
  .tier-max {{ background: #d4b45a; color: #3d2f05; }}
  section.doc img {{ max-width: 100%; border: 1px solid #e4e7eb; border-radius: 10px;
                     margin: 10px 0; }}
  .figure-note {{ color: #9ca3af; font-size: 12px; margin: -4px 0 14px; }}
  .nav-tag {{ font-size: 11.5px; color: #9ca3af; padding: 10px 10px 2px;
             list-style: none; font-weight: 600; }}
  table {{ border-collapse: collapse; margin: 12px 0; width: 100%; font-size: 13.5px; }}
  th, td {{ border: 1px solid #e4e7eb; padding: 7px 10px; text-align: left; }}
  th {{ background: #f0f7f1; }}
  code {{ background: #f3f4f6; padding: 1px 5px; border-radius: 5px; font-size: 13px; }}
  .meta {{ color: #9ca3af; font-size: 12px; margin-bottom: 14px; }}
  .kb-internal {{ background: #fbf6e9; border: 1px dashed #d4b45a; border-radius: 10px;
                 padding: 4px 18px 10px; margin-top: 16px; }}
  .kb-internal::before {{ content: "客服内部口径 · 不直接回复用户"; display: block;
                        font-size: 12px; color: #92700c; font-weight: 600; margin: 10px 0 2px; }}
  .hide {{ display: none; }}
  #nohit {{ display: none; color: #6b7280; font-size: 14px; padding: 20px; }}
  footer {{ color: #9ca3af; font-size: 12.5px; text-align: center; padding: 10px 0 30px; }}
  @media (max-width: 860px) {{
    .layout {{ flex-direction: column; }}
    nav {{ width: 100%; height: auto; position: static; border-right: 0;
          border-bottom: 1px solid #e4e7eb; }}
    main {{ padding: 24px 16px 60px; }}
  }}
  @media print {{
    body {{ background: #fff; }}
    nav, #q, footer {{ display: none; }}
    main {{ padding: 0; }}
    section.doc {{ border: 0; padding: 0 0 18px; page-break-after: always; }}
  }}
</style>
</head>
<body>
<div class="layout">
  <nav>
    <div class="brand">爱小说 · 操作手册</div>
    <div class="brand-sub">写成一本完整的长篇小说</div>
    <input id="q" type="search" placeholder="搜索手册与常见问题…" autocomplete="off">
    <ol id="toc">
{toc}
    </ol>
    <div id="nohit">没有匹配的内容。</div>
  </nav>
  <main><div class="sheet">
{sections}
    <footer>爱小说操作手册 · 更新至 {date} · 问题未解决？邮件 <a href="mailto:{email}">{email}</a></footer>
  </div></main>
</div>
<script>
const q = document.getElementById('q');
const docs = Array.from(document.querySelectorAll('section.doc'));
const nohit = document.getElementById('nohit');
q.addEventListener('input', () => {{
  const v = q.value.trim().toLowerCase();
  let hits = 0;
  for (const d of docs) {{
    const on = !v || d.textContent.toLowerCase().includes(v);
    d.classList.toggle('hide', !on);
    if (on) hits++;
    document.querySelector(`#toc a[href="#${{d.id}}"]`).parentElement.classList.toggle('hide', !on);
  }}
  nohit.style.display = hits ? 'none' : 'block';
}});
</script>
</body>
</html>
"""


def build_manual(chapters: list[dict], kb: list[dict]) -> str:
    toc = []
    for c in chapters:
        toc.append(f'      <li><a href="#{c["id"]}">{c["title"]}</a></li>')
    toc.append('      <li style="margin-top:14px;font-size:12px;color:#9ca3af;padding:0 10px;">常见问题</li>')
    for tag, items in group_kb(kb).items():
        toc.append(f'      <li class="nav-tag">{tag}</li>')
        for k in items:
            toc.append(f'      <li><a class="kb" href="#{k["id"]}">{k["q"]}</a></li>')

    sections = []
    for c in chapters:
        sections.append(
            f'  <section class="doc" id="{c["id"]}">\n'
            f'    <h1>{c["title"]}</h1>\n'
            f'    <div class="meta">更新于 {c["updated"]}</div>\n'
            f'    {render_md(c["_body"])}\n'
            f'  </section>'
        )
    for k in kb:
        answer, internal = split_kb_sections(k["_body"])
        sections.append(
            f'  <section class="doc" id="{k["id"]}">\n'
            f'    <h1>Q：{k["q"]}</h1>\n'
            f'    <div class="meta">知识库 {k["id"]} · 更新于 {k["updated"]}</div>\n'
            f'    {render_md(answer)}\n'
            f'    <div class="kb-internal">{render_md(internal)}</div>\n'
            f'  </section>'
        )
    return PAGE.format(
        title="爱小说 · 操作手册",
        toc="\n".join(toc),
        sections=inline_images("\n".join(sections)),
        date=BUILD_DATE,
        email=SUPPORT_EMAIL,
    )


# --------------------------------------------------------------- kb 产物

def build_kb_md(kb: list[dict]) -> str:
    out = [f"# 爱小说 · 客服知识库\n\n> 构建于 {BUILD_DATE}。每条含「答案」（可直接复述给用户）"
           f"与「客服口径」（内部处理指引）。机读版见 kb-export.jsonl。\n"]
    for tag, items in group_kb(kb).items():
        out.append(f"\n## {tag}\n")
        for k in items:
            answer, internal = split_kb_sections(k["_body"])
            rel = f"（关联手册：{'、'.join(k['related'])}）" if k["related"] else ""
            out.append(f"\n### [{k['id']}] {k['q']}\n\n关键词：{'、'.join(k['keywords'])}{rel}\n")
            out.append(f"**答案**\n\n{answer}\n")
            out.append(f"**客服口径（内部）**\n\n{internal}\n")
    return "\n".join(out)


def build_kb_jsonl(kb: list[dict]) -> str:
    lines = []
    for k in kb:
        answer, internal = split_kb_sections(k["_body"])
        lines.append(json.dumps({
            "id": k["id"],
            "question": k["q"],
            "keywords": k["keywords"],
            "tags": [t.strip() for t in k.get("tags", "").split(",") if t.strip()],
            "answer": answer,
            "internal_note": internal,
            "related_manual_chapters": k["related"],
            "capabilities": k["capabilities"],
            "updated": k["updated"],
        }, ensure_ascii=False))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 保鲜门

def check(chapters: list[dict], kb: list[dict]) -> int:
    real = {p.name for p in SPECS.iterdir() if p.is_dir()} if SPECS.is_dir() else set()
    if not real:
        print(f"!! 找不到 openspec/specs（{SPECS}），无法校验", file=sys.stderr)
        return 2
    bad = 0
    for doc in chapters + kb:
        for cap in doc["capabilities"]:
            if cap not in real:
                print(f"✗ {doc['id']}: capability `{cap}` 不在 openspec/specs/ —— spec 已改名/退役，请更新本篇")
                bad += 1
    ids = [d["id"] for d in chapters + kb]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        print(f"✗ 重复 id：{sorted(dup)}")
        bad += len(dup)
    print(f"check：{len(chapters)} 章 + {len(kb)} 条 KB，"
          f"{'全部通过' if not bad else f'{bad} 处失配'}")
    return 1 if bad else 0


def main() -> int:
    if "--check" in sys.argv[1:]:
        return check(load_dir("content"), load_dir("kb"))
    chapters, kb = load_dir("content"), load_dir("kb")
    DIST.mkdir(exist_ok=True)
    (DIST / "manual.html").write_text(build_manual(chapters, kb), encoding="utf-8")
    (DIST / "kb-export.md").write_text(build_kb_md(kb), encoding="utf-8")
    (DIST / "kb-export.jsonl").write_text(build_kb_jsonl(kb), encoding="utf-8")
    print(f"构建完成 → dist/manual.html + dist/kb-export.md + dist/kb-export.jsonl"
          f"（{len(chapters)} 章 + {len(kb)} 条 KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
