<script setup lang="ts">
/**
 * 收银台——购买流程页（无控制台外壳）。
 * 选套餐（时长主轴×三档对比）、协议弹窗、扫码支付、八态分支。
 * 设计事实源：docs/design-s/prototypes/cashier.html 态一（09-03 改版，s-pay-plans-picker）：
 * 界面以鼠标点按为主，不做键盘适配（用户裁定）；价格展示一律走 fmtPrice 单源。
 */
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  apiPaySkus, apiPayCreateOrder, apiPayQueryOrder, apiPayCancelOrder, apiPayActivate, apiPayLicense,
  fmtPrice, fmtBj, periodLabel,
  type SkusView, type SkuItem, type CreateOrderResult, type ActivateResult, type LicenseView,
} from '@/api/pay'
import { useSessionStore } from '@/stores/session'
import { brand } from '@/constants/brand'
import Ico from '@/components/ui/Ico.vue'
import AppModal from '@/components/ui/AppModal.vue'
import SiteBeianBar from '@/components/site/SiteBeianBar.vue'
import { P } from '@/components/ui/icons'

const router = useRouter()
const route = useRoute()
const session = useSessionStore()

// ── 状态 ──
const loading = ref(true)
const skusData = ref<SkusView | null>(null)
// 二维选套餐状态（s-pay-plans-picker D1）：时长主轴默认包月（用户裁定）+ 档位列选中
const period = ref<SkuItem['period']>('monthly')
const selectedTier = ref('')
const order = ref<CreateOrderResult | null>(null)
const payState = ref<'pick' | 'waiting' | 'success' | 'closed' | 'failCreate' | 'failVerify' | 'waitFail'>('pick')
const showTerms = ref(false)
const termsRead = ref(false)
const countdownSec = ref(0)
const queryHint = ref('')
let pollTimer: ReturnType<typeof setInterval> | null = null
let countdownTimer: ReturnType<typeof setInterval> | null = null

// ── 到货页就地激活（立即激活=真激活，不再只是跳转；囤单路径=「先存着」）──
const activating = ref(false)
const activated = ref(false)
const activateErr = ref('')
const activateResult = ref<ActivateResult | null>(null)

async function doActivate() {
  if (!order.value || activating.value || activated.value) return
  activating.value = true
  activateErr.value = ''
  try {
    activateResult.value = await apiPayActivate(order.value.order_no)
    activated.value = true
  } catch (e: any) {
    activateErr.value = e?.message || '网络异常，请重试'
  } finally {
    activating.value = false
  }
}

// ── 卖点兜底文案（selling_points 空数组时的保底，不空白）──
// 免费/PRO=UpgradeModal 真实功能事实（client/…/UpgradeModal.tsx）；MAX=占位稿待运营定稿
const FALLBACK_FEATS: Record<string, string[]> = {
  free: ['全部基础写作工具', '不含 AI 能力', '本地作品永久保留'],
  pro: ['含免费全部功能', 'AI 生成正文（流式）', '设定与章纲融入 AI', '卷/章高级字段（冲突阶梯·情绪设计）'],
  max: ['含 PRO 全部功能', '更强模型 · 更大用量', '多章连写与批量生成', '优先体验新能力', '最多 10 台设备'],
}
// 目录不可达时的降级骨架：时长/设备数是产品结构事实，价格一律留白
const FALLBACK_PAID = [
  { period: 'monthly', days: 30, devices: 3 },
  { period: 'quarterly', days: 90, devices: 3 },
  { period: 'yearly', days: 365, devices: 5 },
] as const

const PERIOD_ORDER: SkuItem['period'][] = ['monthly', 'quarterly', 'yearly']

// ── 计算属性 ──
const isLoggedIn = computed(() => session.isLoggedIn)

// ── 生效期换档引导（add-refund-rebuy-guide）：已购付费档用户提示"先退再买"路径 ──
const license = ref<LicenseView | null>(null)
const hasActivePaidPlan = computed(() =>
  !!license.value && !['free', 'none'].includes(license.value.tier) && license.value.remaining_sec > 0)

/** 目录里实际在售的时长集合（驱动 tab；目录不可达时为空=不渲染 tab） */
const periods = computed<SkuItem['period'][]>(() => {
  const set = new Set((skusData.value?.skus ?? []).map(s => s.period))
  return PERIOD_ORDER.filter(p => set.has(p))
})

