/* 正文纸张原型抓取：真渲染 → real.css（逐路由累积去重）＋阅读态/编辑态 .app-shell＋截图。
 *
 * 前置（独立栈，端口全冷门私有）：
 *   uvicorn:8103  DATA_ROOT=/tmp/prose-paper-data（私有库，不动主检出/demo 栈）
 *                 PROMPT_PACK_DEV_DIR→sibling 提示词仓
 *   vite:5293     VITE_API_PROXY→8103
 *   config.json token/username 与本文件 localStorage 同值（免 OAuth）
 * 运行：node capture.cjs  （playwright 取自 client/frontend/node_modules）
 */
const path = require("path");
const fs = require("fs");

const FRONTEND_NM = path.join(__dirname, "..", "..", "..", "..", "client", "frontend", "node_modules");
const { chromium } = require(path.join(FRONTEND_NM, "@playwright", "test"));

const BASE = "http://127.0.0.1:5293";
const TOKEN = "prose-paper-proto-token-20261022";
const IDS = JSON.parse(fs.readFileSync("/tmp/prose-paper-data/seed-ids.json", "utf8"));
const OUT = __dirname;

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  await ctx.addInitScript(() => {
    localStorage.setItem("auth_token", "prose-paper-proto-token-20261022");
    localStorage.setItem("auth_username", "proto");
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  const seen = new Set();
  const cssChunks = [];
  async function harvest() {
    for (const s of await page.$$eval("style", (els) => els.map((e) => e.textContent))) {
      if (s && !seen.has(s)) { seen.add(s); cssChunks.push(s); }
    }
  }

  // 路由 1：书架（基础 chunk）→ 路由 2：书工作台（workbench/editor 分片）
  await page.goto(BASE + "/#/novels", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await harvest();

  await page.goto(BASE + "/#/novel/" + IDS.project, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);
  await harvest();

  // 选章 → 正文页签（阅读态）
  const chRow = page.locator(".col-tree .ch").first();
  await chRow.waitFor({ timeout: 20000 });
  await chRow.click();
  await page.waitForTimeout(1200);
  await page.getByRole("tab", { name: /^正文/ }).click();
  await page.waitForTimeout(1200);
  await harvest();

  await page.locator(".editor").waitFor({ timeout: 15000 });
  const readShell = await page.$eval(".app-shell", (el) => el.outerHTML);
  fs.writeFileSync(OUT + "/dom-read.html", readShell);
  await page.screenshot({ path: OUT + "/shot-read.png" });
  const readMetrics = await page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const rect = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; };
    const cs = (el, p) => el ? getComputedStyle(el)[p] : null;
    const wrap = q(".editor-wrap"), ed = q(".editor"), col = q(".col-editor");
    return {
      colEditor: rect(col), editorWrap: rect(wrap), editor: rect(ed),
      wrapBg: cs(wrap, "backgroundColor"), wrapPadding: wrap && cs(wrap, "padding"),
      wrapOverflow: cs(wrap, "overflowY"),
      colBg: cs(col, "backgroundColor"),
      editorMaxW: cs(ed, "maxWidth"), editorFont: cs(ed, "fontFamily"), editorSize: cs(ed, "fontSize"),
      editorLH: cs(ed, "lineHeight"), editorColor: cs(ed, "color"),
      bodyBg: getComputedStyle(document.body).backgroundColor,
      scrollH: wrap && wrap.scrollHeight, clientH: wrap && wrap.clientHeight,
      viewport: { w: innerWidth, h: innerHeight },
    };
  });

  // 编辑态
  await page.getByTestId("prose-edit").click();
  await page.waitForTimeout(1500);
  await harvest();
  await page.getByTestId("prose-done").waitFor({ timeout: 10000 });
  const editShell = await page.$eval(".app-shell", (el) => el.outerHTML);
  fs.writeFileSync(OUT + "/dom-edit.html", editShell);
  await page.screenshot({ path: OUT + "/shot-edit.png" });
  const editMetrics = await page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const rect = (el) => { if (!el) return null; const r = el.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; };
    const cs = (el, p) => el ? getComputedStyle(el)[p] : null;
    const wrap = q(".editor-wrap"), ed = q(".editor"), bar = q(".ol-top.edit-bar"), body = q(".prose-body");
    return {
      proseBody: rect(body), editBar: rect(bar), editorWrap: rect(wrap), editor: rect(ed),
      wrapBg: cs(wrap, "backgroundColor"), wrapBorder: cs(wrap, "border"),
      wrapRadius: cs(wrap, "borderBottomLeftRadius"),
      barBg: cs(bar, "backgroundColor"), barBorder: cs(bar, "borderTop"),
      wrapPadding: wrap && cs(wrap, "padding"),
      scrollH: wrap && wrap.scrollHeight, clientH: wrap && wrap.clientHeight,
      editorScrollH: ed && ed.scrollHeight,
    };
  });

  fs.writeFileSync(OUT + "/real.css", cssChunks.join("\n"));
  fs.writeFileSync(OUT + "/metrics.json", JSON.stringify({ read: readMetrics, edit: editMetrics }, null, 2));
  console.log("css chunks:", cssChunks.length, "bytes:", cssChunks.join("\n").length);
  console.log("read shell:", readShell.length, "edit shell:", editShell.length);
  console.log("errors:", errors.length, errors.slice(0, 3));
  await browser.close();
  if (errors.length) process.exitCode = 2;
})();
