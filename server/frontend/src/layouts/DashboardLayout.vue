<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'
import SiteBeianBar from '@/components/site/SiteBeianBar.vue'
import { brand } from '@/constants/brand'

const router = useRouter()
const session = useSessionStore()

// none→中性、trial→warn、付费→ok
const tierCls = computed(() => {
  if (session.tier === 'none') return ''
  if (session.tier === 'trial') return 'pill-warn'
  return 'pill-ok'
})

function handleLogout() {
  session.logout()
  router.push('/')
}

onMounted(async () => {
  if (session.isLoggedIn) {
    // 等 me 完成再应用主题：会话恢复时已存主题不闪默认（fetchUserInfo 只存不碰 DOM）
    if (!session.userFetched) await session.fetchUserInfo()
    session.applyTheme(session.theme)
  }
})
</script>

<template>
  <div class="dash">
    <header class="appbar">
      <router-link to="/dashboard" class="brand">
        <span class="logo-mark">{{ brand.mark }}</span>
        <span class="brand-name serif">{{ brand.name }}</span>
      </router-link>
      <nav class="nav">
        <router-link to="/dashboard" exact-active-class="on">首页</router-link>
        <router-link to="/dashboard/license" active-class="on">我的套餐</router-link>
        <router-link to="/dashboard/orders" active-class="on">我的订单</router-link>
        <router-link to="/dashboard/devices" active-class="on">我的设备</router-link>
        <router-link to="/dashboard/account" active-class="on">账户</router-link>
      </nav>
      <div class="spacer" />
      <span class="pill pill-status" :class="tierCls">{{ session.tierDisplay }}</span>
      <span class="who">{{ session.username || '用户' }}</span>
      <button class="quit" @click="handleLogout">
        <Ico :d="P.logout" />
        <span class="q-text">退出登录</span>
      </button>
    </header>

    <main class="dash-main">
      <router-view />
    </main>

    <SiteBeianBar />
  </div>
</template>

<style scoped>
.appbar { position: sticky; top: 0; z-index: 40; }
.brand { display: inline-flex; align-items: center; gap: 8px; color: var(--fg); text-decoration: none; }
.brand-name { font-size: 15px; font-weight: 600; }
.who { font-size: 13px; color: var(--muted); max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.quit { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 8px; font-size: 13px; color: var(--muted); }
.quit:hover { color: var(--fg); background: var(--fg-soft); }
.quit svg { width: 15px; height: 15px; }
.dash-main { max-width: 1024px; margin-inline: auto; width: 100%; padding: 28px 24px 48px; }

@media (max-width: 640px) {
  .brand-name, .who, .appbar > .b { display: none; }
  .quit { padding: 5px 7px; }
  .q-text { display: none; }
}
</style>
