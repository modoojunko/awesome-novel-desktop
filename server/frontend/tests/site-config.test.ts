/**
 * site-config sanitize 语义单测（brand-name-single-source）。
 * S端 前端无 vitest 基建，用 Node 24 内置 type-stripping + node:test（零依赖）：
 *   node --test tests/site-config.test.ts
 * 覆盖：白名单五键采纳、未知键丢弃、非字符串丢弃、空串/纯空白=回落（丢弃）。
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { sanitize } from '../src/lib/site-config.ts'

test('五个已知键全部采纳并 trim', () => {
  const out = sanitize({
    apiBase: ' https://example.com/api ',
    beianIcp: '琼ICP备X号',
    beianPolice: '琼公网安备Y号',
    beianPoliceLink: '',
    brandName: '  新品牌  ',
  })
  assert.equal(out.apiBase, 'https://example.com/api')
  assert.equal(out.beianIcp, '琼ICP备X号')
  assert.equal(out.beianPolice, '琼公网安备Y号')
  assert.equal(out.beianPoliceLink, undefined) // 空串=回落构建期值，不采纳
  assert.equal(out.brandName, '新品牌')
})

test('未知键与非字符串一律丢弃', () => {
  const out = sanitize({
    apiBase: 'https://example.com/api',
    evilKey: 'x',
    brandName: 123,
    beianIcp: null,
  })
  assert.deepEqual(out, { apiBase: 'https://example.com/api' })
})

test('非法入参返回空配置（fail-open）', () => {
  assert.deepEqual(sanitize(null), {})
  assert.deepEqual(sanitize('str'), {})
  assert.deepEqual(sanitize([1, 2]), {})
  assert.deepEqual(sanitize(undefined), {})
})

test('brandName 空串/缺省=回落（不出现在结果中）', () => {
  assert.deepEqual(sanitize({ apiBase: '/api', brandName: '' }), { apiBase: '/api' })
  assert.deepEqual(sanitize({ apiBase: '/api' }), { apiBase: '/api' })
})
