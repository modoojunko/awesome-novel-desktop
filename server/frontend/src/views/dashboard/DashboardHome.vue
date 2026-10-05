<script setup lang="ts">
/**
 * 控制台首页——问候 + 被动提醒横幅 + 四卡（我的套餐/我的设备/下载客户端/我的账户）。
 * 设计事实源：docs/design-s/prototypes/console.html + frontend-detail-design §3.2
 * （LicenseCard 与激活码 modal 整体移除——套餐视图由「我的套餐」承担）
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import { useDeviceStore } from '@/stores/devices'
import { usePageLoad } from '@/composables/usePageLoad'
import AppButton from '@/components/ui/AppButton.vue'
import AppCard from '@/components/ui/AppCard.vue'
import DownloadModal from '@/components/download/DownloadModal.vue'
import LoadingSkeleton from '@/components/ui/LoadingSkeleton.vue'
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'
import {
  apiPayLicense, apiPayOrders, fenToYuan,
  type LicenseView, type OrderListItem,
} from '@/api/pay'

const router = useRouter()
const session = useSessionStore()
const deviceStore = useDeviceStore()

const showDownloadModal = ref(false)
const license = ref<LicenseView | null>(null)
const orders = ref<OrderListItem[]>([])

const { loadError, retry } = usePageLoad(() => Promise.all([
  session.fetchUserInfo(),
  deviceStore.fetchDevices(),
  apiPayLicense().then((m) => (license.value = m)),
  apiPayOrders(1, 50).then((r) => (orders.value = r.items)),
]))

// ── HomeBanner（L1 被动提醒，最多一条；优先级：退款处理中 > 试用临期）──
const banner = computed(() => {
  const refunding = orders.value.find(
    (o) => o.status === 'refund_processing' || o.status === 'refund_pending',
  )
  if (refunding) {
    return {
      kind: 'refund_processing' as const,
      text: refunding.refund_amount_fen
        ? `您有一笔退款正在处理中（预计退 ${fenToYuan(refunding.refund_amount_fen)}，一般数分钟至 3 个工作日到账）。`
        : '您有一笔退款正在处理中。',
      to: `/dashboard/orders/${refunding.order_no}`,
      link: '查看进度',
    }
  }
  const m = license.value
  if (m && m.tier === 'trial' && m.remaining_sec > 0 && m.remaining_sec <= 7 * 86400) {
    const days = Math.max(1, Math.ceil(m.remaining_sec / 86400))
    return {
      kind: 'trial_ending' as const,
      text: `试用还剩 ${days} 天。到期后回到免费版：本地作品与数据不受任何影响，AI 与高级功能需购买套餐继续。`,
      to: '/pay',
      link: '看看套餐',
    }
  }
  return null
})

const tierName = computed(() => {
  const t = license.value?.tier ?? ''
  if (t === 'trial') return '试用'
  if (t === 'max') return 'MAX'
  if (t === 'pro') return 'PRO'
  return '免费'
})

const licenseStatusPill = computed(() => {
  const m = license.value
  if (!m) return { cls: 'pill-tag', text: '—' }
  if (m.tier === 'trial' && m.remaining_sec > 0) {
    return { cls: 'pill-warn', text: `试用 · 剩 ${Math.max(1, Math.ceil(m.remaining_sec / 86400))} 天` }
  }
  return m.remaining_sec > 0 ? { cls: 'pill-ok', text: '生效中' } : { cls: 'pill-tag', text: '已到期' }
})

const todayText = computed(() => {
  const weeks = ['星期日', '星期一', '星期二', '星期三', '星期四', '星期五', '星期六']
  const d = new Date()
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日 · ${weeks.at(d.getDay())}`
})
</script>

<template>
  <div class="page-col">
    <!-- 欢迎行 -->
    <div class="page-head">
      <div>
        <h1>你好，{{ session.username || '用户' }}</h1>
        <p class="sub">{{ todayText }}</p>
      </div>
      <AppButton variant="primary" @click="router.push('/pay')">
        {{ license?.tier === 'trial' ? '购买套餐，继续使用' : '续费或购买时长' }}
      </AppButton>
    </div>

    <!-- 加载态 -->
    <LoadingSkeleton v-if="session.isLoading && !loadError" variant="license" />

    <!-- 错误态 -->
    <div v-else-if="loadError" class="err-box">
      <p>加载失败</p>
      <AppButton variant="secondary" size="sm" @click="retry">重试</AppButton>
    </div>

    <!-- 内容区 -->
    <template v-else>
      <!-- 被动提醒横幅（最多一条） -->
      <div v-if="banner" class="notice warn" role="status">
        {{ banner.text }}
        <a class="lnk" @click.prevent="router.push(banner.to)">{{ banner.link }}</a>
      </div>

      <!-- 四卡 -->
      <div class="cards">
        <!-- 我的套餐 -->
        <AppCard hoverable :class="{ hl: license?.tier === 'trial' }">
          <div class="panel-h">
            <span class="qt serif">我的套餐</span>
            <span v-if="licenseStatusPill.text !== '—'" class="pill" :class="licenseStatusPill.cls">{{ licenseStatusPill.text }}</span>
          </div>
          <div class="row">
            <span class="big">{{ tierName }}</span>
          </div>
          <div class="meta" v-if="license">
            <template v-if="license.remaining_sec > 0">剩余 {{ license.remaining_desc }}</template>
            <template v-else>当前无生效中的套餐时长</template>
            <template v-if="license.max_expires_at"> · 最远到期 {{ license.max_expires_at.slice(0, 10) }}</template>
            <template v-if="license.pending_count > 0"> · 待激活 {{ license.pending_count }} 个</template>
          </div>
          <div class="ops">
            <AppButton
              :variant="license?.tier === 'trial' ? 'primary' : 'secondary'"
              size="sm"
              @click="router.push(license?.tier === 'trial' ? '/pay' : '/dashboard/license')"
            >
              {{ license?.tier === 'trial' ? '购买套餐' : '查看套餐明细' }}
            </AppButton>
          </div>
        </AppCard>

        <!-- 我的设备 -->
        <AppCard hoverable>
          <div class="panel-h"><span class="qt serif">我的设备</span></div>
          <div class="row">
            <span class="metric num">{{ deviceStore.activatedCount }}<small>/ {{ deviceStore.activeLimit }} 台</small></span>
          </div>
          <div class="meta">额度按已购最高档计算</div>
          <div class="ops">
            <AppButton variant="secondary" size="sm" @click="router.push('/dashboard/devices')">管理设备</AppButton>
          </div>
        </AppCard>

        <!-- 下载客户端：登录后唯一能拿到安装包的入口 -->
        <AppCard hoverable>
          <div class="panel-h"><span class="qt serif">下载客户端</span></div>
          <div class="row two">
            <AppButton variant="secondary" size="sm" @click="showDownloadModal = true">Windows 版</AppButton>
            <AppButton variant="secondary" size="sm" @click="showDownloadModal = true">macOS 版</AppButton>
          </div>
          <div class="meta">在客户端里使用全部写作功能；套餐时长与设备额度与网页端同步。</div>
          <div class="ops"><span class="mini">免费下载 · 注册另送 7 天 PRO 级试用</span></div>
        </AppCard>

        <!-- 我的账户 -->
        <AppCard hoverable>
          <div class="panel-h"><span class="qt serif">我的账户</span></div>
          <div class="meta acc">账号 {{ session.username || '—' }}</div>
          <div class="ops">
            <AppButton variant="secondary" size="sm" @click="router.push('/dashboard/account')">修改密码</AppButton>
            <button class="lnk danger" @click="session.logout(); router.push('/login')">退出登录</button>
          </div>
        </AppCard>
      </div>
    </template>

    <!-- 下载弹窗（与落地页共享） -->
    <DownloadModal v-model:open="showDownloadModal" />
  </div>
</template>

<style scoped>
.page-col { display: flex; flex-direction: column; gap: 20px; }
.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.page-head h1 { font-family: var(--font-display); font-size: 26px; font-weight: 600; margin: 0; }
.page-head .sub { font-size: 13px; color: var(--muted); margin: 6px 0 0; }
.notice.warn {
  background: color-mix(in oklch, orange 12%, var(--surface));
  border-radius: var(--radius-lg); padding: 12px 16px; font-size: 13.5px;
}
.lnk { color: var(--accent, var(--fg)); cursor: pointer; font-size: 12.5px; }
.lnk.danger { color: var(--muted); background: none; border: none; padding: 0; }
.lnk.danger:hover { color: var(--fg); }
.cards { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.panel-h { display: flex; align-items: center; justify-content: space-between; }
.qt { font-size: 15px; font-weight: 600; }
.row { margin-top: 12px; display: flex; align-items: baseline; gap: 8px; }
.row.two { gap: 8px; }
.big { font-family: var(--font-display); font-size: 24px; font-weight: 600; }
.metric { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-size: 24px; font-weight: 600; color: var(--accent-strong); }
.metric small { font-size: 12px; font-weight: 400; color: var(--muted); margin-left: 3px; }
.meta { font-size: 12.5px; color: var(--muted); margin-top: 6px; }
.meta.acc { margin-top: 14px; }
.mini { font-size: 11.5px; color: var(--muted); }
.ops { margin-top: 14px; display: flex; align-items: center; gap: 10px; }
.pill { border-radius: 999px; font-size: 11.5px; padding: 2px 10px; }
.pill-ok { background: color-mix(in oklch, green 14%, var(--surface)); }
.pill-warn { background: color-mix(in oklch, orange 16%, var(--surface)); }
.pill-tag { background: color-mix(in oklch, var(--fg) 8%, var(--surface)); color: var(--muted); }
.err-box { text-align: center; padding: 48px 0; color: var(--muted); display: flex; flex-direction: column; align-items: center; gap: 12px; }
@media (max-width: 880px) { .cards { grid-template-columns: minmax(0, 1fr); } }
</style>
