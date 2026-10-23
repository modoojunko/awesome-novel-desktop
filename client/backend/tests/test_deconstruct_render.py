"""图谱渲染单元（deconstruct/render.py）——注入安全与确定性。

判例：查看器在用户浏览器打开＝注入面——JSON 岛内 `<` 必须 \u003c 转义；模板文本一律 esc()；
对抗夹具（</script>、<img onerror>、U+2028）进图后不得以可执行形态出现在产物里。
"""

from __future__ import annotations

import json
import re

from deconstruct.graph import assemble
from deconstruct.render import render_html, render_svg

_EVIL = "</script><img src=x onerror=alert(1)>"


def _graph():
    cards = {
        "1": {
            "summary": "开场",
            "characters": [{"name": _EVIL, "role": "主角", "traits": "", "alias": ""}],
            "places": [{"name": "竹湾渡口", "parent": "", "note": ""}],
            "presence": [{"who": _EVIL, "where": "竹湾渡口"}],
            "intro": [],
            "genre": [],
            "world": [],
            "relations": [],
            "mainplot": [],
            "structure": [],
            "style": [],
            "techniques": [],
            "foreshadow": [],
        },
    }
    products = {
        "characters": {
            "data": {
                "characters": [
                    {
                        "name": _EVIL,
                        "role": "主角",
                        "plot": "p" + _EVIL,
                        "evidence_ch": "第1章",
                    }
                ]
            }
        },
        "intro": {"data": {"intro": "恶人开场\u2028第二行"}},
    }
    return assemble(
        book_name="《恶书》" + _EVIL,
        chapter_count=1,
        words=10,
        cards=cards,
        products=products,
        place_merge=None,
        source_text="第1章 开场\n" + _EVIL + "出现。",
    )


def test_render_html_island_roundtrip_and_escape():
    g = _graph()
    html = render_html(g)
    start = html.index('<script id="graphdata" type="application/json">') + len(
        '<script id="graphdata" type="application/json">'
    )
    end = html.index("</script>", start)
    island = html[start:end]
    assert "<" not in island, "JSON 岛内不得残留裸 <（</script> 逃逸面）"
    assert "\\u003c" in island
    assert json.loads(island) == g
    assert "<img" not in html  # 对抗串不得以标签形态出现
    assert "\u2028" not in island  # U+2028 行分隔符已转义
    assert "\\u2028" in island


def test_render_html_title_escaped():
    g = _graph()
    html = render_html(g)
    assert html.count("<title>") == 1
    m = re.search(r"<title>(.*?)</title>", html)
    assert "<" not in m.group(1) and "&lt;" in m.group(1)


def test_template_has_no_prototype_chrome():

    from deconstruct.render import _TEMPLATE

    with open(_TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    for bad in ("原型", "v7", "v6", "尚未产出", "TODO"):
        assert bad not in tpl, f"生产模板残留原型文案：{bad}"


def test_render_svg_deterministic_and_escaped():
    g = _graph()
    a, b = render_svg(g), render_svg(g)
    assert a == b, "同输入必须同字节（禁 wall-clock）"
    assert a.startswith("<svg") and a.rstrip().endswith("</svg>")
    assert "<img" not in a
    assert "&lt;/script&gt;" in a  # 节点名以转义形态呈现
    assert "地点账" in a and "竹湾渡口" in a
    assert "deconstruct-graph/6" in a


def test_template_inline_js_syntax():
    """模板内联 JS 语法检查（环境无 node 时跳过——前端 CI 另有把关）。"""
    import os as _os
    import shutil
    import subprocess
    import tempfile

    if not shutil.which("node"):
        return

    from deconstruct.render import _TEMPLATE

    with open(_TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()
    js = re.findall(r"<script>(.*?)</script>", tpl, re.DOTALL)[-1]
    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", delete=False, encoding="utf-8"
    ) as f:
        f.write(js)
        path = f.name
    try:
        r = subprocess.run(
            ["node", "--check", path], capture_output=True, text=True, check=False
        )
        assert r.returncode == 0, r.stderr[:500]
    finally:
        _os.unlink(path)


# ── c-graph-net-cytoscape：vendor 内联／无外链／hash 与声明同源 ──────────────

_REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]
_VENDOR_DIR = (
    __import__("pathlib")
    .Path(__import__("deconstruct.render", fromlist=["render"]).__file__)
    .resolve()
    .parent
    / "assets"
    / "vendor"
)


