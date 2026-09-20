import { test, expect } from '../fixtures'

test.describe('OAuth 设备授权页 (/auth)', () => {
  test('无 pc_hash 参数时显示警告', async ({ page }) => {
    await page.goto('/auth')
    await expect(page.getByText('无效的授权请求')).toBeVisible()
  })

  test('有效参数显示授权表单', async ({ page }) => {
    await page.goto('/auth?pc_hash=test_hash_123&challenge=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
    await expect(page.getByText('设备授权').first()).toBeVisible()
    await expect(page.getByText('桌面应用请求绑定此设备')).toBeVisible()
  })

  test('成功授权显示成功视图', async ({ page, mockApi }) => {
    mockApi.registerUser()
    await page.goto('/auth?pc_hash=test_hash_123&challenge=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
    const inputs = page.locator('input')
    await inputs.nth(0).fill('testuser')
    await inputs.nth(1).fill('Pass123!')
    await page.locator('button:has-text("授权登录")').click()
    await expect(page.getByText('授权成功')).toBeVisible()
    await expect(page.getByText('此页面可以关闭了')).toBeVisible()
  })

  test('冷启动 503 自愈：授权请求撞网关 503 后延迟重试一次成功', async ({ page, mockApi }) => {
    mockApi.registerUser()
    // 首个 authorize 撞冷启动（网关 503、无业务 code）→ 页面自愈：延迟重试一次后成功。
    // 与生产语义对齐：503 响应体无 code（传输层失败），重试请求 fallback 到 mock 层。
    let authorizeCalls = 0
    await page.route('**/api/authorize', async (route) => {
      authorizeCalls += 1
      if (authorizeCalls === 1) {
        await route.fulfill({ status: 503, contentType: 'text/plain', body: 'Service Unavailable' })
      } else {
        await route.fallback()
      }
    })
    await page.goto('/auth?pc_hash=test_hash_123&challenge=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
    const inputs = page.locator('input')
    await inputs.nth(0).fill('testuser')
    await inputs.nth(1).fill('Pass123!')
    await page.locator('button:has-text("授权登录")').click()
    await expect(page.getByText('授权成功')).toBeVisible({ timeout: 10_000 })
    expect(authorizeCalls).toBe(2)
    // 传输层失败不甩「网络错误」红条给用户（自愈期间走中性提示）
    await expect(page.getByText('网络连接失败')).toHaveCount(0)
  })

  test('提交空表单保持表单可见', async ({ page, mockApi }) => {
    mockApi.registerUser()
    await page.goto('/auth?pc_hash=test_hash_123&challenge=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
    // 空表单时按钮应禁用，表单保持可见
    await expect(page.locator('button:has-text("授权登录")')).toBeDisabled()
    await expect(page.getByText('设备授权').first()).toBeVisible()
  })

  test('缺少配对信息（旧版桌面端）显示升级出口', async ({ page }) => {
    await page.goto('/auth?pc_hash=test_hash_123')
    // #453（s-auth-outdated-signal）后的口径：不断言版本旧，只说此版本需更新
    await expect(page.getByText('此版本的桌面应用需要更新后才能完成授权')).toBeVisible()
    await expect(page.getByText('下载 Windows 版').or(page.getByText('前往下载最新版桌面应用'))).toBeVisible()
    await expect(page.locator('input')).toHaveCount(0)
  })

  test('底部有注册链接', async ({ page }) => {
    await page.goto('/auth?pc_hash=test_hash_123&challenge=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef')
    // 注册链接须携带授权 query（pc_hash 等）：注册成功后回 /auth 续完授权流，不丢上下文
    await expect(page.locator('a[href*="/register"]').first()).toBeVisible()
    await expect(page.locator('a[href*="pc_hash=test_hash_123"]').first()).toBeVisible()
  })
})
