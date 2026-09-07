import type { Page, Route } from '@playwright/test'
import { createTestUser, createTestDevice, type TestUser, type TestDevice } from './test-data'

/** /api/pay/license/codes 明细行（订单来源台账行；手工码不进明细） */
export interface TestLicenseCode {
  code_id: string
  order_no: string
  tier: string
  duration_days: number
  status: string
  activated_at: string
  expires_at: string
  grant_start: string
}

/** /api/pay/license 响应（S端 我的套餐聚合视图；license-grants-pagination 瘦身后无明细内嵌） */
export interface TestLicense {
  tier: string
  remaining_sec: number
  remaining_desc: string
  max_expires_at: string | null
  pending_count: number
  /** 订单来源套餐行总数；缺省由 licenseCodes 列表推导（旧后端退化测试传 0 且不设明细） */
  code_count?: number
}

/** /api/pay/orders 列表项（S端 我的订单） */
export interface TestOrder {
  order_no: string
  status: string
  amount_fen: number
  snapshot: Record<string, unknown>
  created_at: string
  paid_at: string
  refunded_at: string
  refund_amount_fen?: number | null
  remaining_pay_seconds?: number | null
  fulfilled_at?: string
  refund_requested_at?: string
  /** 到货快照（订单详情/激活流转）；缺省由 paid_at 推导 pending_activation */
  fulfillment?: { status: string; activated_at: string; expires_at: string; grant_start?: string } | null
}

/**
 * MockApi — 拦截所有 /api/* 请求并返回模拟数据。
 * 使用精确路径匹配避免干扰 Vite 的模块加载。
 */
export class MockApi {
  private page: Page
  private currentUser: TestUser | null = null
  private devices: TestDevice[] = []
  private license: TestLicense | null = null
  private orders: TestOrder[] = []
  /** /api/pay/license/codes 明细数据源（syncLicenseFromCodes 由 orders 推导，或 setLicenseCodes 直设） */
  private licenseCodes: TestLicenseCode[] = []
  /** orders 列表 GET 门控（orders-page-latency：延迟/失败，测切版保留旧列表、失败不误报空态） */
  private ordersGate: { delayMs?: number; fail?: boolean } | null = null
  /** 套餐明细列表 GET 门控（同 ordersGate 语义，license-grants-pagination） */
  private codesGate: { delayMs?: number; fail?: boolean } | null = null
  /** 退款预览覆写（测拒绝态：below_one_fen / over_one_year / refundable:false） */
  private refundPreviewOverride: { refundable: boolean; reason: string; refund_fen?: number; remaining_desc?: string } | null = null
  /** 冷静期剩余秒数（e2e 用短窗口） */
  private refundCooldown = 300
  /** 激活失败模式（测不可激活错误出路；触发一次后自动复位 none） */
  private activateFailMode: 'none' | 'not_fulfilled' | 'not_activatable' = 'none'
  /** 下单连续失败次数（failCreate 态测试） */
  private createOrderFailCount = 0
  /** 查单 hint（SUCCESS 转成功态；NOTPAY/PAYERROR/CLOSED） */
  private payHint = 'NOTPAY'
  /** 购买开关（off → 收银台登录卡态） */
  private purchaseEnabled = true
  /** /api/pay/skus 覆写（landing 套餐区数据源；null = 用默认三档矩阵，结构与生产一致） */
  private skusOverride: Record<string, unknown> | null = null
  /** /api/pay/skus GET 门控（s-pay-plans-picker：失败→收银台降级骨架；同 codesGate 语义） */
  private skusGate: { delayMs?: number; fail?: boolean } | null = null
  /** 会话失效模式：/user/me 返回 HTTP 200 + code 1（与真实后端「用户不存在/未登录」一致） */
  private userMeDead = false
  /** 让接下来 N 次 /user/preferences 失败（测「保存失败→重试→落库」路径） */
  private preferencesFailCount = 0
  /** 失败形态：'500' = HTTP 500（有响应）；'network' = 连接拒绝（无响应，模拟冷启动 503 无 CORS） */
  private preferencesFailMode: '500' | 'network' = '500'
  /** account-deletion：撤销期态与未消耗权益开关（向导分支用） */
  private deletionPending = false
  private deletionDaysLeft = 15
  private deletionDeadline = '2026-09-14'
  private assetsBlocking = true
  private accountDeleted = false
  private assetRefundRequested = false
  private deletionAssetHasOrder = true
  private routes: string[] = [
    '**/api/web/login',
    '**/api/web/register',
    '**/api/user/me',
    '**/api/user/password',
    '**/api/user/security',
    '**/api/user/preferences',
    // account-deletion（注销向导/撤销期）
    '**/api/user/deletion-status',
    '**/api/user/deletion-assets',
    '**/api/user/deletion/refund-request',
    '**/api/user/deletion',
    '**/api/user/deletion/revoke',
    '**/api/devices/my',
    '**/api/devices/remove',
    '**/api/authorize',
    '**/api/reset_password',
    // ⚠️ 真实调用带 query（?pc_hash=），Playwright glob 匹配完整 URL，须以 * 收尾
    '**/api/check-auth*',
  ]

