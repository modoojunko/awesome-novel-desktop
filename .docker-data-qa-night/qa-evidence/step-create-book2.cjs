// 步骤：填书名 → 创建 → 走简介/题材后续流程
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;
const BOOK = '星尘旅人';

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.goto('http://localhost:6174/#/novels');
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(600);

  // 若弹窗已开则直接用；否则点开
  const dialogText = await page.innerText('body');
  if (!dialogText.includes('创建，去写简介')) {
    await page.getByText('新建作品', { exact: true }).last().click();
    await page.waitForTimeout(600);
  }
  const nameInput = page.getByRole('textbox').first();
  await nameInput.fill(BOOK);
  await page.screenshot({ path: path.join(EV, 't09_create_filled.png') });
  await page.getByRole('button', { name: '创建，去写简介' }).click();
  await page.waitForTimeout(1200);
  out.urlAfterCreate = page.url();
  out.textAfterCreate = (await page.innerText('body')).slice(0, 700);
  await page.screenshot({ path: path.join(EV, 't10_after_create.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
