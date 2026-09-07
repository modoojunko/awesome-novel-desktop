/**
 * 支付 API 层——附录 Z 联合契约的前端消费。
 * 错误码 = 后端数字码 + 前端映射（Z.1）。
 */
import request from './request'
import type { ApiResponse } from './request'

// ── 类型定义（附录 Z DTO）──

export interface SkuItem {
  sku_key: string
  tier_key: string
  period: 'monthly' | 'quarterly' | 'yearly'
  period_days: number
  base_price_fen: number
  discount_display: string
  price_fen: number
  device_limit: number
}

export interface TierItem {
  key: string
  label: string
  is_live: boolean
  /** status=planned 预告档（可见不可购，驱动「即将推出」卡）；s-pay-plans-picker */
  is_planned: boolean
  /** 档位卖点（tiers.selling_points 解析下发；空数组=前端兜底文案） */
  selling_points: string[]
}

export interface SkusView {
  purchase_enabled: boolean
  agreement_version: string
  tiers: TierItem[]
  skus: SkuItem[]
  popular_sku: string
  current?: {
    tier: string
    expires_at: string
    remaining_days: number
    pending_activation_count: number
  }
}

export interface CreateOrderResult {
  order_no: string
  amount_fen: number
  code_url: string
  status: string
  expires_at: string
  ttl_seconds: number
}

export interface OrderDetail {
  order_no: string
  status: string
  amount_fen: number
  created_at: string
  paid_at: string
  fulfilled_at?: string
  refund_requested_at?: string
  refunded_at?: string
  fulfillment?: Fulfillment | null
  agreement?: { version: string; agreed_at: string }
  wx_transaction_id?: string
  remaining_pay_seconds?: number | null
  refund?: {
    status: string
    amount_fen?: number
    cooldown_remaining_seconds?: number | null
    wx_refund_id?: string
  } | null
  snapshot?: Record<string, unknown>
}

export interface RefundPreview {
  refundable: boolean
  reason: string
  refund_fen?: number
  remaining_desc?: string
}

export interface RefundResult {
  order_no: string
  amount_fen: number
  refund_fen: number
  status: string
  cooldown_remaining_seconds: number
}

/** 订单到货快照（本单到货产出的码行激活状态投影；pending 态=null） */
export interface Fulfillment {
  status: string // pending_activation | active | revoked
  activated_at: string
  expires_at: string
  /** 起算时刻（未来=排队码：已激活但顺延未计时；剩余展示与退款折算以它为界） */
  grant_start?: string
}

/** 我的套餐明细行（订单来源码行；手工码不进明细） */
export interface LicenseCode {
  code_id: string
  order_no: string
  tier: string
  duration_days: number
  status: string // pending_activation | active | frozen | revoked
  activated_at: string
  expires_at: string
  grant_start: string
}

export interface LicenseView {
  tier: string
  remaining_sec: number
  remaining_desc: string
  max_expires_at: string | null
  pending_count: number
  /** 订单来源码行总数（与明细接口「全部」total 同过滤器 source='order'） */
  code_count: number
}

export interface LicenseCodePage {
  items: LicenseCode[]
  total: number
}

// ── 套餐明细四版 tab（license-grants-pagination：模式同订单五版，归组映射单源）──

export const LICENSE_TABS = [
  { key: 'all', label: '全部', statuses: null },
  // frozen 归入生效中版：退款处理中被暂停的行留在原 tab（带已冻结徽标），
  // 取消退款自动恢复原状——用户不必换 tab 找"我的套餐去哪了"
  { key: 'active', label: '生效中', statuses: ['active', 'frozen'] },
  { key: 'pending', label: '待激活', statuses: ['pending_activation'] },
  { key: 'revoked', label: '已收回', statuses: ['revoked'] },
] as const

export type LicenseTabKey = (typeof LICENSE_TABS)[number]['key']

/** 默认版=生效中（进页即聚焦正在消耗的套餐；三轮评审拍板） */
export const DEFAULT_LICENSE_TAB: LicenseTabKey = 'active'

/** ?tab= 参数 → 合法组名（非法/缺省回落默认版） */
export function licenseTabFromQuery(v: unknown): LicenseTabKey {
  return LICENSE_TABS.some((t) => t.key === v) ? (v as LicenseTabKey) : DEFAULT_LICENSE_TAB
}