  constructor(page: Page) {
    this.page = page
  }

  /** 在每次测试前调用：重置状态 + 注册路由拦截 */
  async setup(): Promise<void> {
    this.currentUser = null
    this.devices = []
    this.userMeDead = false
    this.preferencesFailCount = 0
    this.skusOverride = null
    this.ordersGate = null
    this.codesGate = null
    this.licenseCodes = []
    this.deletionPending = false
    this.deletionDaysLeft = 15
    this.deletionDeadline = '2026-09-14'
    this.assetsBlocking = true
    this.assetRefundRequested = false
    this.accountDeleted = false
    // 兜底拦最先注册（Playwright 后注册者优先，兜底必须排最前）。
    // 用谓词而非 glob：'**/api/**' 会误吞 vite 模块 URL（/src/api/request.ts
    // 路径里也含 '/api/'，被答成 JSON 应用直接起不来，PR #217 调试实测）。
    // 漏出精确路由表的 /api 一律答 code 1——绝不穿透 vite proxy（CI 上
    // 19000 无人监听，漏网即门闩 15s×4 空转、页面用例集体超时），也绝不
    // 返回 code 2 误触发 401 登出。
    await this.page.route(
      (url) => url.pathname.startsWith('/api/'),
      (route) => route.fulfill(json(1, 'unmocked api'))
    )
    for (const url of this.routes) {
      await this.page.route(url, (route) => this.handler(route))
    }
    // pay 域最后用谓词注册（后注册者优先）：glob 对带 query/子路径的 URL
    // 匹配不稳（'**/api/pay/orders*' / '**/api/pay/**' 实测穿透 vite 代理，
    // 被 FastAPI 打回 {"detail":"Not Found"}），谓词与兜底拦同款语义最可靠。
    await this.page.route(
      (url) => url.pathname.startsWith('/api/pay/'),
      (route) => this.handler(route)
    )
  }

  registerUser(overrides: Partial<TestUser> = {}): TestUser {
    const user = createTestUser(overrides)
    this.currentUser = user
    this.devices = [
      createTestDevice({ is_current: true, activated: true }, 1),
      createTestDevice({ activated: false, reason: { code: 'limit_exceeded', message: '超出设备限额' } }, 2),
    ]
    return user
  }

  /** 无参调用=沿用当前用户（beforeEach registerUser 已建），仅刷新设备表 */
  setLoggedIn(user?: TestUser): void {
    if (user) this.currentUser = user
    this.devices = [
      createTestDevice({ is_current: true, activated: true }, 1),
      createTestDevice({ activated: true }, 2),
    ]
  }

  /** 模拟真实后端「会话失效」：残留 token 有效格式但用户已不存在/未登录（HTTP 200 + code 1） */
  setDeadSession(): void {
    this.currentUser = null
    this.userMeDead = true
  }

  /** 覆写 /api/pay/skus（landing 套餐区降级态测试用；传 null 恢复默认） */
  setSkus(v: Record<string, unknown> | null): void {
    this.skusOverride = v
  }

  /** skus 目录 GET 门控（失败/延迟；null 解除）——收银台降级骨架态测试用 */
  setSkusGate(gate: { delayMs?: number; fail?: boolean } | null): void {
    this.skusGate = gate
  }

