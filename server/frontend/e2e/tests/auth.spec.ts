import { test, expect } from '../fixtures'

test.describe('认证流程', () => {
  test.describe('注册', () => {
    test('页面标题和试用徽章', async ({ page }) => {
      await page.goto('/register')
      await expect(page.getByRole('heading', { name: '注册' })).toBeVisible()
      await expect(page.getByText('注册另送 7 天 PRO 级试用')).toBeVisible()
    })

    test('成功注册', async ({ page, mockApi }) => {
      mockApi.registerUser()
      await page.goto('/register')
      await page.getByLabel('用户名').fill('newuser')
      await page.locator('input[aria-label="密码"]').fill('Pass123!')
      await page.getByLabel('确认密码').fill('Pass123!')
      await page.locator('select').first().selectOption('你的宠物名字是？')
      await page.getByLabel('密保答案').fill('Fluffy')
      // 法律文件双勾选（legal-four-docs）为提交前置，不勾按钮保持 disabled
      await page.locator('label.agr-chk', { hasText: '《用户服务协议》' }).locator('input').check()
      await page.locator('label.agr-chk', { hasText: '《隐私政策》' }).locator('input').check()
      await page.locator('button:has-text("注册")').click()
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
    })

    test('密码校验', async ({ page }) => {
      await page.goto('/register')
      await page.locator('input[aria-label="密码"]').fill('123')
      await expect(page.getByText('密码至少 6 位')).toBeVisible()
    })

    test('确认密码校验', async ({ page }) => {
      await page.goto('/register')
      await page.locator('input[aria-label="密码"]').fill('Pass123!')
      await page.getByLabel('确认密码').fill('Diff!')
      await expect(page.getByText('两次密码不一致').first()).toBeVisible()
    })

    test('按钮初始禁用', async ({ page }) => {
      await page.goto('/register')
      await expect(page.locator('button:has-text("注册")')).toBeDisabled()
    })

    test('跳转登录', async ({ page }) => {
      await page.goto('/register')
      await page.locator('a[href="/login"]').first().click()
      await expect(page).toHaveURL(/\/login/)
    })
  })

  test.describe('登录', () => {
    test('页面渲染', async ({ page }) => {
      await page.goto('/login')
      await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()
    })

    test('成功登录', async ({ page, mockApi }) => {
      const user = mockApi.registerUser()
      await page.goto('/login')
      await page.getByLabel('用户名').fill(user.username)
      await page.locator('input[aria-label="密码"]').fill(user.password)
      await page.locator('button:has-text("登录")').click()
      await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
    })

    test('登录失败', async ({ page, mockApi }) => {
      mockApi.registerUser()
      await page.goto('/login')
      await page.getByLabel('用户名').fill('wrong_user')
      await page.locator('input[aria-label="密码"]').fill('wrong_pass')
      await page.locator('button:has-text("登录")').click()
      // 给 API 调用留出时间
      await page.waitForTimeout(2000)
      // 检查页面是否显示错误信息或仍在登录页
      const currentUrl = page.url()
      expect(currentUrl).toContain('/login')
    })

    test('登录重定向', async ({ page, mockApi }) => {
      const user = mockApi.registerUser()
      await page.goto('/login?redirect=/dashboard/devices')
      await page.getByLabel('用户名').fill(user.username)
      await page.locator('input[aria-label="密码"]').fill(user.password)
      await page.locator('button:has-text("登录")').click()
      await expect(page).toHaveURL(/\/dashboard\/devices/, { timeout: 15000 })
    })

    test('redirect 提示', async ({ page }) => {
      await page.goto('/login?redirect=/dashboard/license')
      await expect(page.getByText('请先登录后继续')).toBeVisible()
    })

    test('忘记密码展开', async ({ page }) => {
      await page.goto('/login')
      await page.getByText('忘记密码？').first().click()
      await expect(page.getByText('重置密码').first()).toBeVisible()
    })

    test('忘记密码提交', async ({ page, mockApi }) => {
      mockApi.registerUser()
      await page.goto('/login')
      await page.getByText('忘记密码？').first().click()
      await page.waitForTimeout(500)
      // 重置区域的输入框现在用独有的 label（不重复）
      await page.getByRole('textbox', { name: '重置账号' }).fill('testuser')
      await page.getByRole('textbox', { name: '密保答案' }).fill('Fluffy')
      await page.getByRole('textbox', { name: '新密码' }).fill('NewPass456!')
      await page.locator('button:has-text("重置密码")').click()
      await page.waitForTimeout(2000)
      await expect(page.getByText('密码已重置').first()).toBeVisible({ timeout: 10000 })
    })

    test('跳转注册', async ({ page }) => {
      await page.goto('/login')
      await page.locator('a[href="/register"]').first().click()
      await expect(page).toHaveURL(/\/register/)
    })
  })
})
