// 步骤：选供应商→保存测试
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

  // 弹窗内选择供应商 OpenAI（在弹窗容器内找）
  await page.getByText('OpenAI', { exact: true }).first().click();
  await page.waitForTimeout(300);
  await page.getByRole('button', { name: '保存并测试连接' }).click();
  await page.waitForTimeout(8000);
  out.afterSave = (await page.innerText('body')).slice(0, 1000);
  await page.screenshot({ path: path.join(EV, 't30_key_saved.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
