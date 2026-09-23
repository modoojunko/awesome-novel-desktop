import { readFileSync } from 'node:fs'
import path from 'node:path'
import { test, expect } from '@playwright/test'

/**
 * s-contract-live-check —— S web ↔ S 后端 真后端活体冒烟。
 *
 * 与其余 spec 的差别：**直接用 base，绝不挂 ../fixtures 的 auto mock**——
 * 本组存在的意义就是真打后端。vite proxy /api → 127.0.0.1:19000 已是现成路径。
 *
 * S_LIVE_BASE_URL 未设置时整组 skip（照 UP11_DATA_DIR 先例：避免误连共享栈）；
 * nightly 设置该变量指向真后端（如 http://localhost:19000）后真跑。
 */
const LIVE = process.env.S_LIVE_BASE_URL || ''

test.skip(!LIVE, '未设 S_LIVE_BASE_URL——活体冒烟整组跳过（避免误连共享栈）')

const USER = `live-${Date.now().toString(36)}`
const PASS = 'Pass123!'

test('落地页渲染：主文案与双入口在（真后端站点配置）', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('人铸灵魂')).toBeVisible()
  await expect(page.getByText('AI 是笔，你才是作家')).toBeVisible()
  await expect(page.getByRole('button', { name: '免费下载' })).toBeVisible()
})

test('备案信息条挂点在（真站点配置）', async ({ page }) => {
  await page.goto('/')
  const link = page.locator('a[href*="beian"]').first()
  await expect(link).toBeVisible()
})

test('check-auth 契约探针：未授权设备 code=1 且带 msg（fixture 单源）', async ({ request }) => {
  // 读 docs/contracts 单源，锚定 code 闭集与未知设备形态
  // cwd = server/frontend（与 design-parity.spec 的 PROTO_FILE 同款解析）
  const fixture = JSON.parse(
    readFileSync(path.resolve(process.cwd(), '../../docs/contracts/check-auth.example.json'), 'utf-8'),
  )
  const res = await request.get(`${LIVE}/api/check-auth?pc_hash=live-probe-${Date.now()}`)
  expect(res.ok()).toBeTruthy()
  const body = await res.json()
  expect(String(body.code)).toBe('1') // 无 grant 且无 outdated 标记 → 等待授权
  expect(typeof body.msg).toBe('string')
  expect(Object.keys(fixture.codes)).toContain(String(body.code))
})

test('注册→登录→控制台（真认证链路）', async ({ page, request }) => {
  const username = USER
  // API 侧注册（web register 开放注册；随机名避免撞库）
  const reg = await request.post(`${LIVE}/api/web/register`, {
    data: {
      username,
      password: PASS,
      security_question: '.live',
      security_answer: 'live',
    },
  })
  expect([200, 201]).toContain(reg.status())

  // UI 侧登录：表单提交 → 落控制台
  await page.goto('/login')
  await page.getByLabel('用户名').fill(username)
  await page.locator('input[aria-label="密码"]').fill(PASS)
  await page.getByRole('button', { name: /登录/ }).click()
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
})
