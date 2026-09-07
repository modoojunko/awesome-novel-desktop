<script setup lang="ts">
import SiteBeianBar from '@/components/site/SiteBeianBar.vue'
import { brandCopyright } from '@/constants/brand'
</script>

<template>
  <footer class="mkt-foot">
    <div class="mkt-foot-in">
      <a href="https://github.com/modoojunko/ai-novel" target="_blank" rel="noopener">GitHub</a>
      <router-link to="/support">联系客服</router-link>
      <router-link to="/login">控制台登录</router-link>
    </div>
    <p class="foot-tag serif">
      你的小说永远属于你 —— 所有创作内容存储在本地，我们不收集任何用户数据。
    </p>
    <p class="foot-cr">{{ brandCopyright() }}</p>
    <!-- 工信部要求：备案号悬挂于网站底部并链接工信部系统 -->
    <SiteBeianBar />
  </footer>
</template>

<style scoped>
.foot-tag { text-align: center; font-size: 13.5px; color: var(--muted); max-width: 480px; margin: 18px auto 0; line-height: 1.7; }
.foot-cr { text-align: center; font-size: 12px; color: color-mix(in oklch, var(--muted) 70%, transparent); margin: 14px 0 0; }
.foot-tag, .foot-cr { padding: 0 24px; }
</style>
