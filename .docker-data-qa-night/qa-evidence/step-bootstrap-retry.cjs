// 步骤：重试「从简介立主角」并连拍捕捉瞬时 toast
const path = require('path');
const { chromium } = require('playwright');
const EV = __dirname;

(async () => {
  const browser = await chromium.connectOverCDP('http://localhost:9333');
  const ctx = browser.contexts()[0];
  const out = { shots: [] };
  let page = ctx.pages().find((p) => p.url().startsWith('http://localhost:6174'));
  await page.waitForLoadState('domcontentloaded');
  await page.reload();
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(600);
  await page.getByText('从简介立主角').first().click();
  for (const ms of [250, 700, 1400, 2500]) {
    await page.waitForTimeout(ms === 250 ? 250 : ms - (ms === 700 ? 250 : ms === 1400 ? 700 : 1400));
    const f = path.join(EV, `t21_bootstrap_${ms}.png`);
    await page.screenshot({ path: f });
    out.shots.push(f);
    // 抓 toast 类浮层文本
    const toast = await page.evaluate(`(() => {
      const els = [...document.querySelectorAll('[class*=toast], [class*=Toast], [class*=message], [class*=notice], [role=alert], [class*=popover], [class*= Pop], [class*=pop]')];
      return els.filter(e => e.offsetParent !== null).map(e => e.textContent.trim().slice(0, 120)).filter(Boolean);
    })()`);
    if (toast && toast.length) out['toastAt' + ms] = toast;
  }
  out.bodyTail = (await page.innerText('body')).slice(-300);
  console.log(JSON.stringify(out, null, 2));
  await browser.close();
})().catch((e) => { console.error('STEP FAILED:', e.message); process.exit(1); });
