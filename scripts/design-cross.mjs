#!/usr/bin/env node
// design:cross —— 两端 base.css 共享段逐字校验（M1 机制，裁决见 docs/ux/cross-end.html §六）
// 共享段 = 两端 src/design/base.css 中 @cross-begin/@cross-end 标记之间的文本；
// 规范化空白后必须 strict 相等，单端私改即退出码 1 并指认首处分歧行。
// 两端 package.json 的 "design:cross" 均指到本脚本；落位变更须同步 openspec/config.yaml 引用。
// TODO(M2): 图标注册表公共键 path 断言（client icons.tsx × server icons.ts）并入本脚本。
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const root = path.join(path.dirname(fileURLToPath(import.meta.url)), '..')
// 拆仓（s-server-repo-split）：S端 前端在 sibling 私有仓 awesome-novel-server——
// S_SERVER_DIR 环境变量可覆盖（默认指向同级检出的 server/ 子目录，与 compose 同约定）。
const serverRoot = process.env.S_SERVER_DIR || path.join(root, '../awesome-novel-server/server')
const FILES = {
  client: path.join(root, 'client/frontend/src/design/base.css'),
  server: path.join(serverRoot, 'frontend/src/design/base.css'),
}
const BEGIN = '/* @cross-begin'
const END = '/* @cross-end */'

function crossSegment(css) {
  const begin = css.indexOf(BEGIN)
  const end = css.indexOf(END)
  if (begin === -1 || end === -1 || end < begin) {
    throw new Error('共享段标记缺失或次序错误（应有 @cross-begin … @cross-end）')
  }
  return css.slice(begin, end + END.length)
}

const norm = (s) => s.replace(/\s+/g, ' ').trim()

let clientSeg, serverSeg
try {
  clientSeg = crossSegment(readFileSync(FILES.client, 'utf8'))
  serverSeg = crossSegment(readFileSync(FILES.server, 'utf8'))
} catch (err) {
  console.error(`✗ design:cross ${err.message}`)
  process.exit(1)
}

if (norm(clientSeg) === norm(serverSeg)) {
  console.log('✓ design:cross 共享段零差异')
  process.exit(0)
}

const a = clientSeg.split('\n')
const b = serverSeg.split('\n')
for (let i = 0; i < Math.max(a.length, b.length); i++) {
  if (norm(a[i] ?? '') !== norm(b[i] ?? '')) {
    console.error('✗ design:cross 共享段分歧（首处）：')
    console.error(`  段内第 ${i + 1} 行`)
    console.error(`  client: ${(a[i] ?? '(缺行)').trim() || '(空行)'}`)
    console.error(`  server: ${(b[i] ?? '(缺行)').trim() || '(空行)'}`)
    console.error('  修复：把改动同步到另一端 base.css 的共享段，两端同提。')
    process.exit(1)
  }
}
