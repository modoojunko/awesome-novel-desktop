// 自托管 Noto Sans SC / Noto Serif SC（SIL OFL 1.1）——品牌口径：只用免费开源字体。
// 从 Google Fonts css2 API 拉切片 CSS，下载 woff2 到 public/fonts/，
// 生成 src/design/fonts.css（unicode-range 原样保留，浏览器按需取切片）。
// 用法：node scripts/fetch-fonts.mjs（需外网；产物入库，构建不依赖本脚本）
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
const ROOT = path.resolve(import.meta.dirname, '..')
const OUT_DIR = path.join(ROOT, 'public', 'fonts')
const FAMS = [
  { cssUrl: 'https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600&display=swap', name: 'noto-sans-sc' },
  { cssUrl: 'https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@600;700&display=swap', name: 'noto-serif-sc' },
]

await mkdir(OUT_DIR, { recursive: true })
const cssOut = []
let totalBytes = 0, fileCount = 0

for (const fam of FAMS) {
  const css = await (await fetch(fam.cssUrl, { headers: { 'User-Agent': UA } })).text()
  const blocks = [...css.matchAll(/@font-face \{[\s\S]*?\}/g)]
  if (!blocks.length) throw new Error(`no @font-face blocks for ${fam.name}`)
  const rewritten = []
  const seen = new Set()
  let xCount = 0
  for (const [face] of blocks) {
    const weight = /font-weight: (\d+)/.exec(face)[1]
    const url = /src: url\((https:[^)]+)\)/.exec(face)[1]
    // 切片号取 URL 末段 .N.woff2；latin/latin-ext 等非 CJK 子集无切片号，用 x 前缀独立命名防互相覆盖
    const slice = /(\d+)\.woff2$/.exec(url)?.[1] ?? `x${xCount++}`
    seen.add(slice)
    const file = `${fam.name}-${weight}-${slice}.woff2`
    const buf = Buffer.from(await (await fetch(url, { headers: { 'User-Agent': UA } })).arrayBuffer())
    await writeFile(path.join(OUT_DIR, file), buf)
    totalBytes += buf.length; fileCount++
    rewritten.push(face.replace(url, `/fonts/${file}`))
  }
  cssOut.push(`/* ===== ${fam.name}（切片 woff2，按 unicode-range 按需加载）===== */\n${rewritten.join('\n')}`)
  console.log(`${fam.name}: ${seen.size} slices`)
}

const ofl = await (await fetch('https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/OFL.txt')).text()
await writeFile(path.join(OUT_DIR, 'OFL.txt'), ofl)

const header = `/* ================================================================
 * 自托管开源字体（品牌口径：只用免费开源字体）：
 *   Noto Sans SC  400/500/600 —— 正文（--font-body / --font-sans）
 *   Noto Serif SC 600/700     —— 标题展示（--font-display / --font-serif）
 * 授权 SIL Open Font License 1.1（见 public/fonts/OFL.txt），可商用、可随包分发。
 * 切片来自 Google Fonts css2，unicode-range 原样保留——浏览器只下载页面
 * 实际用到的分片，单次访问仅几百 KB；font-display: swap 防白屏。
 * 重生成：node scripts/fetch-fonts.mjs
 * ================================================================ */
`
await writeFile(path.join(ROOT, 'src', 'design', 'fonts.css'), header + cssOut.join('\n') + '\n')
console.log(`done: ${fileCount} files, ${(totalBytes / 1024 / 1024).toFixed(1)} MB`)
