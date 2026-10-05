<script setup lang="ts">
/**
 * 套餐权益明细页（tier-plan-four-tiers 批次二；评审 P0-2 漏斗断点修复）。
 * 入口＝落地页套餐区「查看完整权益对比」＋收银台链接。
 * 内容＝四档权益矩阵终版（2026-10-05 拍板，与 docs/marketing/s-landing-copy 同源口径）；
 * 价格为拍板月付口径——售卖价格以收银台实时目录为准（目录驱动，本页零 API）。
 */
import { computed, ref } from 'vue'

const tiers = [
  { key: 'free', name: '免费', pos: '全流程亲手写，AI 替你记账', price: '¥0', cta: '免费下载', href: '/register' },
  { key: 'standard', name: '标准', pos: 'AI 当军师，正文自己写', price: '¥29.9', cta: '选标准', href: '/pay?period=monthly&tier=standard' },
  { key: 'pro', name: 'PRO', pos: 'AI 当枪手，写完即查', price: '¥59.9', cta: '选 PRO', href: '/pay?period=monthly&tier=pro', popular: true },
  { key: 'max', name: 'MAX', pos: 'AI 替你打磨，人工兜底', price: '¥89.9', cta: '选 MAX', href: '/pay?period=monthly&tier=max' },
] as ReadonlyArray<{ key: string; name: string; pos: string; price: string; cta: string; href: string; popular?: boolean }>

// [功能, 说明, 免费有无, 标准有无, PRO 有无, MAX 有无, MAX 附加标注?]
type Row = [string, string, string, string, string, string, string?]
type Group = { id: string; title: string; rows: Row[] }

const yes = '✓'
const no = '—'

const groups: Group[] = [
  {
    id: 'g-flow',
    title: '写作全流程（人工）—— 永久免费',
    rows: [
      ['建书与书架', '含旧稿导入、无缝续写', yes, yes, yes, yes],
      ['设定手填', '题材/主线/世界观/角色/伏笔/文风 全表单', yes, yes, yes, yes],
      ['卷纲与章纲手写', '卷纲四问页＋章纲 13 格表单＋章内剧情条目', yes, yes, yes, yes],
      ['正文写作', '编辑器＋版本历史＋随时回稿', yes, yes, yes, yes],
      ['导出与阅读器', 'Markdown / Word / 纯文本，排版预览', yes, yes, yes, yes],
      ['备份恢复与完本', '', yes, yes, yes, yes],
      ['归档记账＋AI 提取', '前情/人物状态/伏笔自动入册——免费档唯一 AI，自配模型 Key', yes, yes, yes, yes],
    ],
  },
  {
    id: 'g-plan',
    title: 'AI 规划 —— 标准起，AI 替你想',
    rows: [
      ['卷规划 AI', '三套走法抽卡、铺空缺卷纲', no, yes, yes, yes],
      ['拆章 AI', '三方向抽卡，一章一卡', no, yes, yes, yes],
      ['章纲 AI', '起草/三选一/补缺＋高级字段', no, yes, yes, yes],
      ['卷体检', '已写内容与卷纲的出入评估', no, yes, yes, yes],
      ['单章评估', '章自检 AI 短评', no, yes, yes, yes],
      ['文风建议', '自己写正文时的 AI 修改建议', no, yes, yes, yes],
      ['设定域 AI 全家', '世界/势力/角色/主线/题材/伏笔 AI 填格', no, yes, yes, yes],
      ['人物盘点＋抽卡选人', '', no, yes, yes, yes],
    ],
  },
  {
    id: 'g-write',
    title: 'AI 执笔与质检 —— PRO 起，AI 替你写',
    rows: [
      ['正文 AI 全家', '整章生成/续写/扩写/压缩，随时喊停', no, no, yes, yes],
      ['提示词页签', '写作提示词自定义', no, no, yes, yes],
      ['卷纲冲突检测', '拿章纲对卷纲报冲突：偏离卷目标/事件矛盾/设定互斥', no, no, yes, yes],
      ['朱雀 AI 味检测', '腾讯朱雀送检，段落级标注；单独配置朱雀 Key，送检走你的腾讯额度', no, no, yes, yes],
    ],
  },
  {
    id: 'g-polish',
    title: '精修与进阶 —— MAX 专属：剧情推演、打磨与旁路服务',
    rows: [
      ['去 AI 味加工', '热片驱动＋选区兜底的重写', no, no, no, yes],
      ['文风蒸馏', '贴一段旧稿，AI 学你的文风', no, no, no, yes],
      ['剧情推演', '卡文时把角色放进场景演一回合，看走向', no, no, no, yes],
      ['拆书成设定', '完本小说拆成世界观/人物/大纲', no, no, no, yes, '即将上线'],
    ],
  },
  {
    id: 'g-service',
    title: '内容与服务',
    rows: [
      ['文档教程', '六阶段教程＋激活/下载/FAQ', yes, yes, yes, yes],
      ['视频教程', '分阶段视频课', no, yes, yes, yes],
      ['AI 客服', '账号/订单/激活问题，只读上下文', no, no, yes, yes],
      ['人工客服', '优先通道响应', no, no, no, yes],
      ['新版本内测资格', '抢先体验新能力', no, no, no, yes],
    ],
  },
  {
    id: 'g-spec',
    title: '规格',
    rows: [
      ['建书数', '', '1 本', '3 本', '不限', '不限'],
      ['设备数', '', '1 台', '1 台', '3 台', '10 台'],
      ['创作模型 Key 自配（BYOK）', '接 DeepSeek/Kimi/通义等写作大模型，token 费直接付给模型供应商——与朱雀 Key 相互独立', yes, yes, yes, yes],
      ['朱雀 Key 自配', '朱雀检测专用，模型配置页独立页签单独配置；送检消耗你自己的腾讯额度（每月免费额度以腾讯云为准）', no, no, yes, yes],
    ],
  },
]

