<script setup lang="ts">
import Ico from '@/components/ui/Ico.vue'
import { P } from '@/components/ui/icons'

// 三大痛点支柱：怕烂尾 / 不像你 / 有 AI 味（文案以用户语言呈现，不用内部术语）
// 对齐 C 端实况：AI 分卷规划/章纲起草（抽卡三选一）、伏笔台账对账、文风蒸馏、剧情推演均已上线
const pillars = [
  {
    num: '01',
    title: '怕烂尾？',
    promise: '开写前有蓝图，过程中有人盯',
    points: [
      { title: 'AI 先帮你把蓝图搭好', desc: '分卷规划、每章写什么，AI 出草稿你拍板；每一步都有检查，缺了什么会提醒你补上' },
      { title: '埋了的坑，它替你记着', desc: '每个伏笔自动记账，该回收的时候提醒你，前后呼应不写丢' },
      { title: '卡住了？让角色先演一遍', desc: '剧情推演：把角色放进场景里走一回合，合情合理的走向自然浮现' },
      { title: '写一页是一页，随时回到之前任何一稿', desc: '自动保存每一版，写坏了也不怕，一键找回' },
    ],
  },
  {
    num: '02',
    title: '不像你？',
    promise: '越写越像你',
    points: [
      { title: '你的文风，AI 一学就会', desc: '贴一段你写过的旧稿，AI 蒸馏出你的叙事习惯；设定一次，全书都按你的风格写' },
      { title: '去 AI 味', desc: '避开一眼假的机器腔：疲劳词、固定句式、套路描写，帮你拦下来' },
      { title: '10 秒建书，旧稿也能接着写', desc: '填个书名就能开写；已有稿子导入后无缝续写' },
    ],
  },
  {
    num: '03',
    title: '有 AI 味？',
    promise: '机器腔与逻辑漏洞，定稿前拦下',
    points: [
      { title: '每段写完，自动质检', desc: '逻辑硬伤、风格跑偏、人物走形、节奏失衡，生成完当场揪出来' },
      { title: '记得前文的 AI', desc: '它清楚前情、记得角色状态、守你的文风，接得上你写的内容' },
      { title: '从生成到定稿，全程防 AI 味', desc: 'AI 写作时就带着你的风格，成稿前再整体查一遍' },
    ],
  },
]

// 六阶段工作流的用户语言呈现（提示词为内部环节，不向用户展示——对齐 PM 评审）
// 步骤名被 e2e 钉住（建书/设定/大纲/章纲/写作/归档），只改描述
const workflowSteps = [
  { icon: P.book, title: '建书', desc: '填个书名，10 秒开写' },
  { icon: P.tune, title: '设定', desc: '世界观与角色，可深可浅' },
  { icon: P.list, title: '大纲', desc: 'AI 分卷规划，卷卷有目标' },
  { icon: P.doc, title: '章纲', desc: 'AI 起草三选一，拍板再动笔' },
  { icon: P.pencil, title: '写作', desc: '手写或 AI 协作，一章一章推' },
  { icon: P.archive, title: '归档', desc: '前情伏笔自动入册，一键导出成书' },
]

// 关键能力九条 = C 端已上线能力（AI 蓝图/伏笔台账/关系图谱为 2026-09 新补宣传）
const keyFeatures = [
  { icon: P.spark, title: 'AI 写本章', desc: '一口气写完整章，随时喊停；AI 稿采纳才落进正文，写错一键撤回' },
  { icon: P.list, title: 'AI 搭蓝图', desc: '分卷规划、章纲起草：AI 出的每一步都是提案，采纳才生效' },
  { icon: P.bot, title: '抽卡与推演', desc: '章纲、剧情 AI 一次出三版任你挑；卡文时让角色先演一遍，看走向合不合理' },
  { icon: P.doc, title: '伏笔台账', desc: '埋下的坑自动记账，该回收时提醒你，不写丢不烂尾' },
  { icon: P.link, title: '角色关系图谱', desc: '角色关系一图看清，AI 动笔前对齐本卷最新关系' },
  { icon: P.wand, title: '去 AI 味', desc: '避开机器腔，越写越像你' },
  { icon: P.cpu, title: '模型随你选', desc: '接你自己的 AI 服务，DeepSeek、Kimi、通义等主流模型都支持' },
  { icon: P.lock, title: '数据不出电脑', desc: '稿子存在本地，关网也能写' },
  { icon: P.chart, title: '花费心中有数', desc: 'AI 按用量计费，写之前先告诉你大概花多少' },
]
</script>

