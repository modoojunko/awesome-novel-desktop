// 步骤：新建作品（书名 + 题材），观察创建流程落点
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  if (!page) { page = await ctx.newPage(); await page.setViewportSize({ width: 1440, height: 900 }); }
  await page.goto('http://localhost:6174/#/novels');
  await page.waitForLoadState('domcontentloaded');
  await page.reload();
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(800);

  const newBtn = page.getByText('新建作品', { exact: true }).last();
  const cnt = await page.getByText('新建作品', { exact: true }).count();
  out.newBtnCount = cnt;
  await newBtn.click();
  await page.waitForTimeout(800);
  out.afterClickText = (await page.innerText('body')).slice(0, 600);
  await page.screenshot({ path: path.join(EV, 't08_create_dialog.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
