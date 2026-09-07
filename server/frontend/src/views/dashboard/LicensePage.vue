<script setup lang="ts">
/**
 * 我的套餐——档位头汇总 + 套餐明细四版 tab 分页列表（生效中/待激活/已收回）+ 激活入口。
 * 设计事实源：docs/design-s/prototypes/license.html（2026-09-03 tab 分版修订版）
 * 明细走 GET /pay/license/codes 服务端分页（license-grants-pagination），交互与订单页同构：
 * 默认版=生效中；各 tab 独立分页（加载更多）；?tab= 路由同步。
 * 页面级判定单源=code_count：tab 条=code_count>0；整页空态=0 且无生效权益；手工码态=0 且有权益。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppModal from '@/components/ui/AppModal.vue'
import { tierName } from '@/constants/tiers'
import {
  apiPayActivate, apiPayLicense, apiPayLicenseCodes, fmtBj,
  DEFAULT_LICENSE_TAB, LICENSE_TABS, licenseTabFromQuery,
  type LicenseCode, type LicenseTabKey, type LicenseView,
} from '@/api/pay'

const PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const data = ref<LicenseView | null>(null)

/** 明细分页状态（每版独立拉取，切版重置；tabToken 防过期响应） */
const items = ref<LicenseCode[]>([])
const total = ref(0)
const loadingMore = ref(false)
const refreshing = ref(false)
const activeTab = ref<LicenseTabKey>(licenseTabFromQuery(route.query.tab))

const tabLabel = computed(() => LICENSE_TABS.find((t) => t.key === activeTab.value)?.label ?? '')
const statusList = computed(() => LICENSE_TABS.find((t) => t.key === activeTab.value)?.statuses)
const hasMore = computed(() => items.value.length < total.value)
/** 页面级判定（code_count 单源；旧后端无字段 ?? 0 → 仅档位头安全退化） */
const codeCount = computed(() => data.value?.code_count ?? 0)
/** 整页空态：无任何套餐行且无生效权益；手工码态（code_count=0 且 remaining_sec>0）= 仅档位头，天然落在两个分支之外 */
const pageEmpty = computed(() => !!data.value && codeCount.value === 0 && data.value.remaining_sec <= 0)

let tabToken = 0
/** 首载已完成标记：整页 loading 只用于进页首取；切 tab 一律局部刷新（从某类空 tab 切出也绝不整页闪） */
let firstLoadDone = false
/** 置灰延迟：请求超过 200ms 才置灰旧列表——秒回的切版全程无灰闪 */
let dimTimer: number | undefined
const DIM_DELAY_MS = 200

// ── 明细分页（OrdersPage.fetchPage 骨架 + 切版闪烁修补）──
async function fetchPage(reset: boolean): Promise<void> {
  const token = ++tabToken
  if (reset) {
    if (firstLoadDone) {
      dimTimer = window.setTimeout(() => {
        if (token === tabToken) refreshing.value = true
      }, DIM_DELAY_MS)
    } else {
      loading.value = true
    }
  } else {
    loadingMore.value = true
  }
  const page = reset ? 1 : Math.floor(items.value.length / PAGE_SIZE) + 1
  const statuses = statusList.value ?? undefined
  try {
    const res = await apiPayLicenseCodes(page, PAGE_SIZE, statuses)
    if (token !== tabToken) return
    total.value = res.total
    if (reset) {
      items.value = res.items
    } else {
      const seen = new Set(items.value.map((g) => g.code_id))
      items.value = [...items.value, ...res.items.filter((g) => !seen.has(g.code_id))]
    }
  } catch (e) {
    // 失败保留旧列表原样，MUST NOT 误显示空态
    console.error('license codes load failed:', e)
  } finally {
    window.clearTimeout(dimTimer)
    if (token === tabToken) {
      firstLoadDone = true
      loading.value = false
      loadingMore.value = false
      refreshing.value = false
    }
  }
}

/** 切 tab：URL query 同步（默认版省略参数保持 URL 干净；replace 不进历史栈） */
function switchTab(key: LicenseTabKey): void {
  if (key === activeTab.value) return
  activeTab.value = key
  router.replace({ query: { ...route.query, tab: key === DEFAULT_LICENSE_TAB ? undefined : key } })
}

// 浏览器回退/前进改 query → 只还原 tab；刷新统一由 watch(activeTab) 触发（避免双请求）
watch(() => route.query.tab, (v) => {
  const key = licenseTabFromQuery(v)
  if (key !== activeTab.value) activeTab.value = key
})

// 切 tab（switchTab）与 URL 还原两条路径的刷新都收敛到这里
watch(activeTab, () => fetchPage(true))

