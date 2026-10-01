import { test, expect } from '../fixtures'

/**
 * 命名对齐（s-pay-license-naming）：
 * /dashboard/membership 旧链接重定向到 /dashboard/license 真身页。
 * 历史激活码 UI（8.3 拆除的「激活新码」输入框形态）保持移除——s-code-redeem 起
 * 「兑换激活码」为新的官方入口（AppModal 确认制），旧的裸输入直兑形态不复活。
 */
test.describe('membership 旧链接重定向', () => {
  test.beforeEach(async ({ page, mockApi }) => {
    mockApi.registerUser()
    mockApi.setLicense({ tier: 'free', remaining_sec: 0, remaining_desc: '0 天' })
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('token', token), mockApi.token)
  })

  test('/dashboard/membership → /dashboard/license', async ({ page }) => {
    await page.goto('/dashboard/membership')
    await expect(page).toHaveURL(/\/dashboard\/license/, { timeout: 15000 })
    await expect(page.getByRole('heading', { name: '我的套餐' })).toBeVisible({ timeout: 10000 })
  })

  test('历史激活码 UI（裸输入直兑形态）保持移除', async ({ page }) => {
    await page.goto('/dashboard/license')
    // 先等页面渲染完成，防「数到 0 即绿」的空转断言（渲染前 count 恒 0）
    await expect(page.getByRole('heading', { name: '我的套餐' })).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: '激活新码' })).toHaveCount(0)
    // 现行入口=页头「兑换激活码」（确认弹层制，见 license.spec 兑换组）
    await expect(page.getByRole('button', { name: '兑换激活码' })).toBeVisible()
  })
})
