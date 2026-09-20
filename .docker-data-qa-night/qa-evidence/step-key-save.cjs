// 步骤：填假 Key 并保存测试连接，观察失败报错
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

  await page.getByPlaceholder('例如：主线 · OpenAI').fill('本地假模型（QA测试用）');
  await page.getByPlaceholder('https://api.openai.com').fill('http://127.0.0.1:9999/v1');
  await page.getByPlaceholder('sk-...').fill('sk-test-local-fake-000');
  await page.screenshot({ path: path.join(EV, 't28_key_filled.png') });
  await page.getByRole('button', { name: '保存并测试连接' }).click();
  // 连接测试会打到死端口，等失败反馈
  await page.waitForTimeout(6000);
  out.afterSave = (await page.innerText('body')).slice(0, 900);
  await page.screenshot({ path: path.join(EV, 't29_key_test_result.png') });
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
