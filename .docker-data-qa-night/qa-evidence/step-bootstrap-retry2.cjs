// 步骤：左树进角色页 → 从简介立主角 → 连拍捕捉 toast
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = { shots: [] };
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(400);

  // 左树点击「角色」（精确锚定左树条目，避免命中右栏同名）
  await page.getByText('可后补', { exact: true }).locator('..').getByText('角色', { exact: true }).first().click()
    .catch(async () => { await page.locator('[class*=tree], [class*=side], [class*=list]').getByText('角色', { exact: true }).first().click(); });
  await page.waitForTimeout(800);
  out.onCharPage = (await page.innerText('body')).includes('从简介立主角');

  await page.getByText('从简介立主角').first().click();
  for (const ms of [250, 700, 1500, 2600]) {
    await page.waitForTimeout(ms === 250 ? 250 : ms - { 700: 250, 1500: 700, 2600: 1500 }[ms]);
    const f = path.join(EV, `t23_bootstrap_${ms}.png`);
    await page.screenshot({ path: f });
    out.shots.push(f);
    const toast = await page.evaluate(`(() => {
      const els = [...document.querySelectorAll('[class*=toast], [class*=Toast], [role=alert], [class*=error], [class*=Error]')];
      return els.filter(e => e.offsetParent !== null).map(e => e.textContent.trim().slice(0, 150)).filter(Boolean);
    })()`);
    if (toast && toast.length) out['toastAt' + ms] = toast;
  }
  out.bodyAfter = (await page.innerText('body')).slice(0, 500);
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
