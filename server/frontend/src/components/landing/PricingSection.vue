<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppButton from '@/components/ui/AppButton.vue'
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'
import {
  apiPaySkus, fmtPrice, periodLabel,
  type SkusView, type SkuItem,
} from '@/api/pay'

/**
 * 营销页套餐区 = 收银台同 IA（s-pay-landing-plans）：时长 tab 主轴×免费/PRO/MAX 三档对比列。
 * 数据同源 GET /pay/skus，价格走 fmtPrice 单源。与收银台的有意差异：
 * 匿名语境免费列=注册导流（非「当前方案」）、「最受欢迎」徽标保留（收银台按 s-pay-plans-picker 裁定等人数统计）、
 * 购买入口带参跳 /pay（无购买条与协议弹窗——那些属收银台登录流程）。
 */
const PERIOD_ORDER: SkuItem['period'][] = ['monthly', 'quarterly', 'yearly']

// 卖点兜底（目录 tiers.selling_points 空数组时的保底，与收银台 CashierPage 同文案）
const FALLBACK_FEATS: Record<string, string[]> = {
  free: ['全部基础写作工具', '不含 AI 能力', '本地作品永久保留'],
  pro: ['含免费全部功能', 'AI 生成正文（流式）', 'AI 分卷规划与章纲起草', '设定与章纲融入 AI'],
  max: ['含 PRO 全部功能', '更强模型 · 更大用量', '多章连写与批量生成', '优先体验新能力', '最多 10 台设备'],
}

// 目录不可达时的降级骨架：时长/设备数是产品结构事实（与收银台 FALLBACK_PAID 对齐），价格一律留白
const FALLBACK_PAID = [
  { period: 'monthly', days: 30, devices: 3 },
  { period: 'quarterly', days: 90, devices: 3 },
  { period: 'yearly', days: 365, devices: 5 },
] as const

const skusData = ref<SkusView | null>(null)
const period = ref<SkuItem['period']>('monthly')

onMounted(async () => {
  try {
    skusData.value = await apiPaySkus()
  } catch {
    // 保持 null → 降级骨架
  }
})

/** 目录里实际在售的时长集合（驱动 tab；目录不可达时为空=不渲染 tab） */
const periods = computed<SkuItem['period'][]>(() => {
  const set = new Set((skusData.value?.skus ?? []).map(s => s.period))
  return PERIOD_ORDER.filter(p => set.has(p))
})

/** 时长 tab 折扣徽标：读该时长下任一 SKU 的 discount_display（单源，前端不换算） */
function periodDiscount(p: SkuItem['period']): string {
  return skusData.value?.skus.find(s => s.period === p && s.discount_display)?.discount_display ?? ''
}

const storeOpen = computed(() => skusData.value?.purchase_enabled ?? false)
const hasCatalog = computed(() => !!skusData.value && skusData.value.skus.length > 0)

const freeFeats = computed(() => {
  const t = skusData.value?.tiers.find(t => t.key === 'free')
  return t?.selling_points.length ? t.selling_points : FALLBACK_FEATS.free
})

/** 三档对比列（免费列在模板固定；planned/无可购 SKU 渲染预告卡） */
const paidColumns = computed(() => {
  const tiers = skusData.value?.tiers.filter(t => t.key !== 'free') ?? []
  return tiers.map((t) => {
    const sku = skusData.value?.skus.find(s => s.tier_key === t.key && s.period === period.value) ?? null
    const off = storeOpen.value && !!sku && !!sku.discount_display && sku.price_fen < sku.base_price_fen
    return {
      key: t.key,
      label: t.label,
      soon: t.is_planned || !sku,
      feats: t.selling_points.length ? t.selling_points : FALLBACK_FEATS[t.key] ?? [],
      days: sku?.period_days ?? 0,
      devices: sku?.device_limit ?? 0,
      price: sku && storeOpen.value ? fmtPrice(sku.price_fen) : '',
      was: off && sku ? fmtPrice(sku.base_price_fen) : '',
      offLabel: off && sku ? sku.discount_display : '',
      // 「最受欢迎」挂 popular_sku 所属档列（数据单源；停售不挂）
      popular: storeOpen.value && !!sku
        && t.key === (skusData.value?.skus.find(s => s.sku_key === skusData.value?.popular_sku)?.tier_key ?? ''),
      href: `/pay?period=${period.value}&tier=${t.key}`,
    }
  })
})

