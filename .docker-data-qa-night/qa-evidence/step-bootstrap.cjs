// 步骤：尝试「从简介立主角」AI 引导，记录无 Key 时的表现
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
  await page.getByText('从简介立主角').first().click();
  await page.waitForTimeout(3000);
  out.afterClick = (await page.innerText('body')).slice(0, 700);
  await page.screenshot({ path: path.join(EV, 't21_bootstrap_attempt.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
