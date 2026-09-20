// 步骤：打开题材目录，导出目录结构（截图+文本）
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(400);
  await page.getByText('选择题材').first().click();
  await page.waitForTimeout(800);
  out.catalogText = (await page.innerText('body')).slice(0, 1500);
  await page.screenshot({ path: path.join(EV, 't13_genre_catalog.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
