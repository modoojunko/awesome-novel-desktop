<script setup lang="ts">
import { ref } from 'vue'
import { useSessionStore } from '@/stores/session'
import AppButton from '@/components/ui/AppButton.vue'
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'
import DownloadModal from '@/components/download/DownloadModal.vue'
import { brand } from '@/constants/brand'

const session = useSessionStore()

// mock 书架数据（纯展示，C端 v2 书架视觉）
const books = [
  { title: '山海长歌', meta: '卷二 · 第 14 章', pct: 62, on: true },
  { title: '雾都侦探', meta: '卷一 · 完结', pct: 100 },
  { title: '星轨之下', meta: '卷一 · 第 3 章', pct: 18 },
]

const downloadOpen = ref(false)
</script>

<template>
  <section class="mkt-in grid lg:grid-cols-2 gap-12 items-center py-16 lg:py-24">
    <!-- 左侧文字 -->
    <div class="space-y-6">
      <span class="mkt-pill">
        <Ico :d="P.spark" />
        AI 辅助长篇小说写作平台
      </span>
      <h1 class="text-4xl lg:text-[44px] font-semibold serif leading-tight m-0">
        人铸灵魂，<br />
        <span class="mkt-grad-text">AI 行笔墨</span>
      </h1>
      <p class="mkt-lead max-w-md">
        AI 是笔，你才是作家。构想由你铸就，文字交给 AI，成稿由你拍板。
      </p>
      <div class="flex flex-wrap gap-2">
        <span class="chip">装在自己电脑上</span>
        <span class="chip">从灵感到成书</span>
        <span class="chip">数据只属于你</span>
      </div>

      <div class="flex flex-wrap gap-3">
        <AppButton
          v-if="session.isLoggedIn"
          to="/dashboard"
          variant="primary"
          size="lg"
        >
          进入控制台
        </AppButton>
        <!-- 已登录也保留下载入口（次档位），登录后不再找不到 C端 安装包 -->
        <AppButton
          :variant="session.isLoggedIn ? 'secondary' : 'primary'"
          size="lg"
          @click="downloadOpen = true"
        >
          <Ico :d="P.download" />
          免费下载
        </AppButton>
        <AppButton href="#pricing" variant="secondary" size="lg">查看套餐</AppButton>
      </div>

      <p class="text-sm" style="color: var(--muted)">
        已有激活码？
        <router-link to="/login" class="lnk">去控制台激活 →</router-link>
      </p>
      <p class="text-sm" style="color: color-mix(in oklch, var(--muted) 65%, transparent)">
        支持 Windows 与 macOS · 注册即送 7 天试用
      </p>
    </div>

    <!-- 右侧产品界面示意：C端 v2 书架（纯 CSS，随 token 自动适配） -->
    <div class="hero-mock">
      <div class="hm-bar">
        <span class="hm-logo">{{ brand.mark }}</span>
        <span class="hm-title">{{ brand.name }} · 书架</span>
        <span class="hm-seg"><i class="on"></i><i></i><i></i></span>
      </div>
      <div class="hm-body">
        <div v-for="bk in books" :key="bk.title" class="hm-book" :class="{ on: bk.on }">
          <div class="t">{{ bk.title }}</div>
          <div class="m num">{{ bk.meta }}</div>
          <div class="bar"><i :style="{ width: bk.pct + '%' }"></i></div>
        </div>
        <div class="hm-new">+ 新建书籍</div>
      </div>
    </div>
  </section>

  <!-- 下载弹窗（共享组件，控制台首页同款） -->
  <DownloadModal v-model:open="downloadOpen" />
</template>