def test_render_html_inlines_vendor_and_licenses():
    """四个渲染库与许可岛必须内联进单文件，且模板 token 无残留。"""
    html = render_html(_graph())
    for sig in ("Cytoscape Consortium", "cytoscapeFcose", "layoutBase", "coseBase"):
        assert sig in html, f"vendor 特征串缺失：{sig}"
    for token in ("__GRAPH_JSON__", "__BOOK_TITLE__", "__VENDOR_"):
        assert token not in html, f"token 未替换干净：{token}"
    # 许可岛：四库版权＋MIT 全文随单文件（与 THIRD-PARTY-NOTICES 第五节同源）
    assert html.count("Permission is hereby granted, free of charge") >= 4
    for lic in (
        "LICENSE-cytoscape",
        "LICENSE-layout-base",
        "LICENSE-cose-base",
        "LICENSE-cytoscape-fcose",
    ):
        assert lic in html


def test_render_html_no_external_resource_refs():
    """无外链只约束资源引用属性（script/link/img src、@import、url()）——
    书内 quote/note 出现 http(s) 文本是合法数据，不得误判。"""
    g = _graph()
    url = "https://example.com/evil?a=1"
    g["logline"] = "证据见 " + url + " 一段"
    html = render_html(g)
    assert url in html  # 数据文本原样保留（JSON 岛内）
    for pat in (
        r"<script[^>]+src\s*=",
        r"<link[^>]+href\s*=",
        r"<img[^>]+src\s*=",
        r"@import\s+",
        r"url\(\s*['\"]?https?:",
    ):
        assert not re.search(pat, html, re.IGNORECASE), f"外链资源引用：{pat}"


