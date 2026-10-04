<script setup lang="ts">
</script>

<template>
  <!-- 品牌 5.0 代际段：开源 v1–v4.28 → Awesome Novel 5.0（血统宣示，口径见 docs/marketing/brand-copy-update-review.md） -->
  <section class="mkt-section lineage-sec">
    <div class="mkt-in">
      <div class="mb-12 text-center">
        <span class="mkt-eyebrow">五代一脉</span>
        <h2 class="mkt-h2">从开源工具到 <span class="mkt-grad-text">Awesome Novel 5.0</span></h2>
        <p class="mkt-lead max-w-xl mx-auto">你熟悉的六阶段工作流没有变——它长成了全新的桌面工作台。</p>
      </div>
      <div class="gens">
        <div class="gen-card past animate-fade-up">
          <div class="era">开源时代 · 社区共创</div>
          <h3>awesome-novel <span class="ver num">v1 – v4.28</span></h3>
          <p>提示词驱动的开源写作工具，六阶段工作流在此沉淀；AGPL 开源，社区共创，至今仍在独立维护。</p>
        </div>
        <div class="gen-link" aria-hidden="true">
          <span class="ln">→<i>进化</i></span>
        </div>
        <div class="gen-card now animate-fade-up" style="animation-delay: 0.08s">
          <span class="big5 num" aria-hidden="true">5.0</span>
          <div class="era">桌面时代 · AI 工作台</div>
          <h3>爱小说 · Awesome Novel <span class="ver now-tag num">5.0 全新一代</span></h3>
          <p>装在自己电脑上的长篇小说工作台：AI 长在流程里，数据不出电脑；开源版的旧稿，导入即续写。</p>
        </div>
      </div>
      <p class="gen-foot">5.0 是产品代际；安装包上的版本号是桌面软件的工程版本，两者各自独立演进。</p>
    </div>
  </section>
</template>

<style scoped>
.lineage-sec { padding-top: 24px; }
.gens { position: relative; display: grid; grid-template-columns: 1fr 88px 1fr; align-items: stretch; max-width: 900px; margin: 44px auto 0; }
@media (max-width: 800px) { .gens { grid-template-columns: 1fr; gap: 14px; } .gen-link { display: none; } }
.gen-card { border-radius: 16px; padding: 26px 28px; text-align: left; position: relative; }
.gen-card.past { border: 1px solid var(--border); background: var(--surface); }
.gen-card.now { background: color-mix(in oklch, var(--accent) 6%, var(--surface)); border: 1.5px solid color-mix(in oklch, var(--accent) 45%, transparent); box-shadow: var(--shadow-card); }
.gen-card .era { font-size: 11.5px; letter-spacing: 0.22em; font-weight: 600; color: var(--muted); }
.gen-card.now .era { color: var(--accent-strong); }
.gen-card h3 { font-family: var(--font-display); font-size: 21px; font-weight: 600; margin: 8px 0 3px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.gen-card .ver { font-family: var(--font-mono); font-size: 12px; font-weight: 600; color: var(--muted); background: var(--fg-soft); border-radius: 999px; padding: 2px 10px; }
.gen-card .ver.now-tag { color: var(--accent-strong); background: var(--accent-soft); }
.gen-card p { font-size: 13px; color: var(--muted); line-height: 1.8; margin: 10px 0 0; }
.gen-card .big5 { position: absolute; top: 14px; right: 20px; font-family: var(--font-mono); font-size: 56px; font-weight: 700; line-height: 1; color: color-mix(in oklch, var(--accent) 26%, transparent); }
.gen-link { display: grid; place-items: center; }
.gen-link .ln { display: flex; flex-direction: column; align-items: center; gap: 4px; color: color-mix(in oklch, var(--accent) 55%, transparent); font-size: 12px; font-weight: 600; }
.gen-link .ln i { font-style: normal; }
.gen-foot { text-align: center; font-size: 12px; color: var(--faint); margin: 16px 0 0; }
</style>
