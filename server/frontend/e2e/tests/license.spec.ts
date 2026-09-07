import type { Page } from '@playwright/test'
import { test, expect } from '../fixtures'
import type { MockApi, TestLicenseCode } from '../mocks/api-handlers'

function order(overrides: Partial<Parameters<MockApi['setOrders']>[0][number]> = {}): Parameters<MockApi['setOrders']>[0][number] {
  return {
    order_no: 'S20260902TEST0001',
    status: 'fulfilled',
    amount_fen: 3000,
    snapshot: { tier_display: 'PRO', tier_key: 'pro', period: 'monthly', period_days: 30 },
    created_at: '2026-09-02T08:52:00Z',
    paid_at: '2026-09-02T08:53:00Z',
    refunded_at: '',
    refund_amount_fen: null,
    ...overrides,
  }
}

function code(overrides: Partial<TestLicenseCode> = {}): TestLicenseCode {
  return {
    code_id: 'O-S20260902TEST0001',
    order_no: 'S20260902TEST0001',
    tier: 'pro',
    duration_days: 30,
    status: 'active',
    activated_at: '2026-09-02 17:00',
    expires_at: '2026-10-02 17:00',
    grant_start: '2026-09-02 17:00',
    ...overrides,
  }
}

async function gotoLicense(page: Page, query = ''): Promise<void> {
  await page.goto('/')
  await page.evaluate(() => localStorage.setItem('token', 'e2e-token'))
  await page.goto(`/dashboard/license${query}`)
}

async function expectTabOn(page: Page, label: string): Promise<void> {
  await expect(page.getByRole('tab', { name: label })).toHaveAttribute('aria-selected', 'true')
}

