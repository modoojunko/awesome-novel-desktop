// 步骤：诊断角色页按钮文案
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  out.url = page.url();
  out.hasBootstrapText = (await page.innerText('body')).includes('从简介立主角');
  out.bodyMid = (await page.innerText('body')).slice(300, 800);
  // 列出所有含「添加」的元素文案
  out.addTexts = await page.evaluate(`(() => [...document.querySelectorAll('button, a, [role=button]')].map(b => b.textContent.trim()).filter(t => t.includes('添加')).slice(0, 10))()`);
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
