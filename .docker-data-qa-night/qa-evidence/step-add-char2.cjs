// 步骤：添加角色建卡 → 再试从简介立主角（第3次） → 连拍
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(300);

  await page.getByText('添加角色', { exact: false }).first().click();
  await page.waitForTimeout(1000);
  out.afterAdd = (await page.innerText('body')).slice(400, 1100);
  await page.screenshot({ path: path.join(EV, 't24_after_add_char.png') });

  // 第3次尝试：从简介立主角
  if (out.afterAdd.includes('从简介立主角') || (await page.innerText('body')).includes('从简介立主角')) {
    await page.getByText('从简介立主角', { exact: false }).first().click();
    await page.waitForTimeout(4000);
    out.afterBootstrap = (await page.innerText('body')).slice(300, 1100);
    await page.screenshot({ path: path.join(EV, 't25_bootstrap_try3.png') });
  }
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
