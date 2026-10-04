<script setup lang="ts">
import SiteBeianBar from '@/components/site/SiteBeianBar.vue'
import { brand, brandCopyright } from '@/constants/brand'
</script>

<template>
  <footer class="mkt-foot">
    <div class="foot-lockup">
      <span class="mark serif">{{ brand.mark }}</span>
      <span class="lk serif">{{ brand.name }} · {{ brand.nameEn }}</span>
      <span class="gen-badge num">5.0</span>
    </div>
    <div class="mkt-foot-in">
      <router-link to="/support">联系客服</router-link>
      <router-link to="/login">控制台登录</router-link>
    </div>
    <p class="foot-tag serif">
      你的小说永远属于你 —— 所有创作内容存储在本地，我们不收集任何用户数据。
    </p>
    <p class="foot-cr">{{ brandCopyright() }}</p>
    <p class="foot-lineage">源自开源项目 awesome-novel-agent · 第 5 代</p>
    <!-- 工信部要求：备案号悬挂于网站底部并链接工信部系统 -->
    <SiteBeianBar />
  </footer>
</template>

<style scoped>
.foot-tag { text-align: center; font-size: 13.5px; color: var(--muted); max-width: 480px; margin: 18px auto 0; line-height: 1.7; }
.foot-cr { text-align: center; font-size: 12px; color: color-mix(in oklch, var(--muted) 70%, transparent); margin: 14px 0 0; }
.foot-tag, .foot-cr { padding: 0 24px; }
.foot-lockup { display: flex; align-items: center; justify-content: center; gap: 9px; margin-top: 26px; }
.foot-lockup .mark { width: 26px; height: 26px; border-radius: 7px; background: var(--accent); color: var(--on-accent); display: grid; place-items: center; font-size: 14px; }
.foot-lockup .lk { font-size: 17px; font-weight: 600; }
.foot-lineage { text-align: center; font-size: 11.5px; color: color-mix(in oklch, var(--muted) 60%, transparent); margin: 6px 0 0; }
</style>