/** 时长 tab 折扣徽标：读该时长下任一 SKU 的 discount_display（单源，前端不换算） */
function periodDiscount(p: SkuItem['period']): string {
  const sku = skusData.value?.skus.find(s => s.period === p && s.discount_display)
  return sku?.discount_display ?? ''
}

/** 三档对比列（free 行除外；planned 档渲染预告卡） */
const tierCards = computed(() => {
  const tiers = (skusData.value?.tiers ?? []).filter(t => t.key !== 'free')
  return tiers.map(t => ({
    ...t,
    feats: t.selling_points.length ? t.selling_points : FALLBACK_FEATS[t.key] ?? [],
    sku: skusData.value?.skus.find(s => s.tier_key === t.key && s.period === period.value) ?? null,
  }))
})

const freeTier = computed(() => skusData.value?.tiers.find(t => t.key === 'free') ?? null)
const freeFeats = computed(() =>
  freeTier.value?.selling_points.length ? freeTier.value.selling_points : FALLBACK_FEATS.free)

/** 选中规格：档×时长 交集（档被下架/该时长无 SKU 时为 null，由守卫回落） */
const selectedSku = computed<SkuItem | null>(() =>
  skusData.value?.skus.find(s => s.tier_key === selectedTier.value && s.period === period.value) ?? null)

const selectedPrice = computed(() => selectedSku.value ? fmtPrice(selectedSku.value.price_fen) : '')

const savedFen = computed(() => {
  const s = selectedSku.value
  return s ? Math.max(0, s.base_price_fen - s.price_fen) : 0
})

function tierLabelOf(key: string): string {
  if (key === 'free') return '免费'
  return skusData.value?.tiers.find(t => t.key === key)?.label ?? key
}

/** 守卫：所选档失效（下架/该时长无 SKU）时回落——popular 档 → 该时长有货的首个 live 档 */
function ensureSelection() {
  if (selectedSku.value || !skusData.value) return
  const data = skusData.value
  const popular = data.skus.find(s => s.sku_key === data.popular_sku)
  const fallback =
    (popular && popular.tier_key) ||
    data.skus.find(s => s.period === period.value)?.tier_key ||
    data.skus[0]?.tier_key ||
    ''
  if (fallback) selectedTier.value = fallback
}

// 协议确认在「去支付」后的弹窗里打钩留痕（产品拍板），选卡本身不设门槛
const canPay = computed(() => !!selectedSku.value)

function switchPeriod(p: SkuItem['period']) {
  period.value = p
  ensureSelection()
}

// ── 方法 ──
async function loadSkus() {
  try {
    skusData.value = await apiPaySkus()
    // 默认：时长=包月（用户裁定）；档位=popular 所属档回退 pro/首个 live 档。
    // URL 预选（s-pay-landing-plans：落地页带参跳转消费端）：period/tier 先对目录校验，
    // 合法才采用，否则走默认链；不监听路由变化，无参行为与原先完全一致
    const data = skusData.value
    const qp = typeof route.query.period === 'string' ? route.query.period : ''
    const qt = typeof route.query.tier === 'string' ? route.query.tier : ''
    if (periods.value.includes(qp as SkuItem['period'])) {
      period.value = qp as SkuItem['period']
    } else if (periods.value.length && !periods.value.includes(period.value)) {
      period.value = periods.value[0]
    }
    const queryTierValid = !!qt && data.skus.some(s => s.tier_key === qt && s.period === period.value)
    if (queryTierValid) {
      selectedTier.value = qt
    } else {
      const popular = data.skus.find(s => s.sku_key === data.popular_sku)
      selectedTier.value = popular?.tier_key || data.tiers.find(t => t.is_live && t.key !== 'free')?.key || 'pro'
    }
    ensureSelection()
  } catch (e) {
    console.error('loadSkus failed:', e)
  } finally {
    loading.value = false
  }
}

async function goPay() {
  if (!selectedSku.value || !skusData.value) return
  showTerms.value = true
  termsRead.value = false
}

