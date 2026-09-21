import { test, expect } from '../fixtures'

test.describe('Landing Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('显示品牌标题和副标题', async ({ page }) => {
    await expect(page.getByText('人铸灵魂')).toBeVisible()
    await expect(page.getByText('AI 是笔，你才是作家')).toBeVisible()
  })

  test('显示下载按钮和查看套餐按钮', async ({ page }) => {
    await expect(page.getByRole('button', { name: '免费下载' })).toBeVisible()
    await expect(page.getByRole('link', { name: '查看套餐' })).toBeVisible()
  })

  test('免费下载打开弹窗（双平台直链）', async ({ page }) => {
    // #214 起下载走弹窗：打开后才渲染双平台安装包直链
    await page.getByRole('button', { name: '免费下载' }).click()
    await expect(page.locator('.mcard')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('link', { name: /下载 Windows/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /下载 macOS/ })).toBeVisible()
  })

  test('导航栏显示登录和注册链接（未登录）', async ({ page }) => {
    const loginBtn = page.locator('.mkt-nav a[href="/login"]').first()
    await expect(loginBtn).toBeVisible()
    const registerBtn = page.locator('.mkt-nav a[href="/register"]').first()
    await expect(registerBtn).toBeVisible()
  })

  test('导航栏显示「我的账号」（已登录）', async ({ page, mockApi }) => {
    mockApi.registerUser()
    await page.goto('/')
    await page.evaluate((token) => localStorage.setItem('token', token), mockApi.token)
    await page.goto('/')
    await expect(page.locator('.mkt-nav a[href="/dashboard"]')).toBeVisible()
    await expect(page.locator('.mkt-nav a[href="/login"]')).not.toBeVisible()
    // 已登录 Hero：进入控制台与免费下载并存，登录后仍有下载入口
    await expect(page.getByRole('link', { name: '进入控制台' })).toBeVisible()
    await expect(page.getByRole('button', { name: '免费下载' })).toBeVisible()
  })

  test('功能区块存在六个工作流步骤', async ({ page }) => {
    await page.locator('#features').scrollIntoViewIfNeeded()
    const steps = ['建书', '设定', '大纲', '章纲', '写作', '归档']
    for (const step of steps) {
      await expect(page.getByText(step).first()).toBeVisible()
    }
  })

  test('套餐区=收银台同 IA：时长 tab×三档对比列（s-pay-landing-plans）', async ({ page }) => {
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    // 时长 tab 默认包月（与收银台同默认）；列序=免费 + PRO + MAX
    await expect(page.locator('.plans-tabs button.on')).toHaveText(/包月/)
    await expect(page.locator('#pricing .mkt-plan h3')).toHaveText(['免费', 'PRO', 'MAX'])
    // MAX planned → 预告卡（即将推出，不可购）
    await expect(page.locator('#pricing .plans-soon')).toContainText('MAX')
    // 淘宝死链全站清零保持（含页脚/激活指南）
    await expect(page.locator('a[href*="taobao"]')).toHaveCount(0)
    await expect(page.getByText(/淘宝/)).toHaveCount(0)
  })

  test('tab 切换联动三档价格（同源 /pay/skus）', async ({ page }) => {
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    // 包月：PRO ¥30；免费列 ¥0 恒定
    const proCol = page.locator('#pricing .mkt-plan', { hasText: 'PRO' })
    await expect(proCol).toContainText('¥30')
    // 包季：¥72 + 划线原价 ¥80 + tab 徽标 9折（全部读接口单源）
    await page.locator('.plans-tabs button', { hasText: '包季' }).click()
    await expect(proCol).toContainText('¥72')
    await expect(proCol).toContainText('¥80')
    await expect(page.locator('.plans-tabs button', { hasText: '包季' })).toContainText('9折')
    // 包年：¥239.2（fmtPrice 去尾零）+ 结构行随 SKU 联动（365 天 · 5 台设备）
    await page.locator('.plans-tabs button', { hasText: '包年' }).click()
    await expect(proCol).toContainText('¥239.2')
    await expect(proCol).toContainText('365 天 · 最多 5 台设备')
    await expect(page.locator('.plans-tabs button', { hasText: '包年' })).toContainText('8折')
  })

  test('免费列匿名语义：注册导流（非「当前方案」）', async ({ page }) => {
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    const freeCol = page.locator('#pricing .mkt-plan.free').filter({ hasText: '免费' })
    await expect(freeCol).toContainText('¥0')
    await expect(freeCol).toContainText('不含 AI 能力')
    await expect(freeCol.getByRole('link', { name: '注册领取 7 天试用' }).first()).toBeVisible()
    // 「当前方案」是收银台登录态语义，落地页不得出现
    await expect(page.locator('#pricing').getByText('当前方案')).toHaveCount(0)
  })

  test('最受欢迎徽标挂 PRO 档列（随 popular_sku 单源）', async ({ page }) => {
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    await expect(page.locator('#pricing .mkt-plan.pro h3')).toHaveText('PRO')
    await expect(page.locator('#pricing .mkt-plan.pro .mkt-pro-pill')).toHaveText('最受欢迎')
  })

  test('购买入口带参跳收银台（选中规格延续）', async ({ page }) => {
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    const buy = page.locator('#pricing .mkt-plan', { hasText: 'PRO' }).getByRole('link', { name: '立即购买' })
    await expect(buy).toHaveAttribute('href', '/pay?period=monthly&tier=pro')
    await page.locator('.plans-tabs button', { hasText: '包年' }).click()
    await expect(buy).toHaveAttribute('href', '/pay?period=yearly&tier=pro')
  })

  test('停售时价格留白、徽标摘除、结构与预告卡保留', async ({ page, mockApi }) => {
    mockApi.setSkus({ purchase_enabled: false, agreement_version: 'v2026.08', tiers: [
      { key: 'free', label: '免费', is_live: true, is_planned: false, selling_points: [] },
      { key: 'pro', label: 'PRO', is_live: true, is_planned: false, selling_points: ['含免费全部功能', 'AI 生成正文（流式）'] },
      { key: 'max', label: 'MAX', is_live: false, is_planned: true, selling_points: [] },
    ], skus: [
      { sku_key: 'pro_monthly', tier_key: 'pro', period: 'monthly', period_days: 30, base_price_fen: 3000, discount_display: '', price_fen: 3000, device_limit: 3 },
      { sku_key: 'pro_quarterly', tier_key: 'pro', period: 'quarterly', period_days: 90, base_price_fen: 8000, discount_display: '9折', price_fen: 7200, device_limit: 3 },
      { sku_key: 'pro_yearly', tier_key: 'pro', period: 'yearly', period_days: 365, base_price_fen: 29900, discount_display: '8折', price_fen: 23920, device_limit: 5 },
    ], popular_sku: 'pro_yearly' })
    await page.goto('/')
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    // PRO live 列价格留白 ×1（MAX 预告卡本就无价格）；免费列 ¥0 不受影响
    await expect(page.getByText('价格见收银台')).toHaveCount(1)
    await expect(page.locator('#pricing').getByText('¥30')).toHaveCount(0)
    await expect(page.locator('#pricing .mkt-pro-pill')).toHaveCount(0)
    await expect(page.getByText('即将推出')).toBeVisible()
    await expect(page.locator('#pricing a[href^="/pay"]').first()).toBeVisible()
  })

  test('目录不可达 → 降级骨架（价格留白×3，tab 消失，注册与收银台入口仍可达）', async ({ page, mockApi }) => {
    mockApi.setSkusGate({ fail: true })
    await page.goto('/')
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    await expect(page.getByText('价格见收银台')).toHaveCount(3, { timeout: 10000 })
    await expect(page.locator('#pricing .plans-tabs')).toHaveCount(0)
    await expect(page.locator('#pricing a[href="/pay"]').first()).toBeVisible()
    await expect(page.locator('#pricing a[href="/register"]').first()).toBeVisible()
  })

  test('激活指南区块三步流程', async ({ page }) => {
    await page.locator('#guide').scrollIntoViewIfNeeded()
    await expect(page.getByText('下载安装')).toBeVisible()
    await expect(page.getByText('注册账号')).toBeVisible()
    await expect(page.getByText('激活 License')).toBeVisible()
  })

  test('底部页脚包含链接和版权', async ({ page }) => {
    const footer = page.locator('footer')
    // 版权行 = ©年 + 主体 + 组合名：主体名与品牌名是字面量＝故意钉住
    // （主体与 brand/brand.json 的 company 同值，改名须同批改本断言）
    await expect(footer.getByText(/© \d{4} 星纬（海口）投资有限公司 · 爱小说 · AI Novel/)).toBeVisible()
    await expect(footer.getByText('你的小说永远属于你')).toBeVisible()
  })

  test('锚点导航：点击查看套餐跳转到 pricing', async ({ page }) => {
    await page.getByRole('link', { name: '查看套餐' }).click()
    await expect(page.locator('#pricing')).toBeVisible()
  })

  test('「已有激活码」链接跳转登录页', async ({ page }) => {
    await page.getByRole('link', { name: /去控制台激活/ }).click()
    await expect(page).toHaveURL(/\/login/)
  })

  test('桌面端 > lg 时导航菜单可见', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto('/')
    await expect(page.locator('.mkt-nav a[href="/#features"]')).toBeVisible()
    await expect(page.locator('.mkt-nav a[href="/#pricing"]')).toBeVisible()
  })

  test('免费列注册 CTA 跳注册页（原 Trial 卡导流职责并入免费列）', async ({ page }) => {
    await page.locator('#pricing').scrollIntoViewIfNeeded()
    const registerBtn = page.locator('#pricing a[href="/register"]').first()
    await expect(registerBtn).toBeVisible()
  })
})
