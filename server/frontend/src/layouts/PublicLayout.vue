<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useSessionStore } from '@/stores/session'
import AppButton from '@/components/ui/AppButton.vue'
import SiteBeianBar from '@/components/site/SiteBeianBar.vue'

const route = useRoute()
const session = useSessionStore()

// auth 页：卡片不再带品牌行（导航已有 logo），导航也隐藏指向自身的按钮
const isAuthPage = computed(() => route.name === 'login' || route.name === 'register')
// landing 已有自带页脚（FooterSection 内嵌备案条），外层跳过防同屏双份
const isLanding = computed(() => route.name === 'landing')

onMounted(() => {
  // 从 sessionStore 预取用户信息（如果有 token 的话）
  if (session.isLoggedIn && !session.userFetched) {
    session.fetchUserInfo()
  }
})
</script>

<template>
  <div class="pub-root">
    <header class="mkt-nav">
      <div class="mkt-nav-in">
        <router-link to="/" class="mkt-logo">
          <span class="logo-mark">爱</span>
          爱<span>小说</span>
          <span class="gen-badge num">5.0</span>
        </router-link>
        <nav class="mkt-navlinks">
          <router-link to="/#features" class="nl">功能</router-link>
          <router-link to="/#roadmap" class="nl">路线图</router-link>
          <router-link to="/#pricing" class="nl">套餐</router-link>
          <router-link to="/#guide" class="nl">激活指南</router-link>
        </nav>
        <div class="mkt-acts">
          <template v-if="session.isLoggedIn">
            <AppButton to="/dashboard" size="sm">我的账号</AppButton>
          </template>
          <template v-else>
            <AppButton v-if="route.name !== 'login'" to="/login" variant="ghost" size="sm">登录</AppButton>
            <AppButton v-if="route.name !== 'register'" to="/register" size="sm">注册</AppButton>
          </template>
        </div>
      </div>
    </header>

    <main :class="{ 'auth-main': isAuthPage }">
      <router-view />
    </main>

    <SiteBeianBar v-if="!isLanding" />
  </div>
</template>

<style scoped>
/* 品牌文案「小说」着 accent；:not 防命中同为 span 的 .logo-mark
   （其 白字 规则特异性 (0,1,0) 会被本规则 (0,2,1) 压掉，glyph 隐形） */
.mkt-logo span:not(.logo-mark) {
  color: var(--accent);
  font-weight: inherit;
}
/* 品牌 5.0 层：代际徽标（覆盖上面 :not 规则的 accent 着色，同特异性靠后赢） */
.mkt-logo span.gen-badge {
  color: var(--accent-strong);
  background: var(--accent-soft);
  border: 1px solid color-mix(in oklch, var(--accent) 25%, transparent);
}

/* 营销壳列布局：main 吃满剩余高度，auth 页在壳内水平+垂直居中。
   safe center 防移动端长卡（注册页）居中溢出裁顶；不支持时退化为 stretch 不裁切 */
.pub-root {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}
.pub-root main {
  flex: 1;
}
.auth-main {
  display: grid;
  place-items: safe center;
  padding: 40px 24px;
}
/* grid 居中是 shrink-to-fit：不定宽会被 .input 的 width:100% 算成 max-content，
   显式定宽到各自 .auth-card 的 max-width 上限 */
.auth-main :deep(.auth-card) {
  width: 100%;
}
</style>
