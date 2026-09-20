// 步骤：填简介 → 确认完成 → 观察题材页
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;
const SYNOPSIS = '守灯人陈晏在祖母去世当晚发现，老宅地下埋着一扇用星尘封存的门，门后是早已坠落的故乡星域。为找回祖母留在星海中的残影，他踏上以记忆为燃料的旅途——每点亮一颗星，就要遗忘一段往事。灯火渐深，往事成空，当旅程走到终点，他将拿什么想起自己为何出发？而他点亮的光，又会在人间留下怎样的影子？';

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(500);

  const ta = page.locator('textarea').first();
  await ta.fill(SYNOPSIS);
  out.counter = await page.locator('text=/\\/500/').first().innerText().catch(() => 'n/a');
  await page.screenshot({ path: path.join(EV, 't11_synopsis_filled.png') });
  await page.getByRole('button', { name: '确认完成' }).click();
  await page.waitForTimeout(1200);
  out.afterConfirm = (await page.innerText('body')).slice(0, 500);
  out.url = page.url();
  await page.screenshot({ path: path.join(EV, 't12_after_synopsis.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
