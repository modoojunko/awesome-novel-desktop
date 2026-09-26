#!/usr/bin/env node
/**
 * 构建期生成 /legal/eula.html：由仓库根 LICENSE（EULA v2026.09 单一事实源）原样复制。
 * relicense-proprietary：改 LICENSE 后重新构建即同步——严禁手工编辑 public/legal/eula.html
 * （防双源漂移；文件内含版本号 v2026.09 可探测漂移）。
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(here, '..', '..', '..')
let src;
try {
  src = readFileSync(join(repoRoot, 'LICENSE'), 'utf-8').replace(/^\uFEFF/, '');
} catch (e) {
  console.error(`copy-eula: LICENSE 不存在（repoRoot=${repoRoot}）——` +
    `compose 须注入 repo=. 命名上下文并 COPY --from=repo LICENSE /LICENSE`);
  process.exit(1);
}

const esc = (t) =>
  t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>软件许可协议（EULA v2026.09）— 爱小说</title>
<style>
  body { margin: 0 auto; max-width: 760px; padding: 32px 20px 64px; font: 15px/1.8 -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; color: #1f2328; }
  h1 { font-size: 22px; }
  p { white-space: pre-wrap; }
</style>
</head>
<body>
<h1>《爱小说》桌面软件最终用户许可协议</h1>
<p>${esc(src)}</p>
</body>
</html>
`

writeFileSync(join(here, '..', 'public', 'legal', 'eula.html'), html)
console.log('public/legal/eula.html generated from root LICENSE')
