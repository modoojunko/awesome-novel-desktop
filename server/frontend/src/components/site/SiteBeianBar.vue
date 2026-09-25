<script setup lang="ts">
import { siteBeian, hasBeianInfo } from '@/constants/site-beian'
</script>

<template>
  <!-- 全站统一备案信息条；两段皆空整条隐藏，不留占位空壳 -->
  <footer v-if="hasBeianInfo()" class="beian-bar">
    <nav class="legal-links" aria-label="法律文件">
      <a href="/legal/eula.html">软件许可协议</a>
      <a href="/legal/user-agreement.html">用户服务协议</a>
      <a href="/legal/payment-notice.html">付费须知</a>
      <a href="/legal/refund-policy.html">退款政策</a>
      <a href="/legal/privacy-policy.html">隐私政策</a>
    </nav>
    <span class="sep" aria-hidden="true">|</span>
    <a
      v-if="siteBeian.icp"
      :href="siteBeian.miitUrl"
      target="_blank"
      rel="noopener"
    >{{ siteBeian.icp }}</a>
    <a
      v-if="siteBeian.police"
      :href="siteBeian.policeUrl"
      target="_blank"
      rel="noopener"
      class="police-link"
    >
      <!-- 公安备案规范：警徽图标 + 编号文字，整体链至 mps 查询页；图标为部署级资产可直换 -->
      <img src="/beian-police.png" alt="" width="13" height="14" aria-hidden="true" />
      {{ siteBeian.police }}
    </a>
  </footer>
</template>

<style scoped>
/* 字级对齐 FooterSection 的 .foot-cr 体系：12px + muted 混色 */
.beian-bar {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 18px;
  padding: 12px 24px;
  font-size: 12px;
  color: color-mix(in oklch, var(--muted) 70%, transparent);
}
.beian-bar a { color: inherit; text-decoration: none; }
.police-link { display: inline-flex; align-items: center; gap: 4px; }
.police-link img { display: block; }
.sep { color: color-mix(in oklch, var(--muted) 40%, transparent); }
.legal-links { display: flex; gap: 14px; }
.legal-links a { color: inherit; text-decoration: none; }
.legal-links a:hover { color: var(--fg); }
.beian-bar a:hover { color: var(--fg); }
</style>
