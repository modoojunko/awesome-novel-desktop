<script setup lang="ts">
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'

const faqs = [
  {
    q: '我不会用电脑，能装上吗？',
    a: '能。点「免费下载」选择你的系统：Windows 安装包双击即用，macOS 拖入应用程序文件夹即可；装好就能写，注册另送 7 天 PRO 级试用。',
  },
  {
    q: 'AI 还要另外花钱吗？',
    a: '创作模型 Key 全档自配：接 DeepSeek、Kimi、通义等，token 费直接付给模型供应商，平台不经手不抽成——会员费买的是功能解锁，不是算力。PRO 以上用朱雀 AI 味检测需另配朱雀 Key，送检消耗你自己的腾讯云额度（每月有免费额度，以腾讯云为准）。',
  },
  {
    q: '爱小说和 awesome-novel 是什么关系？',
    a: '爱小说是开源写作工具 awesome-novel-agent 的第 5 代（5.0 是产品代际，安装包上的版本号是桌面软件的工程版本，两者各自独立演进）。开源版仍按 AGPL 独立维护；你的旧稿随时可以导入爱小说续写。',
  },
  {
    q: 'macOS 安装后提示"无法打开"怎么办？',
    a: 'Apple 会拦截没有开发者证书的应用（独立开发者搞不起）。解决方法：安装后右键「AI Novel」→ 点「打开」→ 再点弹窗里的「打开」即可。只需第一次，以后正常打开。DMG 包里也有「首次使用.command」脚本，双击一次自动完成。',
  },
  {
    q: '生成的文字有 AI 味怎么办？',
    a: '写前定文风、设约束，免费档就有；标准档每章写完有 AI 自检短评；PRO 起成稿可送朱雀检测 AI 味；MAX 有一键去 AI 味重写。文风约束从第一档就在，越往上查得越严。',
  },
  {
    q: '写几十万字，AI 还记得前面写了什么吗？',
    a: '记得。每章定稿会自动归档：前情提要、人物状态变化、伏笔进展都记进台账，后面章节写作时自动带上；埋了的伏笔该回收时还会提醒你。',
  },
  {
    q: '写完能导出吗？',
    a: '能。全书一键导出 Markdown / Word / 纯文本，也能先在阅读器里预览排版效果。稿子就在你自己的电脑上，怎么用都行。',
  },
  {
    q: '可以用我自己的写作风格吗？',
    a: '可以。在「写作风格」里说说你的叙事方式和描写习惯，设定一次，全书所有 AI 输出都按你的风格来。',
  },
  {
    q: '写到一半可以改设定吗？',
    a: '随时改。世界观、角色、风格都能随时调整，之后的章节会自动跟着新设定走，改错了还能找回旧稿。',
  },
]
</script>

<template>
  <section id="faq" class="mkt-section">
    <div class="mkt-in">
      <div class="mb-10 text-center">
        <span class="mkt-eyebrow">常见问题</span>
        <h2 class="mkt-h2">关于创作与 AI 的疑问</h2>
        <p class="mkt-lead max-w-lg mx-auto">这里都有答案</p>
      </div>
      <div class="max-w-2xl mx-auto flex flex-col gap-2.5">
        <details v-for="faq in faqs" :key="faq.q" class="faq-item">
          <summary>
            {{ faq.q }}
            <span class="fq-ic"><Ico :d="P.chevronDown" /></span>
          </summary>
          <div class="fq-a">{{ faq.a }}</div>
        </details>
      </div>
    </div>
  </section>
</template>