function durationLabel(g: LicenseCode): string {
  return g.duration_days >= 36500 ? '永久' : `${g.duration_days} 天`
}
function statusText(status: string): string {
  return status === 'active' ? '生效中'
    : status === 'frozen' ? '退款处理中'
      : status === 'pending_activation' ? '待激活'
        : status === 'revoked' ? '已收回' : status // 未知状态按原文（防御误标）
}
function statusPill(status: string): string {
  return status === 'active' ? 'pill-status pill-ok'
    : status === 'frozen' ? 'pill-status pill-warn'
      : status === 'pending_activation' ? 'pill-status pill-warn' : 'pill-tag'
}
function statusSub(g: LicenseCode): string {
  if (g.status === 'frozen') return '退款处理中·已暂停使用；取消退款自动恢复'
  if (g.status === 'active') return `已激活 ${fmtBj(g.activated_at)} · ${fmtBj(g.expires_at, false)} 到期`
  if (g.status === 'pending_activation') return '已到货未激活：不计时、不占额度；未激活前退款全额'
  if (g.status === 'revoked') return '已随退款收回'
  return `状态：${g.status}` // 未知状态按原文渲染（防御后端先行/前端滞后的窗口）
}

// ── 激活（确认弹层 → 接口 → 刷新；两段式第二段的用户入口）──
const confirmOpen = ref(false)
const confirmTarget = ref<LicenseCode | null>(null)
const busy = ref(false)
const toast = ref('')
const activateErr = ref('')

function flash(msg: string) {
  toast.value = msg
  window.setTimeout(() => (toast.value = ''), 2200)
}

async function reload() {
  try {
    data.value = await apiPayLicense()
  } catch (e) {
    console.error('license load failed:', e)
  } finally {
    loading.value = false
  }
}

function askActivate(g: LicenseCode) {
  confirmTarget.value = g
  activateErr.value = ''
  confirmOpen.value = true
}

/** 附录 Z：激活不可激活类错误按 msg 枚举映射为用户口径 */
function activateErrText(msg: string): string {
  if (msg.includes('not_fulfilled')) return '套餐还未到货，暂不能激活'
  if (msg.includes('not_found')) return '找不到对应的套餐记录，请稍后重试'
  if (msg.includes('pending_activation')) return '该套餐当前不能激活（可能已激活或已收回）'
  return msg || '激活失败，请稍后重试'
}

/**
 * 激活成功后的统一刷新入口（防双拉取）：hero 必刷（pending_count/remaining 变化）；
 * 待激活版内激活成功 → 切「全部」让用户看到刚生效的行（switchTab 的 watch 会拉列表）；
 * 其余版（含「全部」内直接激活）留在本版重拉——行在版内 pending→active 迁移。
 */
async function postActivateRefresh() {
  await reload()
  if (activeTab.value === 'pending') switchTab('all')
  else fetchPage(true)
}

async function doActivate() {
  const g = confirmTarget.value
  if (!g) return
  busy.value = true
  try {
    await apiPayActivate(g.order_no)
    confirmOpen.value = false
    confirmTarget.value = null
    flash('激活成功，套餐已开始计时')
    await postActivateRefresh()
  } catch (e) {
    activateErr.value = activateErrText(e instanceof Error ? e.message : '')
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  reload()
  fetchPage(true)
})
</script>

<template>
  <div class="license-page">
    <div class="page-head">
      <div>
        <h1>我的套餐</h1>
        <div class="sub">套餐按状态分版：全部、生效中、待激活、已收回；待激活不计时，点「激活」立即开始使用。</div>
      </div>
      <button class="btn btn-primary" @click="router.push('/pay')">续费或购买时长</button>
    </div>

    <div v-if="loading" class="loading">加载中…</div>

    <template v-else-if="data">
      <!-- 档位头（汇总含手工发放的历史权益；不随 tab 联动） -->
      <div class="panel hero">
        <div class="panel-h">
          <div class="tier-hero">
            <span class="tier-name">{{ tierName(data.tier) }}</span>
            <span v-if="data.remaining_sec > 0" class="pill pill-ok">生效中</span>
            <span v-else class="pill pill-tag">已到期</span>
          </div>
          <span class="sum">
            <span>剩余 <b>{{ data.remaining_desc }}</b></span>
            <span v-if="data.max_expires_at">最远到期 <b>{{ data.max_expires_at.slice(0, 10) }}</b></span>
            <span v-if="data.pending_count > 0">待激活 <b>{{ data.pending_count }} 个</b></span>
          </span>
        </div>
      </div>

      <!-- 整页空态：名下无任何套餐行且无生效权益（tab 条不渲染） -->
      <div v-if="pageEmpty" class="empty">
        <div class="serif">还没有生效中的套餐</div>
        <p>购买套餐后，使用情况与时长明细会展示在这里。</p>
        <button class="btn btn-primary" @click="router.push('/pay')">去看看套餐</button>
      </div>

      <!-- 手工码态：code_count=0 但有剩余权益 → 仅档位头（上方已渲染） -->

      <!-- 明细四版 tab（code_count>0 才渲染） -->
      <template v-else-if="codeCount > 0">
        <div class="seg seg-row" role="tablist" aria-label="套餐状态分版">
          <button
            v-for="t in LICENSE_TABS" :key="t.key"
            role="tab" :aria-selected="t.key === activeTab"
            :class="{ on: t.key === activeTab }"
            @click="switchTab(t.key)"
          >{{ t.label }}</button>
        </div>

        <!-- 某类空态 -->
        <div v-if="items.length === 0 && !loading" class="panel tab-empty">
          <p>没有{{ tabLabel }}的套餐</p>
          <button v-if="activeTab !== 'all'" class="lnk" @click="switchTab('all')">切回全部查看</button>
        </div>

        <!-- 列表 -->
        <template v-else-if="!loading">
          <div class="panel list" :class="{ refreshing }">
            <div v-for="g in items" :key="g.code_id" class="code-row" :class="{ revoked: g.status === 'revoked' && activeTab === 'all' }">
              <div class="g-main">
                <span class="g-tier">{{ tierName(g.tier) }} · {{ durationLabel(g) }}</span>
                <span :class="statusPill(g.status)">{{ statusText(g.status) }}</span>
              </div>
              <div class="g-sub">{{ statusSub(g) }}</div>
              <button v-if="g.status === 'pending_activation'" class="btn btn-primary btn-sm" @click="askActivate(g)">激活</button>
            </div>
          </div>
          <div class="list-tail">
            <span class="cnt">{{ refreshing ? '加载中…' : `已显示 ${items.length} 个 · 共 ${total} 个` }}</span>
            <button v-if="hasMore" class="btn btn-secondary" :disabled="loadingMore" @click="fetchPage(false)">
              {{ loadingMore ? '加载中…' : '加载更多' }}
            </button>
          </div>
        </template>
      </template>
    </template>

    <!-- 激活确认：必须走 AppModal（base.css 两段式 .show 体系，手写弹窗会隐形拦截点击） -->
    <AppModal v-model:open="confirmOpen" title="确认激活套餐">
      <ul class="activate-terms">
        <li>激活后本套餐<b>立即开始计时</b></li>
        <li>此后申请退款将<b>按已使用时长折算</b>，不再全额退</li>
      </ul>
      <div v-if="activateErr" class="activate-err">
        {{ activateErr }}
        <a class="lnk" href="/support" @click.prevent="router.push('/support')">联系客服</a>
      </div>
      <template #footer>
        <button class="btn btn-secondary" @click="confirmOpen = false">再想想</button>
        <button class="btn btn-primary" :disabled="busy" @click="doActivate">确认激活</button>
      </template>
    </AppModal>

    <div v-if="toast" class="toast" role="status">{{ toast }}</div>
  </div>