  /** 设置 /api/pay/license 摘要（S端 首页/我的套餐卡数据源） */
  setLicense(m: Partial<TestLicense>): void {
    this.license = {
      tier: 'free',
      remaining_sec: 0,
      remaining_desc: '0 天',
      max_expires_at: null,
      pending_count: 0,
      ...m,
    }
  }

  /** 直设 /api/pay/license/codes 明细（license 页测试用）并同步聚合视图计数 */
  setLicenseCodes(list: TestLicenseCode[]): void {
    this.licenseCodes = list
    if (!this.license) this.setLicense({})
    this.license!.code_count = list.length
    this.license!.pending_count = list.filter((g) => g.status === 'pending_activation').length
  }

  /** 套餐明细列表 GET 门控（延迟/失败；null 解除） */
  setGrantsGate(gate: { delayMs?: number; fail?: boolean } | null): void {
    this.codesGate = gate
  }

  /** 设置 /api/pay/orders 列表（S端 我的订单/首页横幅数据源） */
  setOrders(list: TestOrder[]): void {
    // fulfillment 快照归一：已支付未显式给 fulfillment 的按状态推导（refunded→revoked，其余→pending_activation）
    this.orders = list.map((o) => ({
      ...o,
      fulfillment: o.fulfillment !== undefined
        ? o.fulfillment
        : (o.paid_at
            ? (o.status === 'refunded' ? { status: 'revoked', activated_at: '', expires_at: '' } : { status: 'pending_activation', activated_at: '', expires_at: '' })
            : null),
    }))
  }

  /** orders 列表 GET 门控（延迟/失败；null 解除） */
  setOrdersGate(gate: { delayMs?: number; fail?: boolean } | null): void {
    this.ordersGate = gate
  }

  /** 覆写退款预览结果（拒绝态测试） */
  setRefundPreview(p: { refundable: boolean; reason: string; refund_fen?: number; remaining_desc?: string } | null): void {
    this.refundPreviewOverride = p
  }

  /** 覆写冷静期剩余秒数（0 = 已归零仍 refund_pending 的过渡窗口） */
  setRefundCooldown(seconds: number): void {
    this.refundCooldown = seconds
  }

  /** 让接下来 N 次下单失败 */
  failCreateOrder(times = 1): void {
    this.createOrderFailCount = times
  }

  /** 设置查单结果 hint（收银台轮询/手动查单） */
  setPayHint(hint: 'SUCCESS' | 'NOTPAY' | 'PAYERROR' | 'CLOSED'): void {
    this.payHint = hint
  }

  /** 设置下一次激活失败（not_fulfilled=订单非到货态 / not_activatable=已激活或已收回） */
  failActivate(mode: 'not_fulfilled' | 'not_activatable'): void {
    this.activateFailMode = mode
  }

  /** 由 orders 的 fulfillment 快照同步 license 摘要与明细分页数据源（激活流转后保持一致） */
  private syncLicenseFromCodes(): void {
    const codes: TestLicenseCode[] = this.orders
      .filter((o) => o.fulfillment && o.fulfillment.status !== 'none')
      .map((o) => ({
        code_id: `O-${o.order_no}`,
        order_no: o.order_no,
        tier: (o.snapshot?.tier_key as string) ?? 'pro',
        duration_days: (o.snapshot?.period_days as number) ?? 30,
        status: o.fulfillment!.status,
        activated_at: o.fulfillment!.activated_at,
        expires_at: o.fulfillment!.expires_at,
        grant_start: o.fulfillment!.activated_at,
      }))
    this.licenseCodes = codes
    if (!this.license) this.license = { tier: 'free', remaining_sec: 0, remaining_desc: '0 天', max_expires_at: null, pending_count: 0 }
    this.license.code_count = codes.length
    this.license.pending_count = codes.filter((g) => g.status === 'pending_activation').length
    const active = codes.find((g) => g.status === 'active')
    if (active) {
      this.license.tier = 'pro'
      this.license.max_expires_at = active.expires_at
      this.license.remaining_sec = Math.max(0, Math.round((Date.parse(active.expires_at + 'Z') - Date.now()) / 1000))
      this.license.remaining_desc = `${Math.max(0, Math.round(this.license.remaining_sec / 86400))} 天`
    }
  }

