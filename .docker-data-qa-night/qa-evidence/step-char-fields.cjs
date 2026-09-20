// 步骤：导出角色卡全部可编辑字段（placeholder/label）
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
  out.fields = await page.evaluate(`(() => {
    const els = [...document.querySelectorAll('input[type=text], textarea, input:not([type])')];
    return els.map((el, i) => ({
      i,
      tag: el.tagName,
      ph: el.placeholder || '',
      val: (el.value || '').slice(0, 30),
      label: (el.closest('label')?.textContent || '').trim().slice(0, 40),
      aria: el.getAttribute('aria-label') || '',
      visible: el.offsetParent !== null,
    })).filter(f => f.visible);
  })()`);
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
