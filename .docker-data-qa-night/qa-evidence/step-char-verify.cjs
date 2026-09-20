// 步骤：重载后检查主角卡持久化状态
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.goto('http://localhost:6174/#/novel/68740d38-2ef2-48ba-bdf2-6a53181d353a');
  await page.waitForLoadState('domcontentloaded');
  await page.reload();
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(900);
  await page.getByText('可后补', { exact: true }).locator('..').getByText('角色', { exact: true }).first().click();
  await page.waitForTimeout(900);
  out.bodyHead = (await page.innerText('body')).slice(400, 1100);
  out.railStatus = (await page.innerText('body')).match(/当前角色[^\n]*/)?.[0] ?? 'n/a';
  await page.screenshot({ path: path.join(EV, 't34_char_after_reload.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
