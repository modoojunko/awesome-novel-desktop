// qa-night 测试桥：常驻 Chromium（独立 profile，与用户浏览器隔离），暴露 CDP 9333
// 步进脚本通过 connectOverCDP 接管操作；本进程负责保持浏览器存活并采集控制台错误。
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

const EV = __dirname;
const LOG = path.join(EV, 'console-log.txt');

(async () => {
  const ctx = await chromium.launchPersistentContext(path.join(EV, 'chrome-profile'), {
    headless: true,
    viewport: { width: 1440, height: 900 },
    args: ['--remote-debugging-port=9333'],
  });
  const hook = (page) => {
    const line = (t) => fs.appendFileSync(LOG, `${new Date().toISOString()} ${page.url().slice(0, 80)} ${t}\n`);
    page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') line(`[${m.type()}] ${m.text().slice(0, 300)}`); });
    page.on('pageerror', (e) => line(`[pageerror] ${String(e).slice(0, 400)}`));
    page.on('requestfailed', (r) => line(`[requestfailed] ${r.method()} ${r.url().slice(0, 120)} ${r.failure() && r.failure().errorText}`));
  };
  ctx.pages().forEach(hook);
  ctx.on('page', (p) => { hook(p); fs.appendFileSync(LOG, `${new Date().toISOString()} PAGE-OPEN ${p.url().slice(0, 80)}\n`); });
  fs.writeFileSync(path.join(EV, 'cdp-endpoint.txt'), 'http://localhost:9333');
  console.log('qa-night chromium ready at CDP 9333');
  setInterval(() => {}, 1 << 30);
})().catch((e) => { console.error('bridge failed:', e); process.exit(1); });