export interface ActivateResult {
  code_id: string
  grant_start: string
  expires_at: string
  tier: string
}

export interface OrderListItem {
  order_no: string
  status: string
  amount_fen: number
  snapshot: Record<string, unknown>
  created_at: string
  paid_at: string
  refunded_at: string
  refund_amount_fen?: number | null
  remaining_pay_seconds?: number | null
}

export interface OrderListResult {
  items: OrderListItem[]
  total: number
}

// ── 订单列表五版 tab（orders-status-tabs：归组映射单源，接口只收原始状态白名单）──

export const ORDER_TABS = [
  { key: 'all', label: '全部', statuses: null },
  { key: 'pending', label: '待支付', statuses: ['pending'] },
  { key: 'done', label: '已完成', statuses: ['paid', 'fulfilled'] },
  { key: 'refund', label: '退款', statuses: ['refund_pending', 'refund_processing', 'refunded'] },
  { key: 'closed', label: '已过期', statuses: ['closed'] },
] as const

export type OrderTabKey = (typeof ORDER_TABS)[number]['key']

/** 默认版=待支付（用户裁定 09-02：进页即聚焦未支付订单） */
export const DEFAULT_ORDER_TAB: OrderTabKey = 'pending'

/** ?tab= 参数 → 合法组名（非法/缺省回落默认版） */
export function orderTabFromQuery(v: unknown): OrderTabKey {
  return ORDER_TABS.some((t) => t.key === v) ? (v as OrderTabKey) : DEFAULT_ORDER_TAB
}

// ── API 调用 ──

export async function apiPaySkus(): Promise<SkusView> {
  const r = await request.get<ApiResponse<SkusView>>('/pay/skus')
  return r.data.data!
}

export async function apiPayCreateOrder(skuKey: string, agreementVersion: string): Promise<CreateOrderResult> {
  const r = await request.post<ApiResponse<CreateOrderResult>>('/pay/orders', {
    sku_key: skuKey,
    agreement_version: agreementVersion,
  })
  return r.data.data!
}

export async function apiPayPendingOrder(): Promise<{ order_no: string; amount_fen: number } | null> {
  const r = await request.get<ApiResponse<{ order_no: string; amount_fen: number } | null>>('/pay/orders/pending')
  return r.data.data ?? null
}

export async function apiPayOrders(page = 1, pageSize = 50, statuses?: readonly string[] | null): Promise<OrderListResult> {
  const params: Record<string, unknown> = { page, page_size: pageSize }
  if (statuses?.length) params.status = statuses.join(',')
  const r = await request.get<ApiResponse<OrderListResult>>('/pay/orders', { params })
  return r.data.data!
}

export async function apiPayLicenseCodes(page = 1, pageSize = 20, statuses?: readonly string[] | null): Promise<LicenseCodePage> {
  const params: Record<string, unknown> = { page, page_size: pageSize }
  if (statuses?.length) params.status = statuses.join(',')
  const r = await request.get<ApiResponse<LicenseCodePage>>('/pay/license/codes', { params })
  return r.data.data!
}

export async function apiPayOrderDetail(orderNo: string): Promise<OrderDetail> {
  const r = await request.get<ApiResponse<OrderDetail>>(`/pay/orders/${orderNo}`)
  return r.data.data!
}

export async function apiPayQueryOrder(orderNo: string): Promise<{ hit: boolean; hint: string }> {
  const r = await request.post<ApiResponse<{ hit: boolean; hint: string }>>(`/pay/orders/${orderNo}/query`)
  return r.data.data!
}

export async function apiPayCancelOrder(orderNo: string): Promise<void> {
  await request.post(`/pay/orders/${orderNo}/cancel`)
}

export async function apiPayRefundPreview(orderNo: string): Promise<RefundPreview> {
  const r = await request.get<ApiResponse<RefundPreview>>(`/pay/orders/${orderNo}/refund-preview`)
  return r.data.data!
}

export async function apiPayRequestRefund(orderNo: string, reason: string): Promise<RefundResult> {
  const r = await request.post<ApiResponse<RefundResult>>(`/pay/orders/${orderNo}/refund`, { reason })
  return r.data.data!
}

