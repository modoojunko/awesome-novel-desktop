// brand/scripts/favicon-gen.mjs
// mark-seal.svg（96 viewBox 满幅构图）渲染 256px PNG → server/frontend/public/favicon.png
// 再由 python+Pillow 合成多尺寸 favicon.ico（见同目录说明/调用处）。
import { chromium } from '../../client/frontend/node_modules/playwright/index.mjs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const here = path.dirname(fileURLToPath(import.meta.url))
const src = path.resolve(here, '../mark-seal.svg')
const out = process.argv[2] || path.resolve(here, '../favicon-256.png')

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 256, height: 256 }, deviceScaleFactor: 1 })
await page.goto(`file://${src}`)
await page.waitForTimeout(300)
await page.screenshot({ path: out, clip: { x: 0, y: 0, width: 256, height: 256 }, omitBackground: true })
await browser.close()
console.log(`done: ${out}`)
