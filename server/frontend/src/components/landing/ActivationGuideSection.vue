<script setup lang="ts">
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'

const steps = [
  { n: '1', icon: P.download, title: '下载安装', desc: '在官网 www.awesomenovel.com 下载页获取 Windows 安装包或 macOS DMG；Windows 双击即用，macOS 首次打开若提示无法验证开发者：先点「完成」，再到 系统设置 → 隐私与安全性 点「仍要打开」' },
  { n: '2', icon: P.user, title: '注册账号', desc: '应用内或本站注册，自动获得 7 天 PRO 级试用' },
  { n: '3', icon: P.key, title: '激活 License', desc: '官网「套餐」在线购买，微信扫码支付，控制台一键激活，设备自动绑定' },
]
</script>

<template>
  <section id="guide" class="mkt-section alt">
    <div class="mkt-in">
      <div class="mb-14 text-center">
        <span class="mkt-eyebrow">激活指南</span>
        <h2 class="mkt-h2">三步开始创作</h2>
        <p class="mkt-lead max-w-lg mx-auto">从下载到创作，只需三步</p>
      </div>

      <div class="grid md:grid-cols-3 gap-x-10 gap-y-12">
        <div v-for="step in steps" :key="step.n" class="text-center">
          <div class="mkt-step-dot">{{ step.n }}</div>
          <h3 class="step-t serif">
            <Ico :d="step.icon" />{{ step.title }}
          </h3>
          <p class="step-d">{{ step.desc }}</p>
        </div>
      </div>

      <p class="text-center mt-12">
        <router-link to="/login" class="lnk text-sm">已有账号？前往控制台激活 →</router-link>
      </p>
    </div>
  </section>
</template>

<style scoped>
.step-t { display: flex; align-items: center; justify-content: center; gap: 7px; font-size: 17px; font-weight: 600; margin: 0 0 10px; }
.step-t svg { width: 16px; height: 16px; color: var(--accent-strong); flex: none; }
.step-d { font-size: 13.5px; color: var(--muted); line-height: 1.7; max-width: 260px; margin: 0 auto; }
</style>
