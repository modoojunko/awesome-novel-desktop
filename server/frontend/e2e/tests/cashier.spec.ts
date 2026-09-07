import type { Page } from '@playwright/test'
import { test, expect } from '../fixtures'
import type { MockApi } from '../mocks/api-handlers'

async function gotoPay(page: Page): Promise<void> {
  await page.goto('/')
  await page.evaluate(() => localStorage.setItem('token', 'e2e-token'))
  await page.goto('/pay')
}

/** 选卡 → 去支付 → 协议弹窗打钩 → 确认，进入 waiting */
async function enterWaiting(page: Page): Promise<void> {
  await page.getByText('包年').first().click()
  await page.getByRole('button', { name: '去支付' }).click()
  const modal = page.locator('.mcard')
  await expect(modal).toBeVisible({ timeout: 10000 })
  // 未打钩时确认按钮禁用（协议留痕硬约束）
  await expect(modal.getByRole('button', { name: '阅读并同意，去支付' })).toBeDisabled()
  await modal.locator('input[type="checkbox"]').check()
  await modal.getByRole('button', { name: '阅读并同意，去支付' }).click()
  await expect(page.getByText('微信扫码支付')).toBeVisible({ timeout: 10000 })
}

test.describe('收银台', () => {
  test.beforeEach(async ({ mockApi }) => {
    mockApi.registerUser()
  })

  test('选套餐卡 → 协议弹窗 → 二维码等待态', async ({ page, mockApi }) => {
    mockApi.setPayHint('NOTPAY')
    await gotoPay(page)
    // 默认=包月 tab + PRO 档（s-pay-plans-picker：原 popular 默认包年已改）
    await expect(page.getByText('已选')).toBeVisible({ timeout: 10000 })
    await enterWaiting(page)
    await expect(page.getByText(/SE2ENEWORDER0001/)).toBeVisible()
    await expect(page.getByText(/二维码有效期剩/)).toBeVisible()
    // 二维码本地 canvas 渲染（aria-label 定位；code_url 不外发第三方服务）
    await expect(page.getByLabel('微信支付二维码')).toBeVisible()
  })

  test('生效期付费用户看到换档引导（先退再买+排队提醒）；免费档不显示', async ({ page, mockApi }) => {
    // 付费档：notice 出现且三要素齐（三步引导/排队提醒/我的订单出口）
    mockApi.setLicense({ tier: 'pro', remaining_sec: 20 * 86400 })
    await gotoPay(page)
    const tip = page.locator('.notice.info.pay-notice').first()
    await expect(tip).toBeVisible({ timeout: 10000 })
    await expect(tip).toContainText('想换更高档')
    await expect(tip).toContainText('排队至原套餐到期后才计时')
    await expect(tip.locator('a[href="/dashboard/orders"]')).toBeVisible()
    // 免费档：不渲染（对照，spec 第二 scenario）
    mockApi.setLicense({ tier: 'free', remaining_sec: 0 })
    await page.reload()
    await expect(page.locator('.notice.info.pay-notice')).toHaveCount(0)
  })

  test('协议弹窗提供全文直达链接（勾选前可读、新标签、无幽灵文书名）', async ({ page }) => {
    await gotoPay(page)
    await page.getByRole('button', { name: '去支付' }).click()
    const modal = page.locator('.mcard')
    await expect(modal).toBeVisible({ timeout: 10000 })
    // 勾选前即可见全文入口；href 指向真实法律文档（只验属性不触发导航）。
    // 全文行与勾选行各有两链接，按容器分域避免 strict mode 撞多元素
    const fullRow = modal.locator('.pay-terms-full')
    await expect(fullRow.locator('a[href="/legal/payment-notice.html"][target="_blank"]')).toBeVisible()
    await expect(fullRow.locator('a[href="/legal/refund-policy.html"][target="_blank"]')).toBeVisible()
    await expect(modal.locator('.pay-agree a[href="/legal/payment-notice.html"][target="_blank"]')).toBeVisible()
    await expect(modal.locator('.pay-agree a[href="/legal/refund-policy.html"][target="_blank"]')).toBeVisible()
    // 标题不引用文书名；全文行版本号跟接口单源（mock 返回 v2026.08）
    await expect(modal.getByText('确认购买', { exact: true })).toBeVisible()
    await expect(fullRow).toContainText('《付费须知》（v2026.08）')
    await expect(fullRow).toContainText('《退款政策》（v2026.08）')
  })

  test('支付成功 → 已到货待激活 → 立即激活就地生效', async ({ page, mockApi }) => {
    mockApi.setPayHint('SUCCESS')
    await gotoPay(page)
    await enterWaiting(page)
    // 轮询（3s）或手动查单命中 → success；直接点手动查单加速
    await page.getByText('我已支付，帮我查一下到账').click()
    await expect(page.getByText('支付成功')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('已到货，待激活')).toBeVisible()
    // 立即激活=就地真激活（不再只是跳转我的套餐）；成功后标题与到期信息联动
    await page.getByRole('button', { name: '立即激活' }).click()
    await expect(page.getByText('已激活，计时中')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(/到期/)).toBeVisible()
    await expect(page.getByRole('button', { name: '立即激活' })).toHaveCount(0)
  })

  test('手动查单未支付成功 → 反馈可重试', async ({ page, mockApi }) => {
    mockApi.setPayHint('PAYERROR')
    await gotoPay(page)
    await enterWaiting(page)
    await page.getByText('我已支付，帮我查一下到账').click()
    await expect(page.getByText(/本次支付未成功/)).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(/二维码仍然有效/)).toBeVisible()
    await page.getByRole('button', { name: '返回重试' }).click()
    await expect(page.getByText('微信扫码支付')).toBeVisible()
  })

  test('取消支付返回选卡', async ({ page, mockApi }) => {
    mockApi.setPayHint('NOTPAY')
    await gotoPay(page)
    await enterWaiting(page)
    await page.getByRole('button', { name: '取消支付' }).click()
    await expect(page.getByText('升级套餐，解锁全部写作能力')).toBeVisible({ timeout: 10000 })
  })

  test('下单失败 → failCreate 可重试', async ({ page, mockApi }) => {
    mockApi.failCreateOrder(1)
    await gotoPay(page)
    await page.getByRole('button', { name: '去支付' }).click()
    const modal = page.locator('.mcard')
    await modal.locator('input[type="checkbox"]').check()
    await modal.getByRole('button', { name: '阅读并同意，去支付' }).click()
    await expect(page.getByText('订单创建失败')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(/没有产生扣款/)).toBeVisible()
    await page.getByRole('button', { name: '重试' }).click()
    // 重试回选卡态，再走一遍成功
    await page.getByRole('button', { name: '去支付' }).click()
    await page.locator('.mcard input[type="checkbox"]').check()
    await page.locator('.mcard').getByRole('button', { name: '阅读并同意，去支付' }).click()
    await expect(page.getByText('微信扫码支付')).toBeVisible({ timeout: 10000 })
  })

  test('切换选择重置协议勾选', async ({ page }) => {
    await gotoPay(page)
    await page.locator('.pay-tabs button', { hasText: '包月' }).click()
    await page.getByRole('button', { name: '去支付' }).click()
    await page.locator('.mcard input[type="checkbox"]').check()
    await page.locator('.mcard').getByRole('button', { name: '再想想' }).click()
    // 换时长后 must 重打钩（goPay 重置 termsRead）
    await page.locator('.pay-tabs button', { hasText: '包季' }).click()
    await page.getByRole('button', { name: '去支付' }).click()
    await expect(page.locator('.mcard input[type="checkbox"]')).not.toBeChecked()
  })
})

