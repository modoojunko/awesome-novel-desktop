// 步骤：C端 登录页 → 打开浏览器登录 → 授权页填表 → 授权登录 → 观察配对结果
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = {};

  // 复用已有 C端 标签页或新开
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  if (!page) {
    page = await ctx.newPage();
    await page.setViewportSize({ width: 1440, height: 900 });
  }
  await page.goto('http://localhost:6174/#/login');
  await page.waitForLoadState('domcontentloaded');
  await page.reload();
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(800);
  out.loginPageText = (await page.innerText('body')).slice(0, 200);
  await page.screenshot({ path: path.join(EV, 't03_login_bridge.png') });

  // 点击「打开浏览器登录」
  const btn = page.getByRole('button', { name: '打开浏览器登录' });
  if ((await btn.count()) !== 1) throw new Error('login button not unique: ' + (await btn.count()));
  // 清理历史遗留授权弹窗，避免误取旧挑战
  for (const p of ctx.pages()) if (p !== page && p.url().includes('/auth?')) await p.close();
  await btn.click();
  // 等弹窗
  let popup = null;
  for (let i = 0; i < 20 && !popup; i++) {
    await page.waitForTimeout(500);
    popup = ctx.pages().find((p) => p !== page && p.url().includes('/auth?'));
  }
  if (!popup) throw new Error('auth popup did not open');
  out.popupUrl = popup.url().slice(0, 100);
  await popup.waitForLoadState('domcontentloaded');
  await popup.waitForTimeout(500);
  await popup.screenshot({ path: path.join(EV, 't04_auth_popup.png') });

  // 填用户名/密码并提交
  await popup.getByRole('textbox', { name: '用户名' }).fill('qa_novelist_2026');
  await popup.getByRole('textbox', { name: '密码' }).fill('QaNovel#2026');
  await popup.screenshot({ path: path.join(EV, 't05_auth_filled.png') });
  const authBtn = popup.getByRole('button', { name: '授权登录' });
  out.authBtnEnabled = await authBtn.isEnabled();
  await authBtn.click();
  await popup.waitForTimeout(1500);
  out.afterAuthText = (await popup.innerText('body')).slice(0, 400);
  await popup.screenshot({ path: path.join(EV, 't06_auth_result.png') });

  // 回到 C端 页观察登录态
  await page.waitForTimeout(2500);
  out.clientAfterAuth = (await page.innerText('body')).slice(0, 400);
  out.clientUrl = page.url();
  await page.screenshot({ path: path.join(EV, 't07_client_after_auth.png') });

  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
