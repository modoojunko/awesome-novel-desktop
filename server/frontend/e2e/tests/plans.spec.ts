import { test, expect } from '../fixtures'

test.describe('套餐权益明细页（/plans）', () => {
  test('直达渲染：四档卡＋分组表＋脚注', async ({ page }) => {
    await page.goto('/plans')
    await expect(page.getByRole('heading', { name: '四档套餐，AI 每深一层升一档' })).toBeVisible()
    // 四档卡
    const cards = page.locator('.tier-card h3')
    await expect(cards).toHaveText(['免费', '标准', 'PRO', 'MAX'])
    await expect(page.locator('.tier-card.pro')).toContainText('¥59.9')
    // 分组表：六组都在
    for (const g of ['写作全流程', 'AI 规划', 'AI 执笔与质检', '精修与进阶', '内容与服务', '规格']) {
      await expect(page.locator(`tr.group-row`, { hasText: g })).toBeVisible()
    }
    // 脚注四条（双 Key/试用/即将上线/价格口径）
    await expect(page.locator('.foot-notes')).toContainText('创作模型 Key')
    await expect(page.locator('.foot-notes')).toContainText('7 天 PRO 级试用')
    await expect(page.locator('.foot-notes')).toContainText('无自动续费')
  })

  test('落地页入口可达（评审 P0-2 漏斗断点）', async ({ page }) => {
    await page.goto('/')
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    await page.getByRole('link', { name: /查看完整权益对比/ }).click()
    await expect(page).toHaveURL(/\/plans/)
    await expect(page.getByRole('heading', { name: /四档套餐/ })).toBeVisible()
  })

  test('只看档间差异：四档全同行隐藏、取消恢复', async ({ page }) => {
    await page.goto('/plans')
    await expect(page.locator('tr.group-row')).toHaveCount(6) // 六组齐渲染再计数（懒加载竞态）
    const allRows = () => page.locator('tbody tr:not(.group-row)').count()
    const before = await allRows()
    const toggle = page.locator('.diff-toggle input')
    await toggle.check()
    await page.waitForTimeout(300)
    const after = await allRows()
    expect(after).toBeLessThan(before)
    await toggle.uncheck()
    await page.waitForTimeout(300)
    expect(await allRows()).toBe(before)
  })

  test('收银台入口可达', async ({ page }) => {
    // 收银台需登录态（token 直塞，cashier.spec gotoPay 同款）
    await page.goto('/')
    await page.evaluate(() => localStorage.setItem('token', 'e2e-token'))
    await page.goto('/pay')
    const link = page.getByRole('link', { name: /查看完整权益对比/ })
    await expect(link.first()).toBeVisible({ timeout: 10000 })
    await link.first().click()
    await expect(page).toHaveURL(/\/plans/)
  })
})