test.describe('选套餐区·三档矩阵（s-pay-plans-picker）', () => {
  test.beforeEach(async ({ mockApi }) => {
    mockApi.registerUser()
  })

  test('默认包月+PRO，免费列锚点与 MAX 预告卡', async ({ page }) => {
    await gotoPay(page)
    await expect(page.getByText('已选')).toBeVisible({ timeout: 10000 })
    // 时长 tab 默认包月
    await expect(page.locator('.pay-tabs button.on')).toHaveText(/包月/)
    // 购买条=PRO · 包月（30 天）· ¥30
    await expect(page.locator('.pay-purchase-name')).toHaveText('PRO · 包月（30 天）')
    await expect(page.locator('.pay-purchase-amount')).toHaveText('¥30')
    // 免费列=对比锚点（当前方案 + ¥0）；MAX=预告卡（即将推出，不可购）
    await expect(page.locator('.pay-card-free').filter({ hasText: '免费' })).toContainText('当前方案')
    await expect(page.getByText('即将推出')).toBeVisible()
    // 「最受欢迎」pill 与人数：服务端规则未实现前一律不渲染（广告法红线）
    await expect(page.getByText('最受欢迎')).toHaveCount(0)
  })

  test('切时长 tab 三档价格联动 + 折扣徽标单源', async ({ page }) => {
    await gotoPay(page)
    await expect(page.locator('.pay-purchase-name')).toHaveText('PRO · 包月（30 天）', { timeout: 10000 })
    // 季度：¥72 + 划线原价 ¥80 + tab 徽标 9折 + 已省 ¥8（全部读 discount_display/差值，无前端换算）
    await page.locator('.pay-tabs button', { hasText: '包季' }).click()
    await expect(page.locator('.pay-purchase-amount')).toHaveText('¥72')
    await expect(page.locator('.pay-card-was')).toHaveText('原价 ¥80 元')
    await expect(page.locator('.pay-purchase-save')).toHaveText('已省 ¥8')
    await expect(page.locator('.pay-tabs button', { hasText: '包季' })).toContainText('9折')
    // 年度：¥239.2（fmtPrice 去尾零口径）
    await page.locator('.pay-tabs button', { hasText: '包年' }).click()
    await expect(page.locator('.pay-purchase-amount')).toHaveText('¥239.2')
    await expect(page.locator('.pay-tabs button', { hasText: '包年' })).toContainText('8折')
  })

  test('免费列与预告卡不可选', async ({ page }) => {
    await gotoPay(page)
    await expect(page.locator('.pay-purchase-name')).toHaveText('PRO · 包月（30 天）', { timeout: 10000 })
    await page.locator('.pay-card-free').filter({ hasText: '免费' }).click()
    await expect(page.locator('.pay-purchase-name')).toHaveText('PRO · 包月（30 天）')
    await page.locator('.pay-card-soon').click()
    await expect(page.locator('.pay-purchase-name')).toHaveText('PRO · 包月（30 天）')
  })

  test('停售两分支：已登录停售态 / 未登录走守卫重定向（原单分支混用已拆）', async ({ page, mockApi }) => {
    mockApi.setPurchaseEnabled(false)
    await gotoPay(page)
    // 已登录（token 在）→ 停售态（不再误显「去登录」）
    await expect(page.getByText('暂时无法购买')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: '返回控制台' })).toBeVisible()
    // 未登录：/pay 本就 requiresAuth，守卫先重定向登录页并带 redirect（页内态〇仅为防御性兜底）
    await page.evaluate(() => localStorage.removeItem('token'))
    await page.goto('/pay')
    await expect(page).toHaveURL(/\/login\?redirect=\/pay/, { timeout: 15000 })
  })

  test('目录拉取失败 → 降级骨架价格留白', async ({ page, mockApi }) => {
    mockApi.setSkusGate({ fail: true })
    await page.goto('/')
    await page.evaluate(() => localStorage.setItem('token', 'e2e-token'))
    await page.goto('/pay')
    // 付费档骨架价格留白 ×3，免费列 ¥0 保留，购买条不渲染
    await expect(page.getByText('价格获取失败，请刷新重试')).toHaveCount(3, { timeout: 10000 })
    await expect(page.locator('.pay-card-free').filter({ hasText: '当前方案' }).first()).toContainText('¥0')
    await expect(page.locator('.pay-purchase')).toHaveCount(0)
  })

  test('popular 指向 planned 档 SKU → 默认档回落 PRO（守卫）', async ({ page, mockApi }) => {
    mockApi.setSkus({
      purchase_enabled: true,
      agreement_version: 'v2026.08',
      tiers: [
        { key: 'free', label: '免费', is_live: true, is_planned: false, selling_points: [] },
        { key: 'pro', label: 'PRO', is_live: true, is_planned: false, selling_points: [] },
        { key: 'max', label: 'MAX', is_live: false, is_planned: true, selling_points: [] },
      ],
      skus: [
        { sku_key: 'pro_monthly', tier_key: 'pro', period: 'monthly', period_days: 30, base_price_fen: 3000, discount_display: '', price_fen: 3000, device_limit: 3 },
        { sku_key: 'pro_yearly', tier_key: 'pro', period: 'yearly', period_days: 365, base_price_fen: 29900, discount_display: '8折', price_fen: 23920, device_limit: 5 },
      ],
      popular_sku: 'max_yearly',
    })
    await gotoPay(page)
    await expect(page.locator('.pay-purchase-name')).toHaveText('PRO · 包月（30 天）', { timeout: 10000 })
  })

  test('目录返回但无在售 SKU → 同款降级骨架（spec：失败或为空；防 live 无货档误显「即将推出」）', async ({ page, mockApi }) => {
    mockApi.setSkus({
      purchase_enabled: true,
      agreement_version: 'v2026.08',
      tiers: [
        { key: 'pro', label: 'PRO', is_live: true, is_planned: false, selling_points: [] },
        { key: 'max', label: 'MAX', is_live: false, is_planned: true, selling_points: [] },
      ],
      skus: [],
      popular_sku: '',
    })
    await gotoPay(page)
    // 付费档骨架价格留白 ×3，免费列保留，购买条不渲染，且不出现「即将推出」预告卡
    await expect(page.getByText('价格获取失败，请刷新重试')).toHaveCount(3, { timeout: 10000 })
    await expect(page.locator('.pay-card-free').filter({ hasText: '当前方案' }).first()).toContainText('¥0')
    await expect(page.getByText('即将推出')).toHaveCount(0)
    await expect(page.locator('.pay-purchase')).toHaveCount(0)
  })
})