</template>

<style scoped>
.license-page { max-width: 720px; margin: 0 auto; position: relative; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 24px; }
.page-head h1 { font-family: var(--font-display); font-size: 26px; font-weight: 600; margin: 0; }
.page-head .sub { font-size: 13px; color: var(--muted); margin-top: 6px; }
.loading { padding: 60px; text-align: center; color: var(--muted); }
.panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 6px 22px; transition: opacity .15s; }
.panel.hero { padding: 20px 22px; margin-bottom: 14px; }
.panel.list.refreshing { opacity: .5; pointer-events: none; }
.seg-row { margin-bottom: 16px; }
.tier-hero { display: flex; align-items: center; gap: 10px; }
.tier-name { font-family: var(--font-display); font-size: 22px; font-weight: 600; }
.sum { display: flex; gap: 16px; font-size: 12.5px; color: var(--muted); }
.sum b { color: var(--fg); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.code-row { display: grid; grid-template-columns: 1fr auto; gap: 4px 14px; padding: 13px 0; border-top: 1px solid var(--border); }
.code-row:first-child { border-top: none; }
.code-row.revoked { opacity: 0.55; }
.g-main { display: flex; align-items: center; gap: 10px; }
.g-tier { font-family: var(--font-display); font-weight: 600; font-size: 14px; }
.g-sub { grid-column: 1; font-size: 12.5px; color: var(--muted); }
.code-row .btn { grid-row: 1 / 3; grid-column: 2; align-self: center; }
.btn-sm { padding: 5px 16px; font-size: 13px; }
.tab-empty { padding: 40px 16px; text-align: center; color: var(--muted); font-size: 13.5px; }
.tab-empty p { margin: 0 0 6px; }
.list-tail { display: flex; flex-direction: column; align-items: center; gap: 10px; margin-top: 14px; }
.list-tail .cnt { font-size: 12.5px; color: var(--muted); }
.activate-terms { margin: 0 0 10px; padding-left: 18px; font-size: 13.5px; line-height: 1.9; }
.activate-err { border-radius: var(--radius-lg); background: color-mix(in oklch, red 10%, var(--surface)); padding: 10px 14px; font-size: 13px; }
.activate-err .lnk { color: var(--accent, var(--fg)); cursor: pointer; }
.empty { border: 1px dashed var(--border); border-radius: var(--radius-lg); padding: 64px 32px; text-align: center; color: var(--muted); margin-top: 14px; }
.empty .serif { font-family: var(--font-display); font-size: 19px; color: var(--fg); }
.empty p { margin: 8px 0 0; font-size: 13.5px; }
.empty .btn { margin-top: 16px; }
.toast {
  position: fixed; left: 50%; bottom: 36px; transform: translateX(-50%);
  background: var(--fg); color: var(--surface); border-radius: 8px; padding: 8px 18px;
  font-size: 13px; z-index: 50;
}
</style>
