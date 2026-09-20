## 1. 页签同位＋卷视图衬垫（commit 8c48f01）

- [x] 1.1 撤 editor-toolbar 独立工具行：排版/专注/版本历史/归档并入 e-head 右侧（ChapterWorkspace `.e-head-row`/`.prose-ctrls`；book.css 撤三栏覆写＋补行式布局）；章页签条紧贴头部。验证：DOM 实测章/卷 `.ch-tabs` 顶边 Y 相等（209.09px）、`editor-toolbar` 节点数 0、头部→页签间隙 0px（两视图）。
- [x] 1.2 章页签顺序对齐原型（章纲→正文→提示词→…→操作；提示词 PRO-only 插在正文后）。验证：e2e 探针断言页签名逐一相等（trial 8 项/免费 7 项口径以 trial 验证）。
- [x] 1.3 卷视图补 `.vol-shell .e-pad` 衬垫 18/22/24＋清 tpl-row/.field 死选择器；「章节拆分」补 open。验证：计算样式 pad="18px 22px 24px"；六分节 open:true 全过；应用 vs 原型截图对比留档。
- [x] 1.4 e2e `.editor-toolbar .ch-name` 断言改 `.col-editor .e-title`。验证：workbench-features.spec 全绿。

## 2. AI 入口唯一化右栏（commit 3aeafe4）

- [x] 2.1 撤头部「AI 生成正文」按钮（ChapterWorkspace onAiWrite prop 一并退役；右栏生成正文卡同链路＋testid `ai-write-btn`）。验证：DOM 断言 `.col-editor` 无 AI 按钮×3、`ai-write-btn` 可见；modals-pr5/prompt-pipeline 改 testid 后全绿。
- [x] 2.2 撤 OgPane「AI 起草」「剧情推演」按钮与 props（右栏章纲页签动作本就有；testid og-ai-draft/og-simulate 随迁右栏）。验证：outline-ai-draft/plot-sim 全量绿（PRO 流程走右栏不变语义）。
- [x] 2.3 文风「AI 建议本章调整」触发上右栏：AiAssistPanel style 页签新增动作（testid style-suggest-btn、归档禁用）＋ChapterWorkspace suggestSignal 信号通道＋StyleShadowPane 信号驱动（busyRef 挡并发、mountedRef 挡重挂载误触发；结果与采纳留页签）。验证：e2e 探针＝右栏点击→`.ss-suggestion` 呈现；vitest StyleShadowPane 三用例（无信号不拉/手工面/信号触发采纳写影子）。
- [x] 2.4 免费态语义改右栏置灰：outline-ai-draft/plot-sim 免费态断言改 visible+disabled＋标题改写；NovelWorkspace.test PRO 断言改右栏 ai-write-btn。

## 3. 回归（PR #445 合入前全量）

- [x] 3.1 `npx tsc --noEmit` 零错误；`npx vitest run` 674/674；`npm run design:lint` 0 错。
- [x] 3.2 受影响 e2e 组（outline-ai-draft/plot-sim/modals-pr5/prompt-pipeline/ai-assist/ai-write-route）16/16；全量 e2e 162 过/0 挂/14 跳过（docker 栈重建后实测）。
- [x] 3.3 ADJUSTMENTS 登记（条13修订＋⑪-a）随 #444 先行上 main；PR #445 squash＝4d5459a 合入。
