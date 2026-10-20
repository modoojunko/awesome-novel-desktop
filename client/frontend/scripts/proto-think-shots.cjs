/* 思考呈现原型逐态截图＋控制台错误检查（原型是 file:// 自包含，无需栈）。 */
const { chromium } = require("playwright/test");
const OUT = "/Users/modoojunko/Desktop/coding/ai-novel/docs/design-c/drafts/thinkproto-captures";
const FILE = "file:///Users/modoojunko/Desktop/coding/ai-novel/docs/design-c/drafts/ai-novel-c端-思考呈现-原型.html";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const b = await chromium.launch();
  const page = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push("PAGEERROR: " + String(e).slice(0, 200)));
  page.on("console", (m) => { if (m.type() === "error") errors.push("CONSOLE: " + m.text().slice(0, 200)); });

  await page.goto(FILE);
  await sleep(1200);
  const states = ["editing", "thinking", "writing", "done", "timeout", "reading"];
  for (const s of states) {
    await page.click(`[data-state="${s}"]`);
    await sleep(s === "thinking" ? 3200 : 700);  // 思考态让打字机流出一段
    await page.screenshot({ path: `${OUT}/proto-${s}.png` });
    console.log("shot", s);
  }
  // 思考态额外验证：面板存在＋滚动跟随＋gen-line 秒表在走
  await page.click('[data-state="thinking"]');
  await sleep(2500);
  const t1 = await page.textContent(".tk-sec");
  await sleep(2100);
  const t2 = await page.textContent(".tk-sec");
  console.log("ticker:", t1, "->", t2, Number(t2) > Number(t1) ? "OK" : "FAIL");
  const chars = (await page.textContent(".tk-live-body")).length;
  console.log("streamed chars:", chars);
  // 回看抽屉交互
  await page.click('[data-state="done"]');
  await sleep(500);
  await page.click(".tk-bar");
  await sleep(400);
  console.log("drawer collapsed:", await page.isVisible(".tk-drawer") ? "FAIL" : "OK");
  await page.click(".tk-bar");
  await sleep(400);
  console.log("drawer reopened:", await page.isVisible(".tk-drawer") ? "OK" : "FAIL");
  // 超时态展开回看
  await page.click('[data-state="timeout"]');
  await sleep(400);
  await page.click(".tk-see");
  await sleep(400);
  console.log("timeout drawer:", await page.isVisible(".tk-timeout .tk-drawer") ? "OK" : "FAIL");

  console.log(errors.length ? "ERRORS:\n" + errors.join("\n") : "NO CONSOLE ERRORS");
  await b.close();
})();
