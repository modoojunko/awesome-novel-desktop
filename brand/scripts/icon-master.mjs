// brand/scripts/icon-master.mjs
// 把 brand/mark-seal-1024.svg 渲染为 1024 母版 PNG（安装包图标源）。
// 用 S端 的 playwright 依赖；字体走产品同款栈（Noto Serif SC → Songti SC），栅格化后字形固化。
import { chromium } from '../../client/frontend/node_modules/playwright/index.mjs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.resolve(here, '../mark-seal-1024.svg');
const out = process.argv[2] || path.resolve(here, '../icon-master-1024.png');

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1024, height: 1024 }, deviceScaleFactor: 1 });
await page.goto(`file://${src}`);
await page.waitForTimeout(300); // 字体就绪
await page.screenshot({ path: out, clip: { x: 0, y: 0, width: 1024, height: 1024 }, omitBackground: true });
await browser.close();
console.log(`done: ${out}`);