  /** 设置购买开关（off = 收银台「登录后继续购买」态） */
  setPurchaseEnabled(on: boolean): void {
    this.purchaseEnabled = on
  }

  private refundStatusOf(orderStatus: string): string {
    if (orderStatus === 'refund_pending') return 'cooldown'
    if (orderStatus === 'refund_processing') return 'processing'
    if (orderStatus === 'refunded') return 'succeeded'
    return 'none'
  }

  /** account-deletion：进入撤销期态（登录返回 code 2 结构化状态；状态接口 pending） */
  setDeletionPending(pending = true): void {
    this.deletionPending = pending
  }

  /** account-deletion：是否存有未消耗权益（决定向导是否出现权益处置步） */
  setAssetsBlocking(blocking: boolean): void {
    this.assetsBlocking = blocking
  }

  /** account-deletion：账号已注销终态（登录返回 code 1 + deleted 标记） */
  setAccountDeleted(): void {
    this.accountDeleted = true
    this.deletionPending = false
  }

  /** 让接下来 N 次 /user/preferences 失败（times=0 关闭；mode 见字段注释） */
  failPreferences(times = 1, mode: '500' | 'network' = '500'): void {
    this.preferencesFailCount = times
    this.preferencesFailMode = mode
  }

  get token(): string {
    return this.currentUser?.token || ''
  }

  get username(): string {
    return this.currentUser?.username || ''
  }

