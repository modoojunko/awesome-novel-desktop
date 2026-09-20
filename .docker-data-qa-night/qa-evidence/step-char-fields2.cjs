// 步骤：回角色页，导出主角卡可填字段
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.goto('http://localhost:6174/#/novel/68740d38-2ef2-48ba-bdf2-6a53181d353a');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(800);
  // 左树进角色
  await page.getByText('可后补', { exact: true }).locator('..').getByText('角色', { exact: true }).first().click();
  await page.waitForTimeout(800);
  out.fields = await page.evaluate(`(() => {
    const els = [...document.querySelectorAll('input, textarea')];
    return els.map((el, i) => ({ i, tag: el.tagName, type: el.type || '', ph: (el.placeholder || '').slice(0, 40), val: (el.value || '').slice(0, 20), visible: el.offsetParent !== null })).filter(f => f.visible);
  })()`);
  await page.screenshot({ path: path.join(EV, 't31_char_card.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