async function confirmPay() {
  showTerms.value = false
  if (!selectedSku.value || !skusData.value) return
  try {
    order.value = await apiPayCreateOrder(
      selectedSku.value.sku_key,
      skusData.value.agreement_version,
    )
    payState.value = 'waiting'
    startPolling()
    startCountdown(order.value.ttl_seconds)
    } catch (e: any) {
      if (e?.code === 4012) {
        // 开关未开放
        payState.value = 'pick'
        return
      }
      payState.value = 'failCreate'
    }
}

function startPolling() {
  stopPolling()
  let count = 0
  pollTimer = setInterval(async () => {
    if (!order.value) return
    count++
    // 3s 起步，20 轮后 5s，80 轮后 10s
    const interval = count <= 20 ? 3000 : count <= 80 ? 5000 : 10000
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = setInterval(() => pollTick(), interval)
    // 立即执行一次
    await pollTick()
  }, 3000)
}

async function pollTick() {
  if (!order.value) return
  try {
    const r = await apiPayQueryOrder(order.value.order_no)
    if (r.hint === 'SUCCESS') {
      stopPolling()
      stopCountdown()
      payState.value = 'success'
    } else if (r.hint === 'CLOSED') {
      stopPolling()
      stopCountdown()
      payState.value = 'closed'
    } else if (r.hint === 'PAYERROR') {
      queryHint.value = 'payerror'
    } else if (r.hint === 'NOTPAY') {
      queryHint.value = 'notpay'
    }
  } catch {
    // 网络错误静默重试
  }
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

function startCountdown(seconds: number) {
  stopCountdown()
  countdownSec.value = seconds
  countdownTimer = setInterval(() => {
    countdownSec.value--
    if (countdownSec.value <= 0) {
      stopCountdown()
      payState.value = 'closed'
    }
  }, 1000)
}

function stopCountdown() {
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
}

async function cancelOrder() {
  if (!order.value) return
  try {
    await apiPayCancelOrder(order.value.order_no)
  } catch { /* 静默 */ }
  stopPolling()
  stopCountdown()
  payState.value = 'pick'
  order.value = null
}

async function manualQuery() {
  if (!order.value) return
  try {
    const r = await apiPayQueryOrder(order.value.order_no)
    if (r.hint === 'SUCCESS') {
      stopPolling(); stopCountdown()
      payState.value = 'success'
    } else if (r.hint === 'PAYERROR') {
      payState.value = 'waitFail'
      queryHint.value = 'payerror'
    } else if (r.hint === 'NOTPAY') {
      queryHint.value = 'notpay'
    }
  } catch { /* 静默 */ }
}

function formatCountdown(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// ── 二维码本地渲染（安全红线）──
// code_url 即支付凭证，官方指引明示「调用第三方库生成二维码」——本地 canvas
// 绘制，禁止外发给第三方二维码服务（可被记录/篡改换码）
import QRCode from 'qrcode'

const qrCanvas = ref<HTMLCanvasElement | null>(null)

async function renderQr(): Promise<void> {
  // 先等 DOM：watcher 默认 pre-flush（渲染前触发），此时 waiting 分支的 canvas 尚未挂载，
  // 守卫必须放在 nextTick 之后（否则 qrCanvas 恒为 null，二维码永远画不出来）
  await nextTick()
  const url = order.value?.code_url
  if (!url || !qrCanvas.value) return
  try {
    await QRCode.toCanvas(qrCanvas.value, url, { width: 180, margin: 1 })
  } catch { /* 渲染失败保留占位提示 */ }
}

watch(() => [payState.value, order.value?.code_url], () => { void renderQr() }, { flush: 'post' })

// ── 生命周期 ──
/** license 拉取静默降级：失败/未登录不弹错、不打断选购主流程（spec：接口失败 MUST NOT 显示） */
async function loadLicense() {
  if (!session.isLoggedIn) return
  try {
    license.value = await apiPayLicense()
  } catch (e) {
    console.error('loadLicense failed:', e)
  }
}

onMounted(() => { loadSkus(); loadLicense() })
onUnmounted(() => { stopPolling(); stopCountdown() })
</script>

<template>
  <div class="pay-page">
    <!-- 品牌 -->
    <div class="pay-brand">
      <span class="logo-mark">{{ brand.mark }}</span>
      <span class="pay-brand-name">{{ brand.name }}</span>
    </div>

    <!-- ═══ 态〇：未登录且停售开关关闭（未登录≠停售，两分支按登录态拆分） ═══ -->
    <template v-if="payState === 'pick' && skusData && !skusData.purchase_enabled && !isLoggedIn">
      <div class="pay-stage">
        <h1>登录后继续购买</h1>
        <p class="pay-sub">您选择的套餐已保留</p>
        <div class="pay-card">
          <button class="btn btn-primary btn-block" @click="router.push('/login')">
            去登录
          </button>
          <p class="pay-hint">
            还没有账号？<router-link to="/register" class="lnk">注册即送 7 天全功能试用</router-link>
          </p>
        </div>
      </div>
    </template>

    <!-- ═══ 态一·停售：已登录但购买开关关闭 ═══ -->
    <template v-else-if="payState === 'pick' && skusData && !skusData.purchase_enabled && isLoggedIn">
      <div class="pay-stage">
        <h1>暂时无法购买</h1>
        <div class="pay-card">
          <div class="notice warn pay-notice">
            <span>购买服务暂未开放，已登录账号不受影响。开放后此处即可选购套餐。</span>
          </div>
          <button class="btn btn-secondary btn-block" @click="router.push('/dashboard')">返回控制台</button>
        </div>
      </div>
    </template>

    <!-- ═══ 态一：选套餐（时长主轴×三档对比） ═══ -->
    <template v-else-if="payState === 'pick'">
      <h1 class="pay-h1">升级套餐，解锁全部写作能力</h1>
      <p class="pay-sub">一次性买断 · 到期不自动扣款 · 随时按剩余时长退款</p>

      <!-- 生效期换档引导（add-refund-rebuy-guide）：已购付费档用户提示"先退再买"三步，
           明示"退款完成前下单会排队至原套餐到期后"；免费/未登录/接口失败不渲染 -->
      <div v-if="hasActivePaidPlan" class="notice info pay-notice">
        <span>
          <b>想换更高档？</b>
          可先在<router-link class="lnk" to="/dashboard/orders">我的订单</router-link>对当前套餐申请退款（按剩余时长折算、未用部分原路退回），退款成功后再选购高档套餐，立即生效。
          提醒：退款完成前下单，新套餐会排队至原套餐到期后才计时。
        </span>
      </div>

      <!-- 时长 tab 主轴（包月默认；折扣徽标读 discount_display 单源） -->
      <div v-if="periods.length > 1" class="pay-tabs">
        <button
          v-for="p in periods"
          :key="p"
          class="pay-tab"
          :class="{ on: period === p }"
          @click="switchPeriod(p)"
        >
          {{ periodLabel(p) }}<span v-if="periodDiscount(p)" class="pay-tab-mini">{{ periodDiscount(p) }}</span>
        </button>
      </div>

      <div v-if="loading" class="pay-loading">加载中…</div>

      <!-- 目录不可达或无在售 SKU（spec：失败或为空同款降级）——结构事实保留，价格一律留白，
           防 live 无货档被误渲染成「即将推出」预告卡 -->
      <div v-else-if="!skusData || !skusData.skus.length" class="pay-cards">
        <div class="pay-card-free">
          <span class="pill pill-tag">当前方案</span>
          <div class="pay-card-name">免费</div>
          <div class="pay-card-days">1 台设备</div>
          <div class="pay-card-price">¥0</div>
          <div class="pay-card-feat"><i v-for="f in FALLBACK_FEATS.free" :key="f">{{ f }}</i></div>
        </div>
        <div v-for="fb in FALLBACK_PAID" :key="fb.period" class="pay-card-free">
          <div class="pay-card-name">{{ periodLabel(fb.period) }}</div>
          <div class="pay-card-days">{{ fb.days }} 天 · {{ fb.devices }} 台设备</div>
          <div class="pay-card-price pay-price-blank">价格获取失败，请刷新重试</div>
          <div class="pay-card-feat"><i v-for="f in FALLBACK_FEATS.pro" :key="f">{{ f }}</i></div>
        </div>
      </div>

      <!-- 三档对比列 -->
      <div v-else class="pay-cards">
        <!-- 免费列：对比锚点，不可选 -->
        <div class="pay-card-free">
          <span class="pill pill-tag">当前方案</span>
          <div class="pay-card-name">免费</div>
          <div class="pay-card-days">1 台设备</div>
          <div class="pay-card-price">¥0</div>
          <div class="pay-card-feat"><i v-for="f in freeFeats" :key="f">{{ f }}</i></div>
        </div>

        <!-- 付费档列 / planned 预告卡 -->
        <template v-for="t in tierCards" :key="t.key">
          <div v-if="t.is_planned || !t.sku" class="pay-card-free pay-card-soon">
            <div class="pay-card-name">{{ t.label }}</div>
            <div class="pay-card-days">即将推出</div>
            <div class="pay-card-soon-note">更高设备上限 · 更强 AI 能力。上线后此处自动变为可选时长与价格。</div>
          </div>
          <div
            v-else
            class="pay-card"
            :class="{ on: selectedTier === t.key }"
            @click="selectedTier = t.key"
          >
            <span v-if="t.sku.discount_display && t.sku.price_fen < t.sku.base_price_fen" class="pay-card-offpill">{{ t.sku.discount_display }}</span>
            <div class="pay-card-name">{{ t.label }}</div>
            <div class="pay-card-days">{{ t.sku.period_days }} 天 · 最多 {{ t.sku.device_limit }} 台设备</div>
            <div class="pay-card-price">{{ fmtPrice(t.sku.price_fen) }}<small>元</small></div>
            <div v-if="t.sku.price_fen < t.sku.base_price_fen" class="pay-card-was">原价 {{ fmtPrice(t.sku.base_price_fen) }} 元</div>
            <div class="pay-card-feat"><i v-for="f in t.feats" :key="f">{{ f }}</i></div>
          </div>
        </template>
      </div>

      <!-- 协议 + 购买条 -->
      <div v-if="selectedSku" class="pay-purchase">
        <div class="pay-purchase-info">
          <div class="pay-purchase-label">已选</div>
          <div class="pay-purchase-name">
            {{ tierLabelOf(selectedSku.tier_key) }} · {{ periodLabel(selectedSku.period) }}（{{ selectedSku.period_days }} 天）
          </div>
        </div>
        <div class="pay-purchase-price">
          <div v-if="savedFen > 0" class="pay-purchase-save">
            已省 {{ fmtPrice(savedFen) }}
          </div>
          <div class="pay-purchase-amount">{{ selectedPrice }}</div>
        </div>
        <button class="btn btn-primary btn-lg" :disabled="!canPay" @click="goPay">
          去支付
        </button>
      </div>
      <div v-if="selectedSku" class="pay-agree-hint">
        点击去支付后，将确认<a class="lnk" href="/legal/payment-notice.html" target="_blank" rel="noopener">《付费须知》</a>与<a class="lnk" href="/legal/refund-policy.html" target="_blank" rel="noopener">《退款政策》</a>要点<template v-if="skusData?.agreement_version">（{{ skusData.agreement_version }}）</template>
      </div>
    </template>

    <!-- ═══ 态二：等待支付 ═══ -->
    <template v-else-if="payState === 'waiting' && order">
      <h1 class="pay-h1">微信扫码支付</h1>
      <p class="pay-sub">订单号 <span class="num">{{ order.order_no }}</span></p>
      <div class="pay-qr-card">
        <div class="notice info pay-notice">
          <span>请使用微信扫描二维码完成支付。<b>{{ selectedPrice }}</b> 支付成功后套餐立即到货。</span>
        </div>
        <div class="pay-qr-box">
          <canvas v-show="order.code_url" ref="qrCanvas" aria-label="微信支付二维码"></canvas>
          <div v-if="!order.code_url" class="pay-qr-placeholder">二维码生成中…</div>
        </div>
        <div class="pay-countdown">二维码有效期剩 <span class="num">{{ formatCountdown(countdownSec) }}</span></div>
        <button class="btn btn-ghost" @click="cancelOrder">取消支付</button>
      </div>
      <p class="pay-query-hint">
        <template v-if="queryHint === 'notpay'">查过了：微信侧<b>尚未收到这笔订单的付款</b>——刚付款请等几秒再点一次；未付款则继续扫码。</template>
        <template v-else>已扫码付款但页面没变化？<a class="lnk" @click.prevent="manualQuery">我已支付，帮我查一下到账</a></template>
      </p>
    </template>

    <!-- ═══ 态二·子：查单失败反馈 ═══ -->
    <template v-else-if="payState === 'waitFail' && order">
      <h1 class="pay-h1">微信扫码支付</h1>
      <div class="pay-qr-card">
        <div class="notice warn pay-notice">
          <span>查过了：微信显示<b>本次支付未成功</b>（如余额不足、银行卡限额，或您取消了支付）。<b>二维码仍然有效</b>——请重新扫码，或在手机上更换支付方式后重试。</span>
        </div>
        <button class="btn btn-primary" @click="payState = 'waiting'">返回重试</button>
      </div>
    </template>

    <!-- ═══ 态三：已到货（立即激活=就地真激活；先存着=囤，之后在我的套餐激活） ═══ -->
    <template v-else-if="payState === 'success'">
      <h1 class="pay-h1">支付成功</h1>
      <div class="pay-card pay-success-card">
        <div class="pay-success-mark"><Ico :d="P.check" :size="26" /></div>
        <div class="pay-success-title">{{ activated ? '已激活，计时中' : '已到货，待激活' }}</div>
        <div v-if="activated && activateResult" class="pay-success-hint">
          已激活：{{ fmtBj(activateResult.grant_start, false) }} 起 · {{ fmtBj(activateResult.expires_at, false) }} 到期
        </div>
        <div v-else class="pay-success-hint">点「立即激活」马上开始计时；先存着也随时可在「我的套餐」激活</div>
        <div v-if="activateErr" class="notice warn pay-notice">
          <span>激活没成功：{{ activateErr }}。订单与时长不受影响，可稍后在「我的套餐」重试。</span>
        </div>
        <div class="pay-success-actions">
          <button v-if="!activated" class="btn btn-primary" :disabled="activating" @click="doActivate">
            {{ activating ? '激活中…' : '立即激活' }}
          </button>
          <button class="btn btn-secondary" @click="router.push('/dashboard')">返回控制台</button>
        </div>
        <a v-if="!activated" class="lnk" style="margin-top:6px; font-size:12.5px" @click.prevent="router.push('/dashboard/license')">先存着，之后在「我的套餐」激活</a>
      </div>
    </template>

    <!-- ═══ 态四：已过期 ═══ -->
    <template v-else-if="payState === 'closed'">
      <h1 class="pay-h1">订单已过期</h1>
      <div class="pay-card">
        <div class="notice warn pay-notice">
          <span>本次订单未支付成功，没有产生扣款。重新下单将按<b>当前价格</b>生成新订单。</span>
        </div>
        <button class="btn btn-primary btn-block" @click="payState = 'pick'; order = null">重新下单</button>
      </div>
    </template>

    <!-- ═══ 态五：下单失败 ═══ -->
    <template v-else-if="payState === 'failCreate'">
      <h1 class="pay-h1">订单创建失败</h1>
      <div class="pay-card">
        <div class="notice err pay-notice">
          <span>网络波动或支付服务暂时不可用，本次未能生成支付二维码。<b>没有产生扣款</b>，请重试。</span>
        </div>
        <div class="pay-success-actions">
          <button class="btn btn-primary" @click="payState = 'pick'">重试</button>
        </div>
      </div>
    </template>

    <!-- ═══ 协议确认弹窗 ═══ -->
    <!-- 必须走 AppModal：base.css 对 .scrim/.mcard 是两段式 .show 进出场（默认 opacity:0），
         手写 v-if 弹窗不带 .show 会整体隐形，且 fixed 遮罩仍拦截点击 → 页面假死 -->
    <AppModal v-model:open="showTerms" title="确认购买">
      <ul class="pay-terms">
        <li>一次性买断时长，<b>到期不自动扣款</b></li>
        <li>套餐支付成功即到货，<b>点激活才开始计时</b>；未激活可全额退</li>
        <li>退款<b>按剩余时长计算、原路退回</b>，不影响其他套餐</li>
        <li>本单：<b>{{ selectedSku ? `${tierLabelOf(selectedSku.tier_key)} · ${periodLabel(selectedSku.period)}（${selectedSku.period_days} 天）· ${selectedPrice}` : '' }}</b></li>
      </ul>
      <p class="pay-terms-full">
        全文：<a class="lnk" href="/legal/payment-notice.html" target="_blank" rel="noopener">《付费须知》</a><template v-if="skusData?.agreement_version">（{{ skusData.agreement_version }}）</template>
        ·
        <a class="lnk" href="/legal/refund-policy.html" target="_blank" rel="noopener">《退款政策》</a><template v-if="skusData?.agreement_version">（{{ skusData.agreement_version }}）</template>
      </p>
      <label class="pay-agree">
        <input v-model="termsRead" type="checkbox" />
        <span>我已阅读并同意<a class="lnk" href="/legal/payment-notice.html" target="_blank" rel="noopener" @click.stop>《付费须知》</a>与<a class="lnk" href="/legal/refund-policy.html" target="_blank" rel="noopener" @click.stop>《退款政策》</a>：按剩余时长折算退款、原路退回</span>
      </label>
      <template #footer>
        <button class="btn btn-secondary" @click="showTerms = false">再想想</button>
        <button class="btn btn-primary" :disabled="!termsRead" @click="confirmPay">阅读并同意，去支付</button>
      </template>
    </AppModal>

    <!-- 全站备案条：购买页独立布局的法律文件兜底入口（弹窗之外也能到达四份全文） -->
    <SiteBeianBar class="pay-beian" />
  </div>
</template>

<style scoped>
/* 布局类（令牌走 base.css var）——对应原型 cashier.html 选型 A */
.pay-page { min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 48px 24px 0; background: var(--bg); }
.pay-beian { margin-top: auto; width: 100%; }
.pay-brand { display: flex; align-items: center; gap: 9px; font-family: var(--font-display); font-size: 17px; font-weight: 600; }
.logo-mark { width: 28px; height: 28px; border-radius: 8px; background: var(--accent); color: var(--on-accent); display: grid; place-items: center; font-family: var(--font-display); font-size: 15px; }
.pay-brand-name { color: var(--fg); }
.pay-h1 { font-size: 24px; font-weight: 700; letter-spacing: 0.01em; margin: 30px 0 6px; text-align: center; color: var(--fg); }
.pay-sub { font-size: 13px; color: var(--muted); margin: 0 0 26px; text-align: center; }
.pay-stage { width: 100%; max-width: 460px; margin-top: 20px; }
.pay-loading { padding: 60px; text-align: center; color: var(--muted); }

.pay-tabs { display: inline-flex; background: var(--fg-soft); border-radius: 12px; padding: 4px; gap: 4px; margin-bottom: 10px; }
.pay-tab { height: 42px; padding: 0 26px; border-radius: 9px; font-size: 14.5px; font-weight: 600; color: var(--muted); border: 0; background: none; cursor: pointer; }
.pay-tab.on { background: var(--surface); color: var(--fg); box-shadow: 0 1px 3px color-mix(in oklch, var(--fg) 10%, transparent); }
.pay-tab-mini { font-size: 10.5px; font-weight: 600; color: var(--accent-strong); background: var(--accent-soft); padding: 1px 7px; border-radius: 999px; margin-left: 7px; vertical-align: 1px; }

/* 三档对比列（时长主轴在 tab，列=档位；对齐原型 cashier.html 态一） */
.pay-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; width: 860px; max-width: 100%; margin-top: 26px; }
.pay-card-free, .pay-card { position: relative; background: var(--surface); border: 1.5px solid var(--border); border-radius: 14px; padding: 20px 20px 18px; text-align: left; }
.pay-card { cursor: pointer; transition: border-color 0.15s ease, background 0.15s ease; }
.pay-card:hover { border-color: color-mix(in oklch, var(--accent) 40%, var(--border)); }
.pay-card.on { border-color: var(--accent); background: color-mix(in oklch, var(--accent) 4%, var(--surface)); box-shadow: 0 0 0 3px var(--accent-soft); }
.pay-card-free { cursor: default; }
.pay-card-free:hover { border-color: var(--border); }
/* planned 预告卡：dashed，不可选 */
.pay-card-soon { border-style: dashed; background: transparent; }
.pay-card-soon-note { font-size: 12px; color: var(--muted); margin-top: 10px; line-height: 1.6; }
.pay-card-name { font-size: 15px; font-weight: 600; color: var(--fg); }
.pay-card-days { font-size: 12px; color: var(--muted); margin-top: 2px; }
.pay-card-price { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: 32px; font-weight: 600; letter-spacing: -0.02em; margin-top: 12px; color: var(--fg); }
.pay-card-price small { font-size: 13px; font-weight: 400; color: var(--muted); margin-left: 2px; }
.pay-price-blank { font-family: var(--font-body); font-size: 13px; font-weight: 400; color: var(--muted); }
.pay-card-offpill { position: absolute; top: 10px; right: 12px; font-size: 11px; font-weight: 600; color: var(--accent-strong); background: var(--accent-soft); padding: 2px 8px; border-radius: 999px; }
.pay-card-was { font-size: 12px; color: var(--muted); text-decoration: line-through; margin-top: 1px; }
.pay-card-feat { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); display: grid; gap: 4px; }
.pay-card-feat i { font-style: normal; font-size: 11.5px; color: var(--muted); display: flex; gap: 6px; align-items: baseline; }
.pay-card-feat i::before { content: ''; flex: none; width: 4px; height: 4px; border-radius: 50%; background: var(--accent); }