def test_vendor_files_match_readme_hashes():
    """供应链牙齿：vendor 文件 sha256 与 vendor/README.md 表一致（升级漏改即红）。"""
    import hashlib

    readme = (_VENDOR_DIR / "README.md").read_text(encoding="utf-8")
    rows = re.findall(
        r"\|\s*`([\w.-]+\.js)`\s*\|[^|]+\|[^|]+\|\s*`([0-9a-f]{64})`\s*\|", readme
    )
    assert len(rows) == 4, f"README 应登记四个 js，实际 {len(rows)}"
    for name, digest in rows:
        data = (_VENDOR_DIR / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, f"{name} hash 与 README 不符"
    for lic in (
        "LICENSE-cytoscape",
        "LICENSE-layout-base",
        "LICENSE-cose-base",
        "LICENSE-cytoscape-fcose",
    ):
        assert (_VENDOR_DIR / lic).exists(), f"缺许可文件 {lic}"


def test_notices_and_datas_cover_viewer_assets():
    """合规与打包：NOTICES 第五节四段声明在位；bundle_manifest.DATAS 收录 deconstruct/assets
    （v0.38 安装包缺该条目导致带图谱导出 400——本条目是回归钉）。"""
    notices = (_REPO_ROOT / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    assert "五、图谱查看器内联渲染库" in notices
    for name in ("cytoscape", "layout-base", "cose-base", "cytoscape-fcose"):
        assert f"LICENSE-{name}" in notices
    manifest = (_REPO_ROOT / "client/packaging/build/bundle_manifest.py").read_text(
        encoding="utf-8"
    )
    assert '("client/backend/deconstruct/assets", "deconstruct/assets")' in manifest, (
        "DATAS 缺 deconstruct/assets——安装包将没有查看器模板与 vendor"
    )
    assert (_REPO_ROOT / "client/backend/deconstruct/assets/graph_viewer.html").exists()


def _viewer_fixture_graph() -> dict:
    """冒烟夹具：30 个有关系节点（>20 → 默认只标 12 个枢纽）＋10 个孤立实体；40 条边。"""
    nodes, edges = [], []
    for i in range(30):
        nodes.append(
            {
                "id": f"n{i + 1:02d}",
                "type": "person",
                "label": "主角甲" if i == 0 else f"人物{i + 1:02d}",
                "role": "主角" if i == 0 else ("反派" if i % 11 == 0 else "配角"),
            }
        )
    for i in range(10):
        nodes.append(
            {"id": f"x{i + 1:02d}", "type": "item", "label": f"孤立物{i}", "role": ""}
        )
    kinds = ["恩义", "敌对", "主从", "挚友", "爱慕"]
    for i in range(40):
        a, b = i % 30, (i * 7 + 3) % 30
        if a == b:
            b = (b + 1) % 30
        edges.append(
            {
                "from": f"n{a + 1:02d}",
                "to": f"n{b + 1:02d}",
                "kind": kinds[i % 5],
                "ch": 1 + (i % 3),
                "w": 1 + i % 5,
                "raw": "",
                "quote": "",
            }
        )
    chapters = []
    for no in range(1, 4):
        chapters.append(
            {
                "no": no,
                "beat": f"第{no}章剧情",
                "at": ["p01"],
                "who": ["n01", "n02"],
                "ev": None,
                "presence": [
                    {"who": "n01", "where": "p01"},
                    {"who": "n02", "where": None},
                ],
            }
        )
    return {
        "contract": "deconstruct-graph/6",
        "book": "冒烟书",
        "stats": {"chapters": 3, "words": 999},
        "logline": "夹具书眼",
        "relTypes": {},
        "nodes": nodes,
        "edges": edges,
        "places": [
            {"id": "p01", "label": "夹具地", "parent": None, "ch": 1, "note": ""}
        ],
        "links": [],
        "events": [
            {
                "id": "e1",
                "title": "事件",
                "ch": [1, 3],
                "at": "p01",
                "members": ["n01"],
                "note": "",
            }
        ],
        "hooks": [{"desc": "伏笔", "plant": 1, "payoff": None, "status": "未收"}],
        "chapters": chapters,
        "layout": {
            "net": {},
            "scene": {"p01": [20, 20, 240, 200]},
            "scene_canvas": [860, 470],
        },
        "meta": {
            "completion": {"chapters": 3, "presence_total": 6, "presence_placed": 4},
            "warnings": [],
        },
    }


_DRIVER_JS = r"""
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright');
const [normal, broken] = process.argv.slice(2);
(async () => {
  const browser = await chromium.launch();
  const out = {};
  const errors = [];
  async function open(path) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
    page.on('pageerror', e => errors.push('pageerror: ' + String(e)));
    page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
    await page.goto('file://' + path);
    await page.waitForTimeout(600);
    return page;
  }
  // ── 正常件 ──
  let page = await open(normal);
  await page.click('#tabNet');
  await page.waitForTimeout(1800);
  const attr = (k) => page.evaluate((key) => document.getElementById('netwrap').getAttribute(key), k);
  out.default = {
    visN: await attr('data-vis-nodes'), visE: await attr('data-vis-edges'),
    labeled: await attr('data-labeled'), connected: await attr('data-connected'),
    fallback: await attr('data-fallback'),
  };
  const topId = await page.evaluate(() =>
    window.__net.cy.nodes().toArray().sort((a, b) => b.data('rel') - a.data('rel'))[0].id());
  await page.evaluate((id) => window.__net.focus(id), topId);
  await page.waitForTimeout(500);
  out.focus = await attr('data-focus');
  out.sideHasName = await page.evaluate((id) =>
    document.getElementById('side').textContent.indexOf(
      window.__net.cy.getElementById(id).data('label')) >= 0, topId);
  await page.evaluate(() => window.__net.clear());
  out.focusCleared = (await attr('data-focus')) === '';
  await page.click('#labelsAll');
  await page.waitForTimeout(700);
  out.labeledAll = await attr('data-labeled');
  await page.click('#labelsAll');
  await page.selectOption('#topn', '20');
  await page.waitForTimeout(700);
  out.topN20 = { visN: await attr('data-vis-nodes'), labeled: await attr('data-labeled') };
  await page.selectOption('#topn', '0');
  await page.click('#tabScene');
  await page.waitForTimeout(400);
  out.sceneChildren = await page.evaluate(() => document.getElementById('scene').childNodes.length > 0);
  out.hubOrderRun1 = await page.evaluate(() => {
    const cy = window.__net.cy;
    const ns = cy.nodes().not('.hidden');
    const bb = ns.boundingBox();
    const cx = (bb.x1 + bb.x2) / 2, cy0 = (bb.y1 + bb.y2) / 2;
    const arr = ns.toArray().map(n => ({ rel: n.data('rel'),
      d: Math.hypot(n.position().x - cx, n.position().y - cy0) }));
    arr.sort((a, b) => b.rel - a.rel);
    const avg = (xs) => xs.reduce((sm, x) => sm + x.d, 0) / xs.length;
    return { top5: avg(arr.slice(0, 5)), bottom5: avg(arr.slice(-5)) };
  });
  await page.close();
  // 同一文件重开：层次关系稳定（枢纽中心距 < 低关系；两次都成立，坐标不要求一致）
  page = await open(normal);
  await page.click('#tabNet');
  await page.waitForTimeout(1800);
  out.hubOrderRun2 = await page.evaluate(() => {
    const cy = window.__net.cy;
    const ns = cy.nodes().not('.hidden');
    const bb = ns.boundingBox();
    const cx = (bb.x1 + bb.x2) / 2, cy0 = (bb.y1 + bb.y2) / 2;
    const arr = ns.toArray().map(n => ({ rel: n.data('rel'),
      d: Math.hypot(n.position().x - cx, n.position().y - cy0) }));
    arr.sort((a, b) => b.rel - a.rel);
    const avg = (xs) => xs.reduce((sm, x) => sm + x.d, 0) / xs.length;
    return { top5: avg(arr.slice(0, 5)), bottom5: avg(arr.slice(-5)) };
  });
  await page.close();
  // ── 破坏件：vendor 脚本置空 → 文本清单兜底 ──
  page = await open(broken);
  await page.click('#tabNet');
  await page.waitForTimeout(800);
  out.broken = {
    fallback: await page.evaluate(() => document.getElementById('netwrap').getAttribute('data-fallback')),
    rows: await page.evaluate(() => document.querySelectorAll('#netfallback .erow').length),
    sceneChildren: (await page.click('#tabScene'), await page.waitForTimeout(400),
      await page.evaluate(() => document.getElementById('scene').childNodes.length > 0)),
  };
  await page.close();
  await browser.close();
  out.errors = errors;
  const hubCloser = (o) => o && o.top5 < o.bottom5;
  const ok = hubCloser(out.hubOrderRun1) && hubCloser(out.hubOrderRun2)
    && out.default.visN === '30' && out.default.visE === '40' && out.default.labeled === '12'
    && out.default.connected === '30' && !out.default.fallback
    && out.focus && out.focusCleared && out.sideHasName
    && out.labeledAll === '30' && out.topN20.visN === '20' && out.topN20.labeled === '20'
    && out.sceneChildren
    && out.broken.fallback === '1' && out.broken.rows === 40 && out.broken.sceneChildren
    && errors.length === 0;
  console.log(JSON.stringify(out));
  process.exit(ok ? 0 : 1);
})().catch(e => { console.error(String(e)); process.exit(2); });
"""


def test_graph_viewer_playwright_smoke():
    """查看器交互冒烟（Playwright/Chromium）：默认口径 30/40/12、聚焦、全显、TopN、
    vendor 破坏后文本清单兜底；无 node/playwright 环境跳过（前端 CI 另有把关）。"""
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    playwright_pkg = _REPO_ROOT / "client/frontend/node_modules/playwright/package.json"
    if not node or not playwright_pkg.exists():
        import pytest

        pytest.skip("本机无 node/playwright，查看器冒烟由前端环境执行")

    g = _viewer_fixture_graph()
    html = render_html(g)
    blocks = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    assert len(blocks) == 5, f"应有 4 vendor＋1 应用脚本，实际 {len(blocks)}"
    broken = html
    for i, body in enumerate(blocks[:4]):  # 置空四个 vendor 脚本体 → cytoscape 未加载
        broken = broken.replace(body, "", 1)

    with tempfile.TemporaryDirectory() as td:
        import pathlib

        d = pathlib.Path(td)
        p_normal = d / "normal.html"
        p_broken = d / "broken.html"
        p_normal.write_text(html, encoding="utf-8")
        p_broken.write_text(broken, encoding="utf-8")
        driver = d / "driver.cjs"
        driver.write_text(_DRIVER_JS, encoding="utf-8")
        import os as _os

        env = dict(_os.environ, PLAYWRIGHT_PATH=str(playwright_pkg.parent))
        r = subprocess.run(
            ["node", str(driver), str(p_normal), str(p_broken)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if r.returncode != 0 and "Executable doesn't exist" in (r.stdout + r.stderr):
            import pytest

            pytest.skip("playwright 浏览器未安装（npx playwright install）")
        assert r.returncode == 0, f"冒烟失败：{r.stderr[:600]}\n{r.stdout[:1200]}"