export async function apiPayCancelRefund(orderNo: string): Promise<{ code_restored: boolean }> {
  const r = await request.post<ApiResponse<{ code_restored: boolean }>>(`/pay/orders/${orderNo}/refund/cancel`)
  return r.data.data!
}

export async function apiPayLicense(): Promise<LicenseView> {
  const r = await request.get<ApiResponse<LicenseView>>('/pay/license')
  return r.data.data!
}

export async function apiPayActivate(orderNo: string): Promise<ActivateResult> {
  const r = await request.post<ApiResponse<ActivateResult>>('/pay/codes/activate', { order_no: orderNo })
  return r.data.data!
}

// ── 工具函数 ──

export function fenToYuan(fen: number): string {
  return `¥${(fen / 100).toFixed(2)}`
}

export function fenToYuanShort(fen: number): string {
  return `¥${Math.round(fen / 100)}`
}

/**
 * 收银台价格展示单源（s-pay-plans-picker）：分→元后去尾零——整元不带小数（¥30），
 * 非整元保留分（¥310.2）。卡面/购买条/协议弹窗一律走它，勿再各写一套格式化。
 */
export function fmtPrice(fen: number): string {
  return `¥${(fen / 100).toFixed(2).replace(/\.?0+$/, '')}`
}

/** 订单状态 → UI 徽标类名（附录 Z 状态映射） */
export function statusPillClass(status: string): string {
  switch (status) {
    case 'pending': return 'pill-status pill-warn'
    case 'paid': case 'fulfilled': return 'pill-status pill-ok'
    case 'refund_pending': return 'pill-status pill-warn'
    case 'refund_processing': return 'pill-status pill-warn'
    case 'refunded': return 'pill-tag'
    case 'closed': return 'pill-tag'
    case 'exception': return 'pill-status pill-err'
    default: return 'pill-tag'
  }
}

/** 订单状态 → 中文标签 */
export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '等待支付',
    paid: '已支付',
    fulfilled: '已支付',
    refund_pending: '退款中·冷静期',
    refund_processing: '退款中',
    refunded: '已退款',
    closed: '已过期',
    exception: '核对中',
  }
  return map[status] || status
}

/** 后端时间字符串 → 北京时间展示（sqlite 存 naive UTC，补 Z 再转；已是 iso 带时区则原样） */
export function fmtBj(iso: string, withTime = true): string {
  if (!iso) return '—'
  let s = iso
  if (!/[Zz]|[+-]\d{2}:?\d{2}$/.test(s)) s += 'Z'
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return '—'
  const opts: Intl.DateTimeFormatOptions = {
    timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit',
    ...(withTime ? { hour: '2-digit', minute: '2-digit', hour12: false } : {}),
  }
  const parts = new Intl.DateTimeFormat('zh-CN', opts).formatToParts(d)
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  const date = `${get('year')}-${get('month')}-${get('day')}`
  return withTime ? `${date} ${get('hour')}:${get('minute')}` : date
}

/** 微信单号脱敏：4200****7721 */
export function maskWxNo(no: string): string {
  if (!no) return ''
  if (no.length <= 8) return no
  return `${no.slice(0, 4)}****${no.slice(-4)}`
}

const PERIOD_LABEL: Record<string, string> = { monthly: '包月', quarterly: '包季', yearly: '包年' }

export function periodLabel(period: string): string {
  return PERIOD_LABEL[period] || period
}

/** 快照 → 订单标题（PRO · 包季） */
export function orderTitle(snapshot: Record<string, unknown> | undefined | null): string {
  if (!snapshot) return '套餐订单'
  const tier = (snapshot.tier_display as string) || 'PRO'
  const period = periodLabel((snapshot.period as string) || '')
  return period ? `${tier} · ${period}` : tier
}

/** 快照 → 时长标签（90 天） */
export function periodDaysLabel(snapshot: Record<string, unknown> | undefined | null): string {
  const days = snapshot?.period_days as number | undefined
  return days ? `${days} 天` : ''
}

/** 秒数 → mm:ss */
export function mmss(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${String(m).padStart(2, '0')}:${String(r).padStart(2, '0')}`
}
