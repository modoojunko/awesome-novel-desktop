// 步骤：模型配置页 → 添加假 Key（指向本地死端口，测试 AI 失败路径）
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

  await page.getByText('添加 API Key', { exact: false }).first().click();
  await page.waitForTimeout(800);
  out.formText = (await page.innerText('body')).slice(0, 1200);
  out.fields = await page.evaluate(`(() => {
    const els = [...document.querySelectorAll('input, textarea, select')];
    return els.map((el, i) => ({ i, tag: el.tagName, type: el.type || '', ph: el.placeholder || '', label: (el.closest('label')?.textContent || el.closest('div')?.textContent || '').trim().slice(0, 50), visible: el.offsetParent !== null })).filter(f => f.visible);
  })()`);
  await page.screenshot({ path: path.join(EV, 't27_addkey_form.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
