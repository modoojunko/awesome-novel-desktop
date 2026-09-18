import { test, expect } from '../fixtures'

// 备案信息条（SiteBeianBar）：五个挂点全覆盖 + 同屏唯一性。
// 测试号由 playwright.config.ts webServer 注入，本机 .env 状态不影响断言。
const ICP_URL = 'https://beian.miit.gov.cn/'
const TEST_NO = '粤ICP备TEST0000001号'
const POLICE_NO = '粤公网安备TEST4401000200号'
// policeQueryUrl 抽编号数字拼官方查询页；TEST 号数字段即 4401000200
const POLICE_URL = 'https://beian.mps.gov.cn/#/query/webSearch?code=4401000200'

async function expectBeianVisible(page: import('@playwright/test').Page) {
  const link = page.locator(`a[href="${ICP_URL}"]`)
  await expect(link).toBeVisible()
  await expect(link).toHaveText(TEST_NO)
}

test.describe('备案信息条', () => {
  test('首页：版权行下方唯一一条', async ({ page }) => {
    await page.goto('/')
    const footer = page.locator('.mkt-foot')
    await footer.scrollIntoViewIfNeeded()
    // 同屏唯一性：FooterSection 内嵌 + PublicLayout 对 landing 跳过 = 全页恰好 1 条
    await expect(page.locator(`a[href="${ICP_URL}"]`)).toHaveCount(1)
    await expectBeianVisible(page)
  })

  test('公安备案：警徽图标+编号，链接拼官方查询页', async ({ page }) => {
    await page.goto('/')
    const footer = page.locator('.mkt-foot')
    await footer.scrollIntoViewIfNeeded()
    const link = page.locator(`a[href="${POLICE_URL}"]`)
    await expect(link).toBeVisible()
    await expect(link).toContainText(POLICE_NO)
    // 公安备案规范：编号前挂警徽图标（装饰性 alt 置空），图标+文字同链跳查询页
    const icon = link.locator('img[src="/beian-police.png"]')
    await expect(icon).toBeVisible()
    await expect(icon).toHaveAttribute('alt', '')
  })

  test('登录页：main 之后渲染', async ({ page }) => {
    await page.goto('/login')
    await expectBeianVisible(page)
  })

  test('注册页：main 之后渲染', async ({ page }) => {
    await page.goto('/register')
    await expectBeianVisible(page)
  })

  test('激活过渡页 /auth：吸底', async ({ page }) => {
    await page.goto('/auth?pc_hash=test_hash_123&challenge=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
    await expectBeianVisible(page)
  })

  test('404 页：吸底', async ({ page }) => {
    await page.goto('/no-such-page')
    await expectBeianVisible(page)
  })

  test('dashboard：登录后内容流尾部可见', async ({ page, mockApi }) => {
    mockApi.registerUser()
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('token', token), mockApi.token)
    await page.goto('/dashboard')
    await expectBeianVisible(page)
  })
})
