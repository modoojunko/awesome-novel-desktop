<script setup lang="ts">
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'

// 真实在途的规划项（2026-09-30 对齐）：朱雀检测＝MAX 档支柱权益（openspec c-zhuque-ai-detect 在途），
// 拆书＝设计稿定稿待立项（docs/design-c/drafts/ai-novel-c端-拆书.html）。
// 旧四条（AI 写章纲/长文记忆/伏笔台账/动笔前聊）均已上线，已挪入上方功能宣传，不再挂「规划中」。
const roadmap = [
  { icon: P.eye, title: '朱雀 AI 味检测', desc: '写完一键送检腾讯朱雀，段落级标出 AI 痕迹，发布前心里有底' },
  { icon: P.book, title: '拆书成设定', desc: '把喜欢的完本小说拆成世界观、人物与大纲，变成你自己开书的起点' },
]
</script>

<template>
  <section id="roadmap" class="mkt-section alt">
    <div class="mkt-in">
      <div class="mb-12 text-center">
        <span class="mkt-eyebrow">路线图</span>
        <h2 class="mkt-h2">即将上线</h2>
        <p class="mkt-lead max-w-lg mx-auto">规划中的能力，敬请期待</p>
      </div>
      <div class="grid sm:grid-cols-2 gap-5 max-w-4xl mx-auto">
        <div
          v-for="(item, i) in roadmap"
          :key="item.title"
          class="mkt-card rd animate-fade-up"
          :style="{ animationDelay: `${0.1 + i * 0.05}s` }"
        >
          <span class="pill pill-tag plan-tag">规划中</span>
          <div class="ico"><Ico :d="item.icon" /></div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.desc }}</p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.rd { position: relative; }
.plan-tag { position: absolute; top: 16px; right: 16px; }
</style>