<template>
  <section id="features" class="mkt-section">
    <div class="mkt-in">
      <span class="mkt-eyebrow">设计思路</span>
      <h2 class="mkt-h2">三个最常见的写作困境，一次解决</h2>
      <p class="mkt-lead max-w-lg">不是功能堆叠，是围绕写作困境设计的完整工作流。</p>

      <!-- 三大痛点支柱 -->
      <div class="grid md:grid-cols-3 gap-5 mt-12">
        <div
          v-for="(pillar, i) in pillars"
          :key="pillar.num"
          class="mkt-card animate-fade-up"
          :style="{ animationDelay: `${0.1 + i * 0.05}s` }"
        >
          <div class="pillar-num serif num">{{ pillar.num }}</div>
          <h3>{{ pillar.title }}</h3>
          <p class="promise">{{ pillar.promise }}</p>
          <div class="mt-4 flex flex-col gap-2.5">
            <div
              v-for="point in pillar.points"
              :key="point.title"
              class="point"
            >
              <h4>{{ point.title }}</h4>
              <p>{{ point.desc }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 六阶段工作流 -->
      <div class="mt-16 mb-4 text-center">
        <span class="mkt-eyebrow">创作流程</span>
        <h3 class="sub-h">六阶段创作流程</h3>
        <p class="mkt-lead">从灵感到成书，每一步都有明确的出口</p>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3.5">
        <div
          v-for="(step, i) in workflowSteps"
          :key="step.title"
          class="mkt-card wf animate-fade-up"
          :style="{ animationDelay: `${0.1 + i * 0.05}s` }"
        >
          <div class="ico"><Ico :d="step.icon" /></div>
          <div class="t">{{ step.title }}</div>
          <div class="d">{{ step.desc }}</div>
        </div>
      </div>

      <!-- 关键功能条 -->
      <div class="mt-16 mb-4 text-center">
        <span class="mkt-eyebrow">关键能力</span>
        <h3 class="sub-h">为长篇而生的 AI 能力</h3>
      </div>
      <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        <div
          v-for="(feature, i) in keyFeatures"
          :key="feature.title"
          class="mkt-card kf animate-fade-up"
          :style="{ animationDelay: `${0.1 + i * 0.05}s` }"
        >
          <div class="ico"><Ico :d="feature.icon" /></div>
          <div class="min-w-0">
            <h3>{{ feature.title }}</h3>
            <p>{{ feature.desc }}</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.sub-h { font-family: var(--font-display); font-size: 22px; font-weight: 600; margin: 10px 0 8px; line-height: 1.3; }
.pillar-num { font-size: 34px; font-weight: 600; color: color-mix(in oklch, var(--accent) 45%, transparent); line-height: 1; }
.promise { font-size: 13.5px; color: var(--accent-strong); margin: 2px 0 0; }
.point { border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; background: var(--fg-soft); }
.point h4 { font-size: 13px; font-weight: 500; margin: 0; }
.point p { font-size: 12.5px; color: var(--muted); margin: 4px 0 0; line-height: 1.6; }
.wf { padding: 18px 14px; text-align: center; }
.wf .ico { margin-inline: auto; }
.wf .t { font-size: 14px; font-weight: 500; }
.wf .d { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.6; }
.kf { display: flex; gap: 16px; align-items: flex-start; padding: 22px; }
.kf .ico { margin-bottom: 0; flex: none; }
.kf h3 { margin-top: 1px; }
</style>