const flatCount = groups.reduce((n, g) => n + g.rows.length, 0)
const diffOnly = ref(false)
const shownGroups = computed(() =>
  groups.map(g => ({
    ...g,
    rows: diffOnly.value ? g.rows.filter(r => !(r[2] === r[3] && r[3] === r[4] && r[4] === r[5])) : g.rows,
  })).filter(g => g.rows.length > 0),
)

function jump(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>

<template>
  <div class="plans-page">
    <div class="wrap">
      <header class="page-head">
        <span class="mkt-eyebrow">套餐权益明细</span>
        <h1>四档套餐，AI 每深一层升一档</h1>
        <p class="lead">免费走通全部写作流程，AI 从记账开始；往上一档，AI 替你多干一件事。人工能做的，永远属于你。</p>
      </header>

      <!-- 档位卡 -->
      <div class="tier-cards">
        <div v-for="t in tiers" :key="t.key" class="tier-card" :class="{ pro: t.popular }">
          <span v-if="t.popular" class="pop">最受欢迎</span>
          <h3>{{ t.name }}</h3>
          <div class="pos">{{ t.pos }}</div>
          <div class="price num">{{ t.price }}<span class="per"> /月起</span></div>
          <router-link class="btn" :class="t.popular ? 'btn-primary' : 'btn-secondary'" :to="t.href">{{ t.cta }}</router-link>
        </div>
      </div>

      <!-- 分组锚 + 只看差异 -->
      <nav class="group-nav" aria-label="权益分组">
        <a v-for="g in groups" :key="g.id" :href="`#${g.id}`" @click.prevent="jump(g.id)">{{ g.title.split(' —— ')[0] }}</a>
        <label class="diff-toggle"><input v-model="diffOnly" type="checkbox">只看档间差异</label>
      </nav>

      <!-- 权益对比表 -->
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>权益明细</th>
              <th>免费<span class="tp">¥0 · 永久</span></th>
              <th>标准<span class="tp">¥29.9 /月起</span></th>
              <th>PRO<span class="tp">¥59.9 /月起</span></th>
              <th>MAX<span class="tp">¥89.9 /月起</span></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="g in shownGroups" :key="g.id">
              <tr class="group-row" :id="g.id"><td :colspan="5">{{ g.title }}</td></tr>
              <tr v-for="r in g.rows" :key="r[0]">
                <td><span class="fn">{{ r[0] }}</span><span v-if="r[1]" class="fd">{{ r[1] }}</span></td>
                <td :class="{ yes: r[2] === yes }">{{ r[2] }}</td>
                <td :class="{ yes: r[3] === yes }">{{ r[3] }}</td>
                <td :class="{ yes: r[4] === yes }">{{ r[4] }}</td>
                <td :class="{ yes: r[5] === yes }">{{ r[5] }}<span v-if="r[6]" class="soon">{{ r[6] }}</span></td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <div class="foot-notes">
        <p><b>①</b> 平台涉及两种自配 Key，相互独立：<b>创作模型 Key</b>（全档可配，DeepSeek、Kimi、通义等，token 费直接付给模型供应商）与<b>朱雀 Key</b>（朱雀检测专用，模型配置页独立页签单独配置，送检走你自己的腾讯额度，每月免费额度以腾讯云为准）。会员费买的是功能解锁资格，不是算力。</p>
        <p><b>②</b> 注册即送 7 天 PRO 级试用，权益与 PRO 相同。</p>
        <p><b>③</b> 带「即将上线」标记的能力在上线前不计入对应档位承诺；已上线能力以本表为准。</p>
        <p><b>④</b> 月付价格 2026-10 拍板：免费 0／标准 29.9／PRO 59.9／MAX 89.9；季/年与折扣以收银台实时目录为准；一次性买断时长，无自动续费。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plans-page { min-height: 100vh; }
.wrap { max-width: 1152px; margin-inline: auto; padding: 0 24px 48px; }
.page-head { padding: 44px 0 8px; }
.mkt-eyebrow { font-size: 12px; letter-spacing: 0.25em; color: var(--accent-strong); font-weight: 500; }
h1 { font-family: var(--font-display); font-size: 32px; font-weight: 600; margin: 10px 0 10px; }
.lead { font-size: 14.5px; color: var(--muted); line-height: 1.7; max-width: 640px; }

.tier-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 26px 0 30px; }
@media (max-width: 960px) { .tier-cards { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 640px) { .tier-cards { grid-template-columns: 1fr; } }
.tier-card { border: 1px solid var(--border); border-radius: 14px; background: var(--surface); padding: 18px 18px 16px; position: relative; display: flex; flex-direction: column; }
.tier-card.pro { background: color-mix(in oklch, var(--accent) 4%, var(--surface)); border-color: color-mix(in oklch, var(--accent) 30%, transparent); box-shadow: var(--shadow-card); }
.tier-card .pop { position: absolute; top: -10px; left: 14px; font-size: 10.5px; padding: 2px 10px; border-radius: 999px; background: var(--accent); color: var(--surface); letter-spacing: 0.04em; }
.tier-card h3 { font-family: var(--font-display); font-size: 17px; font-weight: 600; margin: 0; }
.tier-card .pos { font-size: 12px; color: var(--accent-strong); margin-top: 3px; }
.tier-card .price { font-family: var(--font-display); font-size: 24px; font-weight: 600; margin-top: 10px; }
.tier-card .price .per { font-family: var(--font-body); font-size: 11.5px; font-weight: 400; color: var(--muted); }
.tier-card .btn { margin-top: 12px; width: 100%; height: 34px; justify-content: center; display: inline-flex; align-items: center; border-radius: var(--radius); font-size: 13.5px; font-weight: 500; border: 1px solid transparent; }
.btn-primary { background: var(--accent); color: var(--on-accent); }
.btn-primary:hover { background: var(--accent-strong); }
.btn-secondary { background: var(--surface); color: var(--fg); border-color: var(--border); }
.btn-secondary:hover { border-color: var(--fg); }

.group-nav { position: sticky; top: 60px; z-index: 40; display: flex; gap: 8px; flex-wrap: wrap; padding: 10px 0; background: color-mix(in srgb, var(--bg) 92%, transparent); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); }
.group-nav a { font-size: 12.5px; color: var(--muted); border: 1px solid var(--border); background: var(--surface); border-radius: 999px; padding: 4px 13px; }
.group-nav a:hover { color: var(--fg); border-color: var(--fg); }
.diff-toggle { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--muted); cursor: pointer; user-select: none; }
.diff-toggle input { accent-color: var(--accent); }