test.describe('URL 参数预选套餐（s-pay-landing-plans：落地页带参跳转消费端）', () => {
  test.beforeEach(async ({ mockApi }) => {
    mockApi.registerUser()
  })

  test('合法参数预选：/pay?period=yearly&tier=pro → 包年+PRO', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.setItem('token', 'e2e-token'))
    await page.goto('/pay?period=yearly&tier=pro')
    await expect(page.getByText('已选')).toBeVisible({ timeout: 10000 })
    await expect(page.locator('.pay-tabs button.on')).toHaveText(/包年/)
    await expect(page.locator('.pay-purchase-name')).toHaveText('PRO · 包年（365 天）')
    await expect(page.locator('.pay-purchase-amount')).toHaveText('¥239.2')
  })

  test('非法参数回落默认链：不存在档位/不在售时长 → 包月+popular 档', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.setItem('token', 'e2e-token'))
    await page.goto('/pay?period=daily&tier=max')
    await expect(page.getByText('已选')).toBeVisible({ timeout: 10000 })
    // popular_sku=pro_yearly→pro 档，时长回落包月；max 档不产生选中
    await expect(page.locator('.pay-tabs button.on')).toHaveText(/包月/)
    await expect(page.locator('.pay-purchase-name')).toHaveText('PRO · 包月（30 天）')
    await expect(page.locator('.pay-purchase-amount')).toHaveText('¥30')
  })
})
