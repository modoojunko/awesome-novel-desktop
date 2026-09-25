import { expect, test } from '../fixtures'

/**
 * 下载弹窗（relicense-proprietary）：latest.json 双态 mock＋EULA 同意微文案。
 *
 * 原 landing.spec 只覆盖「打开弹窗见双平台直链」，无 latest.json mock（弹窗恒走
 * 降级态、不产出版本相关断言）。本文件补齐：
 * - 成功态：版本 pill 与直链取线上版本；「查看更新说明 →」同源 notes.html 且与版本一致；
 * - 降级态：兜底版本可下载，但**不渲染**版本相关次级链接（兜底版本可能已滑出 CDN 保留窗）；
 * - 两态恒见「下载即表示同意《最终用户许可协议》」微文案（链 /legal/eula.html）。
 */

const LATEST = { version: '0.25', notes: 'e2e mock' }

test.describe('下载弹窗 · latest.json 双态', () => {
  test('成功态：版本 pill 与双平台直链取线上版本，更新说明同源且同版本', async ({ page }) => {
    await page.route('**/download/latest.json', (r) =>
      r.fulfill({ json: LATEST }),
    )
    await page.goto('/')
    await page.getByRole('button', { name: '免费下载' }).click()
    const modal = page.locator('.mcard')
    await expect(modal).toBeVisible({ timeout: 10_000 })

    // 版本 pill 直显线上版本
    await expect(modal.getByText('v0.25').first()).toBeVisible()
    // 双平台直链按线上版本拼接
    await expect(page.getByRole('link', { name: /下载 Windows/ })).toHaveAttribute(
      'href',
      /AI_Novel_Setup_v0\.25\.exe$/,
    )
    await expect(page.getByRole('link', { name: /下载 macOS/ })).toHaveAttribute(
      'href',
      /AI_Novel_mac_v0\.25\.dmg$/,
    )
    // 「查看更新说明 →」＝官网同站 notes.html，且与 pill 同版本（成功态「永不 404」成立域）
    const notes = modal.getByRole('link', { name: '查看更新说明 →' })
    await expect(notes).toBeVisible()
    await expect(notes).toHaveAttribute(
      'href',
      'https://www.awesomenovel.com/download/v0.25/notes.html',
    )
    // EULA 同意微文案恒在，链官网法律页
    const consent = modal.getByRole('link', { name: '《最终用户许可协议》' })
    await expect(consent).toBeVisible()
    await expect(consent).toHaveAttribute('href', '/legal/eula.html')
  })

  test('降级态：兜底版本可下载，不渲染版本相关次级链接，同意微文案仍在', async ({ page }) => {
    // latest.json 不可达（fetch 抛错）→ fetchLatestRelease 降级
    await page.route('**/download/latest.json', (r) => r.abort())
    await page.goto('/')
    await page.getByRole('button', { name: '免费下载' }).click()
    const modal = page.locator('.mcard')
    await expect(modal).toBeVisible({ timeout: 10_000 })

    // 降级 warn pill（兜底版本提示）
    await expect(modal.locator('.dl-pill.warn')).toBeVisible()
    // 兜底版本仍给双平台直链
    await expect(page.getByRole('link', { name: /下载 Windows/ })).toBeVisible()
    await expect(page.getByRole('link', { name: /下载 macOS/ })).toBeVisible()
    // 版本相关次级链接不渲染（relicense-proprietary：兜底版本可能已滑出保留窗）
    await expect(modal.getByRole('link', { name: '查看更新说明 →' })).toHaveCount(0)
    // 同意微文案不依赖版本，恒在
    await expect(modal.getByRole('link', { name: '《最终用户许可协议》' })).toBeVisible()
  })
})