  private async handler(route: Route): Promise<void> {
    const url = new URL(route.request().url())
    const path = url.pathname
    const method = route.request().method()

    // ── 预热探测（冷启动门闩）──
    // 真实后端对空 pc_hash 返回 code 1；任何带业务 code 的应答都代表「实例已热」，
    // 门闩（warmUpBackend）据此立即放行。不 mock 会穿透到真实网络，e2e 里门闩
    // 会空转重试 60s 导致所有页面数据用例超时。
    if (path === '/api/check-auth') {
      return route.fulfill(json(1, '缺少 pc_hash'))
    }

    // ── C端 冻结契约 ──
    if (path === '/api/authorize' && method === 'POST') {
      const body = route.request().postDataJSON()
      if (!body?.username || !body?.password) {
        return route.fulfill(json(1, '用户名或密码不能为空'))
      }
      return route.fulfill(json(0, {
        message: '设备授权成功',
        tier: 'trial',
        expires_at: new Date(Date.now() + 7 * 86400000).toISOString(),
      }))
    }

    if (path === '/api/reset_password' && method === 'POST') {
      return route.fulfill(json(0, { success: true }))
    }

    // ── 账号自助注销（account-deletion）──
    if (path === '/api/user/deletion-status' && method === 'GET') {
      if (!this.currentUser) return route.fulfill(json(1, '未登录'))
      if (this.accountDeleted) return route.fulfill(json(0, { pending: false, deleted: true }))
      if (this.deletionPending) {
        return route.fulfill(json(0, { pending: true, days_left: this.deletionDaysLeft, deadline: this.deletionDeadline }))
      }
      return route.fulfill(json(0, { pending: false, deleted: false }))
    }

    if (path === '/api/user/deletion/refund-request' && method === 'POST') {
      const body = route.request().postDataJSON()
      this.assetRefundRequested = true
      return route.fulfill(json(0, { code_id: body?.code_id ?? '', refund_requested: true },
        { msg: '退款申请已提交' }))
    }

    if (path === '/api/user/deletion-assets' && method === 'GET') {
      if (!this.currentUser) return route.fulfill(json(1, '未登录'))
      const blocked = this.assetsBlocking
        ? [{ code_id: 'TRIAL-AB12CD34', tier: 'trial', status: 'active', expires_at: '2026-09-05', has_order: true }]
        : []
      return route.fulfill(json(0, { blocked_assets: blocked }))
    }

    if (path === '/api/user/deletion' && method === 'POST') {
      const body = route.request().postDataJSON()
      if (!this.currentUser) return route.fulfill(json(1, '未登录'))
      if (this.assetsBlocking && !body?.waive_assets && !this.assetRefundRequested) {
        return route.fulfill(json(3, { blocked_assets: [
          { code_id: 'TRIAL-AB12CD34', tier: 'trial', status: 'active', expires_at: '2026-09-05', has_order: true },
        ] }, { msg: '存在未消耗的套餐权益，请先退款或确认放弃' }))
      }
      this.deletionPending = true
      this.deletionDaysLeft = 15
      return route.fulfill(json(0, { pending: true, days_left: 15, deadline: this.deletionDeadline },
        { msg: '注销申请已提交' }))
    }

    if (path === '/api/user/deletion/revoke' && method === 'POST') {
      if (this.accountDeleted) return route.fulfill(json(1, '该账号已注销，无法撤销'))
      this.deletionPending = false
      return route.fulfill(json(0, { success: true }))
    }

    // ── 门户 API ──
    if (path === '/api/web/login' && method === 'POST') {
      if (this.accountDeleted) {
        return route.fulfill(json(1, { deleted: true }, { msg: '该账号已注销' }))
      }
      if (this.deletionPending) {
        return route.fulfill(json(4, { deletion_pending: true, days_left: this.deletionDaysLeft, deadline: this.deletionDeadline },
          { msg: '账号注销进行中' }))
      }
      const body = route.request().postDataJSON()
      if (!this.currentUser || body.username !== this.currentUser.username) {
        return route.fulfill(json(1, '用户名或密码错误'))
      }
      return route.fulfill(json(0, {
        token: this.currentUser.token,
        tier: this.currentUser.tier,
        expires_at: this.currentUser.expires_at,
        theme: this.currentUser.theme,
      }))
    }

    if (path === '/api/web/register' && method === 'POST') {
      const body = route.request().postDataJSON()
      if (!body?.username || !body?.password) {
        return route.fulfill(json(1, '请填写完整信息'))
      }
      this.registerUser({ username: body.username, password: body.password })
      return route.fulfill(json(0, {
        token: this.currentUser!.token,
        tier: this.currentUser!.tier,
        expires_at: this.currentUser!.expires_at,
      }))
    }

    if (path === '/api/user/me' && method === 'GET') {
      if (this.userMeDead) {
        return route.fulfill(json(1, null))
      }
      if (!this.currentUser) {
        return route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ code: 2, msg: '未登录' }) })
      }
      return route.fulfill(json(0, {
        username: this.currentUser.username,
        tier: this.currentUser.tier,
        expires_at: this.currentUser.expires_at,
        is_valid: this.currentUser.is_valid,
        theme: this.currentUser.theme,
        // account-blocks-unify：密保问题文本 + 注册时间（答案从不下发）
        security_question: this.currentUser.security_question || '',
        registered_at: this.currentUser.registered_at || '',
      }))
    }

    if (path === '/api/user/preferences' && method === 'PUT') {
      if (this.preferencesFailCount > 0) {
        this.preferencesFailCount--
        if (this.preferencesFailMode === 'network') {
          return route.abort('connectionrefused')
        }
        return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ code: 500, msg: 'mock preferences fail' }) })
      }
      const body = route.request().postDataJSON()
      const known = ['teal', 'ink', 'bamboo', 'rouge', 'wisteria', 'celadon']
      if (!known.includes(body?.theme)) {
        return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ code: 422, msg: `不支持的主题：${body?.theme}` }) })
      }
      this.currentUser!.theme = body.theme
      return route.fulfill(json(0, { theme: body.theme }))
    }

    if (path === '/api/user/password' && method === 'PUT') {
      const body = route.request().postDataJSON()
      if (!body?.old_password || !body?.new_password) {
        return route.fulfill(json(1, '请填写完整信息'))
      }
      if (body.new_password.length < 6) {
        return route.fulfill(json(1, '密码至少 6 位'))
      }
      if (body.old_password === body.new_password) {
        return route.fulfill(json(1, '新密码不能与旧密码相同'))
      }
      return route.fulfill(json(0, { success: true }))
    }

    if (path === '/api/user/security' && method === 'PUT') {
      // account-blocks-unify：保存后回写会话内的问题文本（行状态联动）
      if (this.currentUser) {
        const body = route.request().postDataJSON() as { security_question?: string }
        this.currentUser.security_question = body.security_question || ''
      }
      return route.fulfill(json(0, { success: true }))
    }

    if (path === '/api/devices/my' && method === 'GET') {
      const activatedCount = this.devices.filter(d => d.activated).length
      return route.fulfill(json(0, this.devices, {
        total_count: this.devices.length,
        activated_count: activatedCount,
        active_limit: 3,
      }))
    }

    if (path === '/api/devices/remove' && method === 'POST') {
      const body = route.request().postDataJSON()
      this.devices = this.devices.filter(d => d.id !== body?.id)
      return route.fulfill(json(0, { success: true }))
    }

    // ── 支付（S端）──
    // 单源 skus 路由（s-pay-plans-picker：曾存在第二个重复块漂移为死代码，已删；此处为唯一出口）
    if (path === '/api/pay/skus' && method === 'GET') {
      if (this.skusGate?.fail) return route.abort('connectionrefused')
      if (this.skusGate?.delayMs) await new Promise((r) => setTimeout(r, this.skusGate.delayMs))
      if (this.skusOverride) return route.fulfill(json(0, this.skusOverride))
      return route.fulfill(json(0, {
        purchase_enabled: this.purchaseEnabled,
        agreement_version: 'v2026.08',
        // 三档矩阵（s-pay-plans-picker）：free 卖点空数组=前端兜底；max planned=预告卡
        tiers: [
          { key: 'free', label: '免费', is_live: true, is_planned: false, selling_points: [] },
          { key: 'pro', label: 'PRO', is_live: true, is_planned: false, selling_points: ['含免费全部功能', 'AI 生成正文（流式）', '设定与章纲融入 AI'] },
          { key: 'max', label: 'MAX', is_live: false, is_planned: true, selling_points: [] },
        ],
        skus: [
          { sku_key: 'pro_monthly', tier_key: 'pro', period: 'monthly', period_days: 30, base_price_fen: 3000, discount_display: '', price_fen: 3000, device_limit: 3 },
          { sku_key: 'pro_quarterly', tier_key: 'pro', period: 'quarterly', period_days: 90, base_price_fen: 8000, discount_display: '9折', price_fen: 7200, device_limit: 3 },
          { sku_key: 'pro_yearly', tier_key: 'pro', period: 'yearly', period_days: 365, base_price_fen: 29900, discount_display: '8折', price_fen: 23920, device_limit: 5 },
        ],
        popular_sku: 'pro_yearly',
      }))
    }

    // ── 套餐明细分页（license-grants-pagination：status 白名单 + 真分页，与真实契约同款）──
    if (path === '/api/pay/license/codes' && method === 'GET') {
      if (this.codesGate?.fail) return route.abort('connectionrefused')
      if (this.codesGate?.delayMs) await new Promise((r) => setTimeout(r, this.codesGate.delayMs))
      if (!this.licenseCodes.length && this.orders.some((o) => o.fulfillment)) this.syncLicenseFromCodes()
      const statusQ = url.searchParams.get('status')
      const allowed = ['pending_activation', 'active', 'frozen', 'revoked']
      let list = this.licenseCodes
      if (statusQ !== null) {
        const want = statusQ.split(',').map((s) => s.trim()).filter((s) => allowed.includes(s))
        list = want.length ? list.filter((g) => want.includes(g.status)) : []
      }
      const page = Math.max(1, Number(url.searchParams.get('page') ?? '1') || 1)
      const size = Math.min(100, Math.max(1, Number(url.searchParams.get('page_size') ?? '20') || 20))
      const items = list.slice((page - 1) * size, page * size)
      return route.fulfill(json(0, { items, total: list.length }))
    }

    if (path === '/api/pay/license' && method === 'GET') {
      if (!this.license && this.orders.some((o) => o.fulfillment)) this.syncLicenseFromCodes()
      return route.fulfill(json(0, this.license ?? {
        tier: this.currentUser?.tier ?? 'free',
        remaining_sec: 0,
        remaining_desc: '0 天',
        max_expires_at: null,
        pending_count: 0,
        code_count: 0,
      }))
    }

    // ── 激活（到货-激活两段式第二段；明细待激活行入口）──
    // 前端走 codes/activate（api-naming-convergence）
    if (path === '/api/pay/codes/activate' && method === 'POST') {
      const body = route.request().postDataJSON()
      if (this.activateFailMode !== 'none') {
        const m = this.activateFailMode
        this.activateFailMode = 'none'
        const msg = m === 'not_fulfilled' ? 'not_fulfilled' : 'Code is not in pending_activation state'
        return route.fulfill(json(4004, null, { msg }))
      }
      const o = this.orders.find((x) => x.order_no === body?.order_no)
      if (!o || o.fulfillment?.status === 'revoked') {
        return route.fulfill(json(4004, null, { msg: 'Code is not in pending_activation state' }))
      }
      const days = (o.snapshot?.period_days as number) ?? 30
      const expires = new Date(Date.now() + days * 86400000).toISOString().slice(0, 19)
      o.fulfillment = { status: 'active', activated_at: new Date().toISOString().slice(0, 19), expires_at: expires }
      this.syncLicenseFromCodes()
      return route.fulfill(json(0, {
        code_id: `O-${o.order_no}`,
        grant_start: new Date().toISOString().slice(0, 19),
        expires_at: expires,
        tier: (o.snapshot?.tier_key as string) ?? 'pro',
      }))
    }

    if (path === '/api/pay/orders' && method === 'GET') {
      if (this.ordersGate?.fail) return route.abort('connectionrefused')
      if (this.ordersGate?.delayMs) await new Promise((r) => setTimeout(r, this.ordersGate.delayMs))
      // orders-status-tabs：与真实契约同款——status 逗号白名单筛选 + 真分页 + total 筛选全量计数
      const statusQ = url.searchParams.get('status')
      const allowed = ['pending', 'paid', 'fulfilled', 'refund_pending', 'refund_processing', 'refunded', 'closed', 'exception']
      let list = this.orders
      if (statusQ !== null) {
        const want = statusQ.split(',').map((s) => s.trim()).filter((s) => allowed.includes(s))
        list = want.length ? list.filter((o) => want.includes(o.status)) : []
      }
      const page = Math.max(1, Number(url.searchParams.get('page') ?? '1') || 1)
      const size = Math.min(100, Math.max(1, Number(url.searchParams.get('page_size') ?? '20') || 20))
      const items = list.slice((page - 1) * size, page * size)
      return route.fulfill(json(0, { items, total: list.length }))
    }

    // ── 订单详情 / 退款操作（最小状态机）──
    if (path === '/api/pay/orders/pending' && method === 'GET') {
      const pending = this.orders.find((x) => x.status === 'pending')
      return route.fulfill(json(0, pending
        ? { order_no: pending.order_no, sku_id: 1, amount_fen: pending.amount_fen }
        : null))
    }

    const orderDetailMatch = path.match(/^\/api\/pay\/orders\/([^/]+)$/)
    if (orderDetailMatch && method === 'GET') {
      const o = this.orders.find((x) => x.order_no === orderDetailMatch[1])
      if (!o) return route.fulfill(json(4004, null, { msg: '订单不存在' }))
      return route.fulfill(json(0, {
        order_no: o.order_no,
        status: o.status,
        amount_fen: o.amount_fen,
        snapshot: o.snapshot,
        created_at: o.created_at,
        paid_at: o.paid_at,
        fulfilled_at: o.fulfilled_at ?? (o.paid_at || ''),
        refund_requested_at: o.refund_requested_at ?? (o.refund_amount_fen ? (o.refunded_at || o.paid_at) : ''),
        refunded_at: o.refunded_at,
        fulfillment: o.fulfillment !== undefined
          ? o.fulfillment
          : (o.status === 'refunded'
              ? { status: 'revoked', activated_at: '', expires_at: '' }
              : (o.paid_at ? { status: 'pending_activation', activated_at: '', expires_at: '' } : null)),
        agreement: { version: 'v2026.08', agreed_at: o.created_at },
        wx_transaction_id: o.paid_at ? `4200${o.order_no.slice(-8)}` : undefined,
        remaining_pay_seconds: o.remaining_pay_seconds ?? null,
        refund: o.refund_amount_fen
          ? { status: this.refundStatusOf(o.status), amount_fen: o.refund_amount_fen, cooldown_remaining_seconds: this.refundCooldown }
          : null,
      }))
    }

    if (/^\/api\/pay\/orders\/[^/]+\/cancel$/.test(path) && method === 'POST') {
      const o = this.orders.find((x) => path === `/api/pay/orders/${x.order_no}/cancel`)
      if (o) o.status = 'closed'
      return route.fulfill(json(0, { status: 'closed' }))
    }

    const previewMatch = path.match(/^\/api\/pay\/orders\/([^/]+)\/refund-preview$/)
    if (previewMatch && method === 'GET') {
      if (this.refundPreviewOverride) return route.fulfill(json(0, this.refundPreviewOverride))
      return route.fulfill(json(0, {
        refundable: true, reason: '',
        refund_fen: 776, remaining_desc: '9 天 16 小时 48 分',
      }))
    }

    if (/^\/api\/pay\/orders\/[^/]+\/refund$/.test(path) && method === 'POST') {
      const o = this.orders.find((x) => path.startsWith(`/api/pay/orders/${x.order_no}/refund`))
      if (o) {
        o.status = 'refund_pending'
        o.refund_amount_fen = this.refundPreviewOverride?.refund_fen ?? 776
      }
      return route.fulfill(json(0, {
        order_no: o?.order_no ?? '', amount_fen: o?.amount_fen ?? 0,
        refund_fen: o?.refund_amount_fen ?? 776,
        status: 'refund_pending', cooldown_remaining_seconds: this.refundCooldown,
      }))
    }

    const cancelRefundMatch = path.match(/^\/api\/pay\/orders\/([^/]+)\/refund\/cancel$/)
    if (cancelRefundMatch && method === 'POST') {
      const o = this.orders.find((x) => x.order_no === cancelRefundMatch[1])
      if (o) { o.status = 'fulfilled'; o.refund_amount_fen = null }
      return route.fulfill(json(0, { code_restored: true }))
    }

    if (path === '/api/pay/orders' && method === 'POST') {
      const body = route.request().postDataJSON()
      if (!body?.sku_key || !body?.agreement_version) {
        return route.fulfill(json(4003, null, { msg: '参数缺失' }))
      }
      if (this.createOrderFailCount > 0) {
        this.createOrderFailCount--
        return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ code: 500, msg: 'mock create order fail' }) })
      }
      // 登记订单（收银台成功页就地激活消费；幂等去重防连测串单）
      const orderNo = 'SE2ENEWORDER0001'
      this.orders = this.orders.filter((o) => o.order_no !== orderNo)
      this.orders.push({
        order_no: orderNo,
        status: 'fulfilled',
        amount_fen: 23920,
        snapshot: { tier_key: 'pro', tier_display: 'PRO', period: 'yearly', period_days: 365 },
        created_at: new Date().toISOString().slice(0, 19),
        paid_at: new Date().toISOString().slice(0, 19),
        refunded_at: '',
        fulfillment: { status: 'pending_activation', activated_at: '', expires_at: '' },
      })
      return route.fulfill(json(0, {
        order_no: orderNo,
        amount_fen: 23920,
        code_url: 'weixin://mock/e2e-new-order',
        status: 'pending',
        expires_at: new Date(Date.now() + 900_000).toISOString(),
        ttl_seconds: 900,
      }))
    }

    if (/^\/api\/pay\/orders\/[^/]+\/query$/.test(path) && method === 'POST') {
      return route.fulfill(json(0, { hit: this.payHint === 'SUCCESS', hint: this.payHint }))
    }

    // pay 域内未覆盖的路径 → code 1（绝不穿透 vite proxy，同兜底拦逻辑）
    if (path.startsWith('/api/pay/')) {
      return route.fulfill(json(1, 'unmocked pay api'))
    }

    // 未匹配 → 让请求正常通过
    return route.fallback()
  }
}

function json(code: number, data: any, extra: Record<string, any> = {}): any {
  return {
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ code, msg: code === 0 ? 'ok' : 'error', data, ...extra }),
  }
}
