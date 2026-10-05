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
 * 营销页套餐区 = 收银台同 IA（s-pay-landing-plans）：时长 tab 主轴×四档对比列（免费/标准/PRO/MAX）。
 * 数据同源 GET /pay/skus，价格走 fmtPrice 单源；卖点兜底/定位语/预告卡 note 走 tierCopy.ts 单源（与收银台同引）。
 * 与收银台的有意差异：匿名语境免费列=注册导流（非「当前方案」）、「最受欢迎」徽标保留、
 * 购买入口带参跳 /pay（无购买条与协议弹窗——那些属收银台登录流程）。
 */
const PERIOD_ORDER: SkuItem['period'][] = ['monthly', 'quarterly', 'yearly']

import { TIER_FALLBACK_FEATS, TIER_POS, TIER_SOON_NOTES } from '@/constants/tierCopy'

// 目录不可达时的降级骨架：时长是产品结构事实，价格/设备数一律留白（设备数不写死，防与权益明细矛盾）
const FALLBACK_PAID = [
  { period: 'monthly' as const, days: 30 },
  { period: 'quarterly' as const, days: 90 },
  { period: 'yearly' as const, days: 365 },
]

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
  return t?.selling_points.length ? t.selling_points : TIER_FALLBACK_FEATS.free
})

/** 四档对比列（免费列在模板固定；planned/无可购 SKU 渲染预告卡） */
const paidColumns = computed(() => {
  const tiers = skusData.value?.tiers.filter(t => t.key !== 'free') ?? []
  // 四档展示：目录还没有 standard 档时，合成一张预告卡补位（目录上了即走真实数据）
  // 合成预告卡补齐目录行形状（is_live 同步 planned，防消费端按 live 判定走岔）
  const cols = tiers.some(t => t.key === 'standard')
    ? tiers
    : [{ key: 'standard', label: '标准', is_live: false, is_planned: true, selling_points: TIER_FALLBACK_FEATS.standard }, ...tiers]
  return cols.map((t) => {
    const sku = skusData.value?.skus.find(s => s.tier_key === t.key && s.period === period.value) ?? null
    const off = storeOpen.value && !!sku && !!sku.discount_display && sku.price_fen < sku.base_price_fen
    return {
      key: t.key,
      label: t.label,
      soon: t.is_planned || !sku,
      feats: t.selling_points.length ? t.selling_points : TIER_FALLBACK_FEATS[t.key] ?? [],
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
  period: fb.period, days: fb.days, label: periodLabel(fb.period),
}))
</script>

<template>
  <section id="pricing" class="mkt-section">
    <div class="mkt-in">
      <div class="mb-12 text-center">
        <span class="mkt-eyebrow">套餐</span>
        <h2 class="mkt-h2">写到哪一程，就选哪一档</h2>
        <p class="mkt-lead max-w-xl mx-auto">人工笔耕全流程免费；想让 AI 多搭把手时再升级——从想大纲、写正文到打磨成书，每档都替你多担一件事。</p>
      </div>

      <!-- 时长 tab 主轴（包月默认；折扣徽标读 discount_display 单源） -->
      <div v-if="periods.length > 1" class="plans-tabs" role="tablist" aria-label="付费时长">
        <button
          v-for="p in periods"
          :key="p"
          class="plans-tab"
          role="tab"
          :aria-selected="period === p"
          :class="{ on: period === p }"
          @click="period = p"
        >
          {{ periodLabel(p) }}<span v-if="periodDiscount(p)" class="plans-tab-mini">{{ periodDiscount(p) }}</span>
        </button>
      </div>

      <div class="plans-grid" :class="{ 'has-skeleton': !hasCatalog }">
        <!-- 免费列：匿名语境=注册导流，不标「当前方案」（那是收银台登录态语义） -->
        <div class="mkt-plan free">
          <h3>免费</h3>
          <div class="pos">{{ TIER_POS.free }}</div>
          <div class="sub">1 台设备</div>
          <div class="price num">¥0</div>
          <!-- 免费档≠试用：免费档永久可用，PRO 级试用是注册另赠（评审 P1-6） -->
          <div class="feats">
            <div v-for="f in freeFeats" :key="f" class="f">
              <Ico :d="P.check" :style="{ color: 'var(--ok)' }" />
              {{ f }}
            </div>
          </div>
          <AppButton variant="primary" block to="/register">免费开始写</AppButton>
          <p class="cta-note">注册另送 7 天 PRO 级试用</p>
        </div>

        <!-- 目录可达：付费档列 / planned 预告卡 -->
        <template v-if="hasCatalog">
          <template v-for="col in paidColumns" :key="col.key">
            <div v-if="col.soon" class="mkt-plan free plans-soon">
              <h3>{{ col.label }}</h3>
              <div class="pos">{{ TIER_POS[col.key] }}</div>
              <div class="sub">即将推出</div>
              <p class="soon-note">{{ TIER_SOON_NOTES[col.key] ?? '上线后此处即可选购。' }}</p>
            </div>
            <div v-else class="mkt-plan paid" :class="{ pro: col.popular }">
              <span v-if="col.popular" class="mkt-pro-pill">最受欢迎</span>
              <h3>{{ col.label }}</h3>
              <div class="pos">{{ TIER_POS[col.key] }}</div>
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
              <!-- 四档统一实心 CTA：档位强调由卡片高亮＋最受欢迎徽标承担 -->
              <AppButton variant="primary" block :to="col.href">立即购买</AppButton>
            </div>
          </template>
        </template>

        <!-- 目录不可达/空目录：降级骨架（结构事实保留，价格留白，入口仍可达） -->
        <template v-else>
          <div v-for="fb in skeletonCards" :key="fb.period" class="mkt-plan free">
            <h3>{{ fb.label }}</h3>
            <div class="sub">{{ fb.days }} 天</div>
            <div class="price num"><span class="price-blank">价格见收银台</span></div>
            <div class="feats">
              <div class="f"><Ico :d="P.check" :style="{ color: 'var(--ok)' }" />全功能</div>
            </div>
            <AppButton variant="outline" block to="/pay">去收银台</AppButton>
          </div>
        </template>
      </div>

      <!-- 权益明细入口：四张卡答不了建书数/设备数/双 Key 规则，漏斗断点补链（评审 P0-2） -->
      <p class="plans-detail-link">
        <router-link to="/plans">四档权益逐项对比（含建书数、设备数、教程与服务）——查看完整权益对比 →</router-link>
      </p>
    </div>
  </section>
</template>