.pay-purchase { width: 860px; max-width: 100%; margin-top: 18px; background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 20px; display: flex; align-items: center; gap: 18px; }
.pay-purchase-info { flex: 1; }
.pay-purchase-label { font-size: 13px; color: var(--muted); }
.pay-purchase-name { font-size: 15px; font-weight: 600; }
.pay-purchase-price { text-align: right; }
.pay-purchase-save { font-size: 12px; color: var(--warn); font-weight: 500; }
.pay-purchase-amount { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: 26px; font-weight: 600; }
.pay-agree-hint { width: 860px; max-width: 100%; margin-top: 12px; font-size: 12px; color: var(--muted); text-align: center; }

.pay-qr-card { width: 460px; max-width: 100%; }
.pay-notice { margin-bottom: 14px; }
.pay-qr-box { width: 188px; height: 188px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); display: grid; place-items: center; overflow: hidden; margin: 0 auto; }
.pay-qr-box img { width: 100%; height: 100%; object-fit: contain; }
.pay-qr-placeholder { font-size: 13px; color: var(--muted); }
.pay-countdown { font-size: 13px; color: var(--muted); text-align: center; margin-top: 14px; }
.pay-countdown .num { font-size: 17px; font-weight: 600; color: var(--fg); }
.pay-query-hint { text-align: center; font-size: 13px; color: var(--muted); margin-top: 14px; }

