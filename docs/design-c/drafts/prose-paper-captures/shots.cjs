/* 正文纸张原型 · 逐变体截图（评审参照，不参与构建）
 *
 * 前置：python3 docs/design-c/drafts/build-prose-paper-proto.py 先生成产物。
 * 运行：node docs/design-c/drafts/prose-paper-captures/shots.cjs
 * 产物：prose-paper-captures/proto-shots/*.png（1440×900 @2x）
 */
const path = require("path");
const fs = require("fs");
const FRONTEND_NM = path.join(__dirname, "..", "..", "..", "..", "client", "frontend", "node_modules");
const { chromium } = require(path.join(FRONTEND_NM, "@playwright", "test"));

const DRAFTS = path.join(__dirname, "..");
const FILE = "file://" + encodeURI(path.join(DRAFTS, "ai-novel-c端-正文纸张-原型.html"));
const OUT = path.join(__dirname, "proto-shots");

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  await page.goto(FILE, { waitUntil: "load" });
  await page.waitForTimeout(400);

  async function shot(name) {
    await page.waitForTimeout(320);
    await page.screenshot({ path: path.join(OUT, name + ".png") });
  }

  // 单形态：A 连续纸 + 白纸（2026-10-22 拍板），只切阅读/编辑
  await shot("read");
  await page.click('#ppMode button[data-mode="edit"]');
  await shot("edit");

  // 专注（宽桌面——最接近 Word 的一屏）
  await page.click('#ppView button[data-focus="1"]');
  await shot("edit-focus");
  await page.click('#ppView button[data-focus="0"]');

  // 长章滚到中部（连续纸的纸边跟着走）
  await page.click('#ppMode button[data-mode="read"]');
  await page.evaluate(() => { document.querySelector(".pp-stage .editor-wrap").scrollTop = 1200; });
  await shot("read-scrolled");

  // 编辑态滚到中部：看写字范围框随纸走
  await page.click('#ppMode button[data-mode="edit"]');
  await page.evaluate(() => { document.querySelector(".pp-stage .editor-wrap").scrollTop = 1200; });
  await shot("edit-scrolled");

  // 几何快照（与 metrics.json 的抓取值对拍用）
  const geo = await page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const cs = (el, p) => getComputedStyle(el)[p];
    const w = q(".pp-stage .editor-wrap"), p = q(".pp-paper"), e = q(".pp-stage .editor");
    return {
      editorWidth: cs(e, "width"),
      paperWidth: cs(p, "width"),
      paperPadding: cs(p, "padding"),
      deskBg: cs(w, "backgroundColor"),
      paperBg: cs(p, "backgroundColor"),
      hScrollOverflow: w.scrollWidth - w.clientWidth,
    };
  });
  fs.writeFileSync(path.join(OUT, "geometry.json"), JSON.stringify(geo, null, 2));
  console.log(JSON.stringify(geo));
  console.log("errors:", errs.length, errs.slice(0, 3));
  await browser.close();
  if (errs.length) process.exitCode = 2;
})();