.table-wrap { overflow-x: auto; margin: 22px 0 10px; border: 1px solid var(--border); border-radius: 14px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; min-width: 760px; }
thead th { position: sticky; top: 0; background: var(--fg-soft); z-index: 5; font-size: 13px; font-weight: 600; text-align: center; padding: 12px 10px; border-bottom: 1px solid var(--border); }
thead th:first-child { text-align: left; padding-left: 18px; width: 34%; }
thead th .tp { display: block; font-size: 10.5px; font-weight: 400; color: var(--muted); margin-top: 2px; }
tbody td { padding: 11px 10px; border-bottom: 1px solid var(--border); font-size: 13px; text-align: center; vertical-align: top; }
tbody td:first-child { text-align: left; padding-left: 18px; }
tbody td:first-child .fn { font-weight: 500; }
tbody td:first-child .fd { display: block; font-size: 11.5px; color: var(--muted); margin-top: 2px; line-height: 1.55; }
tbody tr:hover td { background: color-mix(in oklch, var(--accent) 3%, transparent); }
td .yes { color: var(--ok); }
td .no { color: var(--faint); }
td .txt { font-size: 12px; color: var(--muted); }
td .soon { display: inline-block; font-size: 10px; color: var(--warn); background: var(--warn-soft); border-radius: 999px; padding: 1px 7px; margin-left: 6px; }
tr.group-row td { background: var(--fg-soft); font-family: var(--font-display); font-size: 13.5px; font-weight: 600; text-align: left; padding: 9px 18px; color: var(--accent-strong); letter-spacing: 0.04em; }
tr.diff-hide { display: none; }

.foot-notes { max-width: 860px; margin: 18px 0 0; display: flex; flex-direction: column; gap: 6px; }
.foot-notes p { font-size: 12px; color: var(--faint); line-height: 1.7; margin: 0; }
.foot-notes b { color: var(--muted); font-weight: 600; }
</style>