.pay-success-card { display: grid; justify-items: center; gap: 6px; padding: 28px 22px; text-align: center; }
.pay-success-mark { width: 54px; height: 54px; border-radius: 50%; background: var(--ok-soft); display: grid; place-items: center; color: var(--ok); font-size: 24px; }
.pay-success-title { font-family: var(--font-display); font-size: 21px; font-weight: 600; }
.pay-success-hint { font-size: 13px; color: var(--muted); }
.pay-success-actions { display: flex; gap: 10px; margin-top: 10px; }

.pay-terms { margin: 8px 0; padding-left: 18px; display: grid; gap: 5px; font-size: 12.5px; color: var(--muted); list-style: none; }
.pay-terms li::before { content: ''; display: inline-block; width: 4px; height: 4px; border-radius: 50%; background: var(--accent); margin-right: 6px; vertical-align: middle; }
.pay-terms b { color: var(--fg); }
.pay-terms-full { margin: 10px 0 0; font-size: 12px; color: var(--muted); }
.pay-agree { display: flex; gap: 8px; align-items: flex-start; margin: 12px 0 0; font-size: 12.5px; color: var(--fg); cursor: pointer; }
.pay-agree input { margin-top: 3px; accent-color: var(--accent); width: 14px; height: 14px; flex: none; }

/* 响应式：三档对比列 768px 以下单列纵排（对比列变对比行），购买条堆叠 */
@media (max-width: 768px) {
  .pay-cards { grid-template-columns: 1fr; }
  .pay-purchase { flex-direction: column; align-items: stretch; text-align: center; }
  .pay-purchase-info, .pay-purchase-price { text-align: center; }
}
</style>