const skeletonCards = FALLBACK_PAID.map(fb => ({
  ...fb, label: periodLabel(fb.period),
}))
</script>

<template>
  <section id="pricing" class="mkt-section">
    <div class="mkt-in">
      <div class="mb-12 text-center">
        <span class="mkt-eyebrow">套餐</span>
        <h2 class="mkt-h2">选择适合你的套餐</h2>
        <p class="mkt-lead max-w-lg mx-auto">微信扫码支付，支付成功套餐立即到账</p>
      </div>

      <!-- 时长 tab 主轴（包月默认；折扣徽标读 discount_display 单源） -->
      <div v-if="periods.length > 1" class="plans-tabs">
        <button
          v-for="p in periods"
          :key="p"
          class="plans-tab"
          :class="{ on: period === p }"
          @click="period = p"
        >
          {{ periodLabel(p) }}<span v-if="periodDiscount(p)" class="plans-tab-mini">{{ periodDiscount(p) }}</span>
        </button>
      </div>

      <div class="plans-grid">
        <!-- 免费列：匿名语境=注册导流，不标「当前方案」（那是收银台登录态语义） -->
        <div class="mkt-plan free">
          <h3>免费</h3>
          <div class="sub">1 台设备</div>
          <div class="price num">¥0</div>
          <div class="feats">
            <div v-for="f in freeFeats" :key="f" class="f">
              <Ico :d="P.check" :style="{ color: 'var(--ok)' }" />
              {{ f }}
            </div>
          </div>
          <AppButton variant="primary" block to="/register">注册领取 7 天试用</AppButton>
        </div>

        <!-- 目录可达：付费档列 / planned 预告卡 -->
        <template v-if="hasCatalog">
          <template v-for="col in paidColumns" :key="col.key">
            <div v-if="col.soon" class="mkt-plan free plans-soon">
              <h3>{{ col.label }}</h3>
              <div class="sub">即将推出</div>
              <p class="soon-note">更高设备上限 · 更强 AI 能力。上线后此处即可选购。</p>
            </div>
            <div v-else class="mkt-plan" :class="{ pro: col.popular }">
              <span v-if="col.popular" class="mkt-pro-pill">最受欢迎</span>
              <h3>{{ col.label }}</h3>
              <div class="sub">{{ col.days }} 天 · 最多 {{ col.devices }} 台设备</div>
              <div class="price num">
                <template v-if="col.price">
                  {{ col.price }}
                  <span v-if="col.was" class="price-was num">{{ col.was }}</span>
                  <span v-if="col.offLabel" class="price-off">{{ col.offLabel }}</span>
                </template>
                <span v-else class="price-blank">价格见收银台</span>
              </div>
              <div class="feats">
                <div v-for="f in col.feats" :key="f" class="f">
                  <Ico :d="P.check" :style="{ color: col.popular ? 'var(--accent)' : 'var(--ok)' }" />
                  {{ f }}
                </div>
              </div>
              <AppButton
                :variant="col.popular ? 'primary' : 'outline'"
                block
                :to="col.href"
              >立即购买</AppButton>
            </div>
          </template>
        </template>

        <!-- 目录不可达/空目录：降级骨架（结构事实保留，价格留白，入口仍可达） -->
        <template v-else>
          <div v-for="fb in skeletonCards" :key="fb.period" class="mkt-plan free">
            <h3>{{ fb.label }}</h3>
            <div class="sub">{{ fb.days }} 天 · {{ fb.devices }} 台设备</div>
            <div class="price num"><span class="price-blank">价格见收银台</span></div>
            <div class="feats">
              <div class="f"><Ico :d="P.check" :style="{ color: 'var(--ok)' }" />全功能</div>
            </div>
            <AppButton variant="outline" block to="/pay">去收银台</AppButton>
          </div>
        </template>
      </div>
    </div>
  </section>
</template>
