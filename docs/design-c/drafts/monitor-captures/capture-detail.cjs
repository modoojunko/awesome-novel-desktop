/* 拆书监控原型抓取：真渲染 → real.css（逐路由累积去重）＋.app-shell＋整页截图。
 *
 * 前置（独立栈，见同目录 seed.py 头注释）：uvicorn:8101（私有 DATA_ROOT＋
 * DECONSTRUCT_DISPATCHER_OFF=1）先 boot 再 seed，vite:5291 VITE_API_PROXY→8101；
 * config.json 与本文件 auth token/username 同值（免 OAuth）。
 * 等待锚＝面板 od-id（mon-sum/mon-recent），不硬编码种子数字——批次/在途数随种子变。
 * 运行：node capture-detail.cjs（playwright 取自 client/frontend/node_modules，
 * 用仓库相对路径解析，worktree 换目录无需改）。
 */
const path = require("path");
const fs = require("fs");

const FRONTEND_NM = path.join(__dirname, "..", "..", "..", "..", "client", "frontend", "node_modules");
const { chromium } = require(path.join(FRONTEND_NM, "@playwright", "test"));

const BASE = "http://localhost:5291";
const TID = "dec-mon-proto-1"; // 须与 seed.py 的 TID 一致
const OUT = __dirname;
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 960 } });
  await ctx.addInitScript(() => {
    localStorage.setItem("auth_token", "proto-token-decmon-20261019");
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

  // 路由 1：任务清单（累积基础 chunk）→ 路由 2：监控详情
  await page.goto(BASE + "/#/tools", { waitUntil: "networkidle" });
  await page.waitForTimeout(800);
  await harvest();
  await page.goto(BASE + "/#/tools/deconstruct/" + TID, { waitUntil: "networkidle" });
  await page.waitForSelector('[data-od-id="mon-sum"]', { timeout: 20000 });
  await page.waitForSelector('[data-od-id="mon-recent"]', { timeout: 10000 });
  await page.waitForTimeout(1200); // 入场动画/延迟 chunk
  await harvest();

  const shell = await page.$eval(".app-shell", (el) => el.outerHTML);
  fs.writeFileSync(OUT + "/real.css", cssChunks.join("\n"));
  fs.writeFileSync(OUT + "/dom-detail.html", shell);
  await page.screenshot({ path: OUT + "/shot-detail.png", fullPage: true });
  console.log("css chunks:", cssChunks.length, "bytes:", cssChunks.join("\n").length);
  console.log("shell bytes:", shell.length);
  console.log("console errors:", errors.length, errors.slice(0, 3));
  await browser.close();
  if (errors.length) process.exitCode = 2;
})();
