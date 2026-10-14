"""图谱渲染（c-deconstruct-book 10.3）——graph/6 → 图谱.html / 图谱.svg（纯函数、确定性）。

- html：加载 assets/graph_viewer.html 生产模板，注入 JSON 岛（`<`→`\\u003c` 防 </script> 逃逸）
  与标题（html.escape）；模板内 JS 对一切模型文本走 esc()——查看器在用户浏览器打开，是注入面。
- svg：关系全网（layout.net）＋地点账（归属缩进名册），文本 xml 转义；同输入同字节（禁 wall-clock）。
- 两渲染器共读 layout 块（坐标单一来源，防同书不同脸）。
"""

from __future__ import annotations

import html
import json
import os

_TEMPLATE = os.path.join(os.path.dirname(__file__), "assets", "graph_viewer.html")

_JSON_TOKEN = "__GRAPH_JSON__"
_TITLE_TOKEN = "__BOOK_TITLE__"

_SVG_W = 960


def render_html(graph: dict) -> str:
    """graph/6 → 自包含查看器 HTML（模板 token 注入；校验 token 在位）。"""
    with open(_TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    for token in (_JSON_TOKEN, _TITLE_TOKEN):
        if tpl.count(token) != 1:
            raise RuntimeError(f"视图模板缺唯一占位符 {token}")
    payload = (
        json.dumps(graph, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    # 顺序纪律（评审 P3）：标题先替——若岛先替，数据内含 __BOOK_TITLE__ 会被二次替换污染
    tpl = tpl.replace(_TITLE_TOKEN, html.escape(str(graph.get("book") or ""), quote=True))
    if tpl.count(_JSON_TOKEN) != 1:
        raise RuntimeError(f"视图模板缺唯一占位符 {_JSON_TOKEN}")
    return tpl.replace(_JSON_TOKEN, payload)


def _esc(s: object) -> str:
    return html.escape(str(s or ""), quote=True)


def _place_order(places: list[dict]) -> list[tuple[dict, int]]:
    """地点账顺序：按 parent 链 DFS（根先、子随父），缩进＝深度；孤儿单独列尾。"""
    by_id = {p["id"]: p for p in places}
    kids: dict[str | None, list[dict]] = {}
    for p in places:
        parent = p.get("parent") or None
        if parent not in by_id:
            parent = None
        kids.setdefault(parent, []).append(p)
    out: list[tuple[dict, int]] = []

    def walk(parent: str | None, depth: int) -> None:
        for p in sorted(kids.get(parent, []), key=lambda x: str(x.get("label") or "")):
            out.append((p, depth))
            walk(p["id"], depth + 1)

    walk(None, 0)
    seen = {p["id"] for p, _ in out}
    for p in places:  # 防御：异常 parent 环导致的漏网
        if p["id"] not in seen:
            out.append((p, 0))
    return out


def render_svg(graph: dict) -> str:
    """graph/6 → 静态 SVG（关系全网＋地点账）；确定性纯函数。"""
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    places = list(graph.get("places") or [])
    net = (graph.get("layout") or {}).get("net") or {}

    ledger = _place_order(places)
    net_h = 470
    ledger_h = 34 + len(ledger) * 22 + 10
    warn_list = (graph.get("meta") or {}).get("warnings") or []
    comp = (graph.get("meta") or {}).get("completion") or {}
    n_warn_total = sum(int(w.get("count") or 1) for w in warn_list)
    foot_h = 34
    height = net_h + ledger_h + foot_h

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_SVG_W}" height="{height}" '
        f'viewBox="0 0 {_SVG_W} {height}" font-family="PingFang SC, Hiragino Sans GB, Microsoft YaHei, Noto Sans CJK SC, sans-serif">'
    )
    out.append(f'<rect x="0" y="0" width="{_SVG_W}" height="{height}" fill="#fdfdfd"/>')
    out.append(f'<text x="20" y="30" font-size="19" font-weight="600">《{_esc(graph.get("book"))}》拆书知识图谱</text>')
    st = graph.get("stats") or {}
    out.append(
        f'<text x="20" y="52" font-size="12" fill="#666">共 {_esc(st.get("chapters"))} 章 · '
        f'{_esc(st.get("words"))} 字 · 人 {sum(1 for n in nodes if n.get("type") == "person")} · '
        f'势力 {sum(1 for n in nodes if n.get("type") == "faction")} · 物 {sum(1 for n in nodes if n.get("type") == "item")} · '
        f'关系 {len(edges)} 条 · 地点 {len(places)} 处</text>'
    )
    # 完成度恒显（评审 P2-3：非空警告才显示会把零警告书也藏起来）
    warn_color = "#a76b00" if n_warn_total else "#8a929b"
    warn_txt = f"警告 {n_warn_total} 处" if n_warn_total else "无警告"
    out.append(
        f'<text x="{_SVG_W - 20}" y="30" font-size="12" fill="{warn_color}" text-anchor="end">'
        f'完成度 {_esc(comp.get("presence_placed"))}/{_esc(comp.get("presence_total"))} · {warn_txt}（详见 图谱.html）</text>'
    )
    # 图例
    out.append('<text x="20" y="80" font-size="11.5" fill="#666">实心圆＝主角 · 空心圆＝配角 · 红＝反派 · 方＝势力 · 菱＝物品 · 线粗＝戏份 · 红＝敌对 · 黄＝从属</text>')

    def pos(nid: str) -> tuple[float, float] | None:
        p = net.get(nid)
        return (float(p[0]), float(p[1])) if isinstance(p, (list, tuple)) and len(p) >= 2 else None

    label_by_id = {str(n.get("id")): str(n.get("label") or "") for n in nodes}

    def label_of(nid: object) -> str:
        return label_by_id.get(str(nid), str(nid))

    # 边
    for e in edges:
        a, b = pos(e.get("from")), pos(e.get("to"))
        if not a or not b:
            continue
        kind = str(e.get("kind") or "")
        if kind == "敌对":
            stroke = "#c25555"
        elif kind in ("师徒", "主从", "同门", "同僚"):
            stroke = "#c99b3f"
        else:
            stroke = "#9aa4ae"
        w = 1.2 + float(e.get("w") or 1) * 1.3
        title = f"{label_of(e.get('from'))} —{kind}→ {label_of(e.get('to'))} · 第{e.get('ch')}章"
        out.append(
            f'<line x1="{a[0]:.0f}" y1="{a[1]:.0f}" x2="{b[0]:.0f}" y2="{b[1]:.0f}" '
            f'stroke="{stroke}" stroke-width="{w:.1f}" stroke-linecap="round">'
            f"<title>{_esc(title)}</title></line>"
        )
    # 节点
    for n in nodes:
        a = pos(n.get("id"))
        if not a:
            continue
        x, y = a
        t = n.get("type")
        if t == "faction":
            out.append(f'<rect x="{x - 30:.0f}" y="{y - 13:.0f}" width="60" height="26" rx="8" fill="#fdf3dd" stroke="#c99b3f" stroke-width="1.6"/>')
            ly = y + 30
        elif t == "item":
            out.append(
                f'<path d="M {x:.0f} {y - 14:.0f} L {x + 14:.0f} {y:.0f} L {x:.0f} {y + 14:.0f} L {x - 14:.0f} {y:.0f} Z" '
                f'fill="#e6f6ee" stroke="#3f9f76" stroke-width="1.6"/>'
            )
            ly = y + 30
        else:
            role = n.get("role") or ""
            if role == "主角":
                fill, stroke, r = "#3f9f8b", "#2f7d6d", 19
            elif role == "反派":
                fill, stroke, r = "#c25555", "#a33f3f", 14
            else:
                fill, stroke, r = "#ffffff", "#3f9f8b", 14
            out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
            ly = y + r + 15
        out.append(f'<text x="{x:.0f}" y="{ly:.0f}" font-size="12" text-anchor="middle">{_esc(n.get("label"))}</text>')

    # 地点账
    base = net_h
    out.append(f'<line x1="20" y1="{base - 8}" x2="{_SVG_W - 20}" y2="{base - 8}" stroke="#e5e7ea"/>')
    out.append(f'<text x="20" y="{base + 16}" font-size="13" font-weight="600">地点账（归属缩进 · 首现章）</text>')
    for i, (p, depth) in enumerate(ledger):
        y = base + 38 + i * 22
        note = str(p.get("note") or "")
        line = f"{p.get('label')}（第{p.get('ch')}章）" + (f" · {note}" if note else "")
        out.append(f'<text x="{28 + depth * 18}" y="{y}" font-size="12">{_esc(line)}</text>')

    # 页脚
    out.append(
        f'<text x="20" y="{height - 12}" font-size="11" fill="#8a929b">'
        f'由 AwesomeNovel 拆书导出（契约 deconstruct-graph/6）· 图谱.json 为唯一机器正身，本图与 图谱.html 同源'
        f'</text>'
    )
    out.append("</svg>")
    return "\n".join(out)
