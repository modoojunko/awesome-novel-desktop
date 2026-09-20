// 步骤：关闭遗留授权弹窗；添加角色建主角卡；再试从简介立主角
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = { closedPopups: 0 };
  // 关掉遗留授权弹窗（还在轮询生产 check-auth）
  for (const p of ctx.pages()) {
    if (p.url().includes('/auth?')) { await p.close(); out.closedPopups++; }
  }
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(300);

  // 确保在角色页
  if (!(await page.innerText('body')).includes('从简介立主角')) {
    await page.getByText('可后补', { exact: true }).locator('..').getByText('角色', { exact: true }).first().click();
    await page.waitForTimeout(600);
  }
  // 先添加角色
  await page.getByText('添加角色', { exact: true }).first().click();
  await page.waitForTimeout(900);
  out.afterAdd = (await page.innerText('body')).slice(0, 600);
  await page.screenshot({ path: path.join(EV, 't24_after_add_char.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
