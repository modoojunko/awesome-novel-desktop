// 步骤：完成题材页全部五段并确认
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

  await page.getByText('东方史诗玄幻', { exact: true }).first().click();
  await page.waitForTimeout(400);

  // 02 主要看什么：自定义填写
  const watchInput = page.locator('textarea, input[type=text]').filter({ hasNot: page.locator('[readonly]') }).last();
  await watchInput.fill('以记忆换力量的代价感，与跨越星域的归乡执念');
  // 03 禁雷勾选
  for (const ban of ['禁天降外援', '禁白捡神器', '禁预知破局']) {
    await page.getByText(ban, { exact: true }).first().click();
  }
  // 04 吃苦指数滑杆
  const slider = page.locator('input[type=range]').first();
  out.sliderCount = await slider.count();
  if (out.sliderCount > 0) await slider.fill('7');
  // 05 斗什么
  await page.getByText('查真相', { exact: true }).first().click();
  await page.getByText('抗外敌', { exact: true }).first().click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(EV, 't15_genre_filled.png') });
  await page.getByRole('button', { name: '确认完成' }).click();
  await page.waitForTimeout(1200);
  out.afterConfirm = (await page.innerText('body')).slice(0, 400);
  await page.screenshot({ path: path.join(EV, 't16_after_genre.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
