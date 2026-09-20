// 步骤：选玄幻大类→小类→口味/禁雷/吃苦/斗什么→确认完成
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

  await page.getByText('玄幻', { exact: true }).first().click();
  await page.waitForTimeout(600);
  out.afterCategory = (await page.innerText('body')).slice(0, 900);
  await page.screenshot({ path: path.join(EV, 't14_xuanhuan_subs.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