test.describe('我的套餐明细 tab 分版与激活（license-grants-pagination）', () => {
  test.beforeEach(async ({ mockApi }) => {
    mockApi.registerUser()
  })

  test('整页空态：无套餐行且无权益 → 引导购买，tab 条不渲染', async ({ page }) => {
    await gotoLicense(page)
    await expect(page.getByText('还没有生效中的套餐')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('tablist')).toHaveCount(0)
  })

  test('手工码态：有剩余权益无套餐行 → 仅档位头', async ({ page, mockApi }) => {
    mockApi.setLicense({ tier: 'pro', remaining_sec: 86400, remaining_desc: '1 天', pending_count: 0, code_count: 0 })
    await gotoLicense(page)
    await expect(page.getByText('剩余')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('tablist')).toHaveCount(0)
    await expect(page.getByText('还没有生效中的套餐')).toHaveCount(0)
  })

  test('默认版=生效中且 URL 省参；某类空态给切回全部出口', async ({ page, mockApi }) => {
    mockApi.setOrders([order()]) // 唯一行=待激活
    await gotoLicense(page)
    // 默认版生效中：URL 无 tab 参数，某类空态 + 切回全部出口
    await expect(page.getByText('没有生效中的套餐')).toBeVisible({ timeout: 10000 })
    expect(new URL(page.url()).searchParams.get('tab')).toBeNull()
    await expectTabOn(page, '生效中')
    await page.getByRole('button', { name: '切回全部查看' }).click()
    await expect(page.getByText('PRO · 30 天')).toBeVisible()
    await expect(page.url()).toContain('tab=all')
  })

  test('非法 tab 回落默认版；切 tab URL 同步', async ({ page, mockApi }) => {
    mockApi.setOrders([order()])
    await gotoLicense(page, '?tab=bogus')
    await expectTabOn(page, '生效中')
    await page.getByRole('tab', { name: '待激活' }).click()
    await expect(page.url()).toContain('tab=pending')
    await expect(page.locator('.code-row .pill-warn')).toBeVisible()
  })

  test('待激活行可见 → 确认激活 → 自动切「全部」展示生效中', async ({ page, mockApi }) => {
    mockApi.setOrders([order()])
    await gotoLicense(page)
    // 页头待激活计数与行一致
    await expect(page.locator('.sum')).toContainText('1 个', { timeout: 10000 })
    await page.getByRole('tab', { name: '待激活' }).click()
    await expect(page.getByText('PRO · 30 天')).toBeVisible()
    await expect(page.getByText(/不计时、不占额度/)).toBeVisible()
    // 确认弹层讲清两条后果
    await page.getByRole('button', { name: '激活', exact: true }).click()
    await expect(page.getByText('确认激活套餐')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(/立即开始计时/)).toBeVisible()
    await expect(page.getByText(/按已使用时长折算/)).toBeVisible()
    await page.getByRole('button', { name: '确认激活' }).click()
    // 成功后自动切「全部」：刚激活的行可见、待激活入口消失
    await expect(page.getByText('激活成功，套餐已开始计时')).toBeVisible({ timeout: 10000 })
    await expectTabOn(page, '全部')
    await expect(page.getByText('PRO · 30 天')).toBeVisible()
    await expect(page.getByText('生效中').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '激活', exact: true })).toHaveCount(0)
  })

  test('不可激活给出原因与联系客服出口', async ({ page, mockApi }) => {
    mockApi.setOrders([order()])
    mockApi.failActivate('not_activatable')
    await gotoLicense(page)
    await page.getByRole('tab', { name: '待激活' }).click({ timeout: 10000 })
    await page.getByRole('button', { name: '激活', exact: true }).click()
    await page.getByRole('button', { name: '确认激活' }).click()
    await expect(page.getByText(/该套餐当前不能激活/)).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('联系客服')).toBeVisible()
  })

  test('退款冻结行：留在生效中版带「退款处理中」标识，无激活按钮（s-pay-refund-freeze）', async ({ page, mockApi }) => {
    mockApi.setLicenseCodes([code({
      code_id: 'O-S20260905FROZEN01',
      order_no: 'S20260905FROZEN01',
      status: 'frozen',
    })])
    await gotoLicense(page)
    // 默认版=生效中：冻结行留在本版可见（不凭空消失），带退款处理中标识
    await expect(page.getByText('退款处理中', { exact: true })).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('退款处理中·已暂停使用；取消退款自动恢复')).toBeVisible()
    // 冻结行不提供激活入口；「全部」版同样可见
    await expect(page.getByRole('button', { name: '激活' })).toHaveCount(0)
    await page.getByRole('tab', { name: '全部' }).click()
    await expect(page.getByText('退款处理中', { exact: true })).toBeVisible()
  })

  test('未知状态行：按原文渲染防御性回退，不误标生效或冻结', async ({ page, mockApi }) => {
    mockApi.setLicenseCodes([code({
      code_id: 'O-S20260905FUTURE01',
      order_no: 'S20260905FUTURE01',
      status: 'some_new_status',
    })])
    await gotoLicense(page, '?tab=all')
    // 状态分版筛选会把未知状态滤掉，未知行只在「全部」出现；文案按原文渲染
    await expect(page.getByText('状态：some_new_status')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('some_new_status').first()).toBeVisible()
  })

  test('已收回行：专属版不置灰可见，「全部」内置灰，无操作按钮', async ({ page, mockApi }) => {
    mockApi.setLicenseCodes([code({
      code_id: 'O-S20260902REFUND01',
      order_no: 'S20260902REFUND01',
      status: 'revoked',
      activated_at: '',
      expires_at: '',
      grant_start: '',
    })])
    await gotoLicense(page)
    // 默认版生效中 → 某类空
    await expect(page.getByText('没有生效中的套餐')).toBeVisible({ timeout: 10000 })
    await page.getByRole('tab', { name: '已收回' }).click()
    await expect(page.getByText('已随退款收回')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: '激活' })).toHaveCount(0)
    // 专属版内不置灰（无 revoked 置灰类）
    await expect(page.locator('.code-row.revoked')).toHaveCount(0)
    // 切回「全部」→ 置灰
    await page.getByRole('tab', { name: '全部' }).click()
    await expect(page.locator('.code-row.revoked')).toHaveCount(1)
  })

  test('加载更多：跨页追加不重复，取完按钮消失', async ({ page, mockApi }) => {
    mockApi.setLicenseCodes(
      Array.from({ length: 25 }, (_, i) => code({
        code_id: `O-S20260902BULK${String(i).padStart(2, '0')}`,
        order_no: `S20260902BULK${String(i).padStart(2, '0')}`,
      })),
    )
    await gotoLicense(page)
    await page.getByRole('tab', { name: '全部' }).click()
    await expect(page.locator('.code-row')).toHaveCount(20, { timeout: 10000 })
    await expect(page.getByText('已显示 20 个 · 共 25 个')).toBeVisible()
    await page.getByRole('button', { name: '加载更多' }).click()
    await expect(page.locator('.code-row')).toHaveCount(25)
    await expect(page.getByText('已显示 25 个 · 共 25 个')).toBeVisible()
    await expect(page.getByRole('button', { name: '加载更多' })).toHaveCount(0)
  })

  test('从某类空 tab 切出不整页闪（档位头保持、无整页加载态）', async ({ page, mockApi }) => {
    mockApi.setOrders([order()]) // 唯一行=待激活：默认版生效中=某类空
    await gotoLicense(page)
    await expect(page.getByText('没有生效中的套餐')).toBeVisible({ timeout: 10000 })
    mockApi.setGrantsGate({ delayMs: 600 })
    await page.getByRole('tab', { name: '待激活' }).click()
    // 等待期内档位头与 tab 条保持原位，整页 MUST NOT 被「加载中…」替换
    await expect(page.locator('.panel.hero')).toBeVisible({ timeout: 2000 })
    await expect(page.getByText('加载中…')).toHaveCount(0)
    await expect(page.getByText('没有待激活的套餐')).toBeVisible() // 旧空态面板保留到数据到达（文案随新 tab 名）
    await expect(page.getByText('PRO · 30 天')).toBeVisible({ timeout: 5000 })
  })

  test('切版失败保留旧列表、不误报空态', async ({ page, mockApi }) => {
    mockApi.setOrders([order()]) // 待激活行
    await gotoLicense(page)
    await page.getByRole('tab', { name: '待激活' }).click()
    await expect(page.getByText('PRO · 30 天')).toBeVisible({ timeout: 10000 })
    // 切回「全部」时断网：旧列表原样保留
    mockApi.setGrantsGate({ fail: true })
    await page.getByRole('tab', { name: '全部' }).click()
    await page.waitForTimeout(800)
    await expect(page.getByText('PRO · 30 天')).toBeVisible()
    await expect(page.getByText(/没有.*的套餐/)).toHaveCount(0)
  })
})
