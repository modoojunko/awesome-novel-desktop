## 1. 原型先行（drafts ＋ ADJUSTMENTS 登记）

- [x] 1.1 `docs/design-c/drafts/storyline.html` 卷右栏段收窄：`aiVolHTML` 由「四页签统计卡＋动作清单」改为「验证面板随页签」——四键进「当前页签」、引导语随页签、报告三组按页签前置、卷纲页签补「重新规划这一卷（AI）」；验证＝手工点四个卷页签，右栏标题/引导语/组序随之变化，且不再出现统计卡与假动作
  - 证据：新增 `AI_VOL_TAB_NAME`（outline 在卷页签＝卷纲）＋`aiShell(tab,lead,body,tabName)` 可选形参＋`VOL_CHECK` 演示报告＋rp-* 报告类搬入；Playwright 走查实测：卷纲→[对主线→对设定→对已写内容]＋动作[体检这一卷/重新规划这一卷（AI）]、本卷章节→[对已写内容→对主线→对设定]＋仅体检、角色关系/伏笔→[对设定→对主线→对已写内容]＋仅体检，统计卡 `ai-stats` 计数=0，**零 JS 报错**（截图 /tmp/proto-vol-rail.png）
- [x] 1.2 `docs/design-c/drafts/ai-novel-c端-整书拆纲.html`：④写作页默认页补「书主页卡」态（进度眉标＋续写＋＋新增一卷/＋新增一章），落点卡补「＋ 新增一卷」；3 套 `cand` 卡首行补「上接」（两行截断＋`title` 全文）；验证＝页面可点走到该态，卡片区可直接读到上一卷结尾
  - 证据：新增 `homeCardHTML()`＋demo ⑦（`DEMO` 加项＋`setDemo('home')`）；`enterText()` 单源（锚点块与卡片同源）；走查实测：书主页卡文本＝「2 卷 · 3 章 · 已归档 1 章 · 共 4.2 万字 / 接着写第 3 章？/ 续写 · 第 3 章 / ＋ 新增一卷 / ＋ 新增一章」；三张卡 `cand-in` 文本与 `title` 均＝上一卷结尾；落点卡按钮＝3 个（含 ＋ 新增一卷）；零 JS 报错
- [x] 1.3 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记四条＋类名角色口径；注明 book.html 与 parity 基线不动；验证＝登记条目落盘并与 change 名关联
  - 证据：新增章节「三页签回默认主页＋卷页签右栏＋抽卡「上接」（c-write-home-rail-anchor，2026-09-22）」5 条，含「`.be-k` 眉标/`.be-t` 主句 与原型 `.be-mark` 不同名不同层——不为新卡引入未登记类」
- [x] 1.4 原型门禁；验证＝输出结论追加在本条
  - 证据：`docs/design-c` 无独立 npm 工程 → 以 `client/frontend npm run design:lint` 为准：exit 0（严格扫描 32 文件，无严格范围违规；存量统计不阻断）

## 2. 三页签回默认主页（写作／设定／预览）

- [x] 2.1 回主页语义落成 `goTab`（三守卫＋三分支）；五个入口改走它
  - 证据：`NovelWorkspace.tsx` 删旧 `go()`、新增 `goTab()`（离开设定脏确认／已在设定拨回默认面板／进预览落首章／写作清选中＋卷纲脏＋流式中双守卫）；modnav 三按钮＋`SettingsView onGoWrite`＋`PreviewView onGoWrite`＋`ProPhaseSurface onGoSettings`＋规划台 `onGoSettings` 全改走它；vitest 新增三条用例全绿
- [x] 2.2 中栏默认页第三态换成书主页卡＋落点卡补「＋ 新增一卷」
  - 证据：`data-testid=write-home`（`home-progress` 进度眉标／`home-resume` 续写／`home-add-volume`／`home-add-chapter`／选章引导句）；「＋ 新增一章」走新增的 `addChapterAtEnd()`（末卷下一章号，零卷回落先垫卷）；vitest 四态（空书／未排章／删空／有章）＋e2e 新用例（1 卷 1 章 → 删空后 0 章仍见主页卡）
- [x] 2.3 顶栏「续写」与主页卡「续写」同文案同行为
  - 证据：抽出 `resumeTitle` 单源，顶栏与主页卡 `title` 同源同判据；e2e「页签回默认主页」用例点主页卡续写回到该章（章纲页签）
- [x] 2.4 `book.css` 书主页卡样式（复用既有类，不新增类族）
  - 证据：`git diff src/design/book.css` 仅 +2 行（`.cand-line.cand-in` 两行截断），书主页卡零新增 CSS（复用 `.e-empty/.be-k/.be-t/.be-desc/.be-acts`）；`npx tsc --noEmit` 0 error
- [x] 2.5 设定回默认面板（`settingsHomeSeq` ＋ `SettingsView` effect）
  - 证据：`SettingsView` 新增可选 `homeSeq`，值变化→`setPanel(normalizePanel(undefined))`（回执由既有 `[panel]` effect 清）；脏表单由壳层先确认；vitest「重复点『设定』把面板拨回默认项（简介）」绿
- [x] 2.6 预览定档首章（`previewHomeSeq` ＋ 下线 `initialRef` 继承）
  - 证据：`PreviewView` 删 `initialRef` prop 与回落分支（孤儿清理），改 `homeSeq`；vitest 改写为「定档＝首章：不继承写作页当前章」；e2e 在 workbench-features 预览用例内断言「回写作落主页卡 ＋ 续写回首章」

## 3. 右栏随卷页签（卷选中态验证面板）

- [x] 3.1 卷模式把 `volumeData.tab` 透给 `VolumeAssistPanel`
  - 证据：数据本就在 `VolumeRailData.tab` 且 `Rail` 已传 `data={volumeData}` → **无需改 Rail.tsx**；`VolumeVerifyPanel` 直接读 `data.tab`
- [x] 3.2 四页签：当前页签名／引导语／组序（未体检不预置空报告）
  - 证据：新增 `VOL_TAB_NAME/VOL_TAB_LEAD/VOL_TAB_ORDER`＋`groups` 重排（顺序表外组名按原序追加，不丢结论）；vitest 参数化 4 页签×组序＋入口有无＋「未体检只给引导语与动作」共 5 例；e2e volume-plan ⑨ 用真实 CHECK_REPORT 断言「对主线」打头 ↔ 切本卷章节后「对已写内容」打头
- [x] 3.3 卷纲页签补「重新规划这一卷（AI）」（`volume-replan`）
  - 证据：点击 `onPlanVolume(data.volume)`；vitest 断言回调参数=本卷号；e2e workbench-features / volume-plan 断言该入口只在卷纲页签在场（其余页签 `toHaveCount(0)`）
- [x] 3.4 采纳回填口径回归（对已有卷不建卷）
  - 证据：既有 e2e「手点『回填』只发一次建卷请求」＋「规划全链」在本轮全量里绿；`startBackfill` 对已存在 `vol-N` 只 `focusNode` 未改

## 4. 抽卡卡片「上接」

- [x] 4.1 每张 `cand` 卡在走向前插「上接」行（取数复用 `useAnchor`）
  - 证据：`data-testid=plan-card-{n}-enter`，`<b>{first?"起点":"上接"}</b><span title={anchor.text}>`；vitest 断言三张卡文本＝锚点块文本且 `title`＝全文；e2e volume-plan ③b 同断言（首卷＝起点）
- [x] 4.2 `.cand-in` 两行截断（全文挂 `title`）
  - 证据：`book.css` +2 行（`-webkit-line-clamp:2`）；e2e 断言 `title`＝全文（截断只在视觉层）
- [x] 4.3 后端零改动确认
  - 证据：`git diff --stat` 无 `client/backend/**`；后端 pytest 见 7.3 条

## 5. 测试补齐（vitest）

- [x] 5.1 `NovelWorkspace.test.tsx`：点写作回默认页／书主页卡／重复点回主页／设定拨回默认
  - 证据：新增 3 例＋改写 1 例（原「切设定再返回 prose 不丢」改为「切设定编辑器仍挂载」＋新契约）；该文件 12 passed
- [x] 5.2 `volumePlan.test.tsx`＋`previewReader.test.tsx` 补齐
  - 证据：volumePlan 16→25 passed（卷页签 4＋未体检 1＋卡片上接 1＝+9）；previewReader 6 passed（改写 1 例）；**全量 `npx vitest run`：76 文件 / 723 passed / 0 failed**

## 6. e2e 审计与更新

- [x] 6.1 逐处审计「点 `.mtab 写作`」的既有用例；验证＝审计清单追加
  - 证据：全仓 24 处（`.mtab 写作` 19 ＋ `getByRole(/^写作/)` 5）。**需改 5 处**：`settings-forms:735`（原依赖「点写作后原章仍选中」→ 改为「落主页卡 → 点回首章 → 切正文页签」）、`workbench-features:803`（回写作改断主页卡＋续写回首章）、`design-parity-preview:12/104` 与 `settings-forms:710/757` 注释改「定档＝首章」。其余 19 处是「建书后切写作」或「点写作后自己点章」，不受影响；另有 `workbench-features:243` 因本轮插入的页签断言顺序需把「回卷纲」断言移到台账断言之后，已修
- [x] 6.2 `volume-plan.spec.ts` 补卡片「上接」＋卷页签右栏跟随断言；验证＝通过
  - 证据：③b「每张卡自带上接（同源、首卷＝起点）」＋⑨「组序随页签 ＋ 卷纲页签有重新规划入口/其余页签没有」；该 spec 3 passed
- [x] 6.3 `workbench-features.spec.ts` 补：点写作落书主页卡（含建书入口）、删空最后一章后仍见书主页卡；验证＝通过
  - 证据：新增用例「页签回默认主页：点『写作』落书主页卡（建书入口在场），删空后仍是主页卡」passed（含重复点回主页、续写回章、API 删空后仍见主页卡「0 章」）
- [x] 6.4 落点回归：`landing-view.spec.ts` / `works-finish-flow.spec.ts` 按「打开书落点不变」口径核对；验证＝通过
  - 证据：两条 spec 在本轮全量 e2e 中全绿（未改一行）

## 7. 回归（门禁实际输出）

- [x] 7.1 不触共享段判定复核；验证＝`git diff --stat` 中无 `base.css`／`server/` 文件
  - 证据：改动 16 文件＝`client/frontend/src/**`（7）＋`client/frontend/e2e/**`（4）＋`docs/design-c/**`（3）＋ `openspec/changes/c-write-home-rail-anchor/**`；无 `base.css`、无 `server/**` → 免 `design:cross`
- [x] 7.2 设计门禁；验证＝两条命令输出结论
  - 证据：`npm run design:lint` exit 0；`npm run design:check`（lint＋parity）**8 passed**。另跑 `DESIGN_PARITY=1 e2e/design-parity-book.spec.ts`：4 failed（free·workbench 4.501%、modal-delete 2.642%、modal-prefs 2.558%、modal-upgrade 2.559%）——**主栈同条同值**（5174 同 spec 实测 2.558/2.559/2.642/4.501，逐位相同）→ 存量基线漂移，本 change 零新增像素差
- [x] 7.3 类型与单测；验证＝输出结论
  - 证据：`npx tsc --noEmit` 0 error；`npx vitest run` 76 文件 723 passed；后端 **1258 passed**（`client/backend` 用主检出 venv 解释器跑 pytest——运行镜像不含 pytest；代码取本 worktree，后端零 diff，跑一遍确认无连带）
- [x] 7.4 本机隔离栈全量 e2e；验证＝全量通过结论
  - 证据：隔离栈（worktree `docker-compose.override.yml`：container_name=hra-*、5274/8100、独立 `.docker-data`；容器内抓特征串 `write-home`/`volume-replan`/`plan-card-` 自证是我这版构建）第二轮**全量 171 passed / 0 failed / 17 skipped（8.2min）**，存量红项 0

## 8. 过程中发现的存量问题（非本 change，登记备查）

- [x] 8.1 `volume-plan.spec.ts` 会话注入缺 `username`：C端 `get_current_user` 要求 `config.json` 有登录用户名，该 spec 只写 token/tier/expires_at，干净库（`{}` 播种）下书架恒 401「未获取到登录用户」；本机因共享 `.docker-data` 残留旧 username 才假绿（CI 的 `echo '{}' > config.json` 播种会真撞）。已按其余 10+ 份 spec 同款补 `cfg.username = u`（本文件内 1 行）
- [x] 8.2 新装库题材候选词汇为空（**归档复核：已由 main 修复，无需立项**）：当时量的基线是 `dfceb17d`，
  彼时 `ensure_seed_genre_vocab()` 无调用点；现在 `origin/main` 的 `client/backend/main.py` 启动期会调它
  （`main.py:108-110`），全新库的候选词汇不再为空。本轮验证时的「空词汇」现象来自**运行中的旧容器**
  （镜像早于该修复）＋ 外部补种后未重启进程

## 9. 评审修复（review-agent 四条 findings，2026-09-22）

- [x] 9.1 [P2] 组序重排改逐实例消费＋组名前缀归一：`normGroupKey`（对主线/对设定/对已写内容 前缀命中，变体「对主线（…）」也参与重排）；splice 逐组消费，重名/顺序表外的组按模型原序跟在尾——**一组都不丢**（旧实现按名字建 Map 会吞重名组）；渲染 key 改 `名#序` 防重名撞 key；验证＝vitest 新增「组名变体按前缀归一仍重排；重名组一组都不吞」
- [x] 9.2 [P3] 「待写」端点占位不再当章名拼进问句：书主页卡「接着写第 N 章？待写」→「接着写第 N 章？」；顶栏 `hereBar` 同款拼法一并修（`bh-tag` 徽已表达状态，避免「第 3 章待写 待写」）；验证＝vitest 全绿（free-writing-flow:305 只断言 `.bh-t` 含「第 2 章」与 `.bh-tag`，不受影响）
- [x] 9.3 [P3] 三条「回默认」守卫补测试：设定脏同页确认（vitest：取消留原面板输入保留／确认拨回简介）、AI 流式中确认（vitest：`@/lib/ai` 的 `streamChapterWrite` 桩成挂起的 AbortController → streaming 稳定 true，取消留原章）、卷纲脏（e2e：dismiss 留编辑态输入保留 / accept 回默认页）；验证＝NovelWorkspace.test 15 passed、workbench-features 守卫用例 passed
- [x] 9.4 [P3] 过期契约注释同步：NovelWorkspace.test 头与 describe 名、previewReader.test 头与 89 行注释（initialRef → 定档首章）、VolumeAssistPanel 头（补随页签与重新规划入口）；验证＝grep 无「initialRef 回退链 / 正文脏状态切视图不丢」残留
- [x] 9.5 评审测试缺口：新增 e2e「重新规划这一卷：已有卷采纳回填不新建卷」（expand 桩 + 建卷 POST 计数=0 + 树仍 1 卷 + 表单逐段落进来）；验证＝volume-plan.spec 4 passed
- [x] 9.6 修复后门禁复跑：`npx tsc --noEmit` 0 error；`npx vitest run` 76 文件 **726 passed**；design:lint exit 0；隔离栈全量 e2e 第三轮 **173 passed / 0 failed / 17 skipped（8.3min）**

## 10. 基线换基重做（2026-09-22，c-volume-antagonist #458 合入之后）

首版分支切自 `dfceb17d`（#458 之前）；#458 重写了规划台（`VolumePlanModal` 586 行变更＋新增
`PickCardsModal`）并把建卷统一为规划流。**直接合入会把弹窗改回旧版**（用户 2026-09-22 指出）。
本轮把三件事重新落 origin/main：

- [x] 10.1 分支重置到 `origin/main`（9c341783），我的三件事按新代码重贴；main 未触及的文件
  （`SettingsView`/`PreviewView`/`previewReader.test`/`settings-forms.spec`/`design-parity-preview.spec`）整份取回
- [x] 10.2 `NovelWorkspace`：`goTab`/`settingsHomeSeq`/`previewHomeSeq`/`resumeTitle`/`archivedTotal`/
  `addChapterAtEnd`/书主页卡（`write-home`）/落点卡「＋ 新增一卷」全部重贴；建卷入口统一走
  `openPlanVolume(nextVolNo)`（付费抽卡／免费四问，**不复活添加卷弹窗**）；顶栏与主页卡的「待写」占位不拼章名
- [x] 10.3 `VolumeAssistPanel`：卷页签跟随（`VOL_TAB_NAME/LEAD/ORDER`＋`normGroupKey` 前缀归一＋逐实例
  splice 消费）重贴，并保留 main 的 `nextVolNo` 单源改动
- [x] 10.4 卡片「上接」改落 `PickCardsModal`：新增 `projectId` 透传＋组件内 `useAnchor`（plan-anchor 单源）
  ＋每张 `.pick-card` 卡首 `.pk-row.pk-in`（testid `pick-enter-{n}`，避开既有 `pick-card-` 正则）；
  `book.css` 加两行截断
- [x] 10.5 测试重贴：`NovelWorkspace.test` 三条新用例＋流式桩；`volumePlan.test` 卷页签右栏 6 例＋
  抽卡「上接」1 例；e2e：`volume-plan` 付费链加「上接」断言＋新增「卷页签右栏跟随与重新规划不新建卷」；
  `workbench-features` 右栏断言改「随页签」＋新增书主页卡与卷纲脏守卫两例；预览阅读器用例改「回写作走主页卡＋续写」
- [x] 10.6 spec 增量按 main 现文本重抄：`workbench` 的 N4 块（含新场景「新增一卷按档分流」与规划流口径）
  与右栏块（含卷页签跟随/重新规划两张新场景）；`volume-plan-ai` 收敛为「新增需求＝抽卡卡片自带进场」
  ＋体检块补页签重排与重新规划入口
- [x] 10.7 门禁（换基后）：`npx tsc --noEmit` 0 error；`npx vitest run` **77 文件 / 751 passed**；
  `openspec validate --strict` 绿；隔离栈（重建镜像，容器内抓 `pick-enter-`/`write-home`/`volume-replan`
  特征串自证）聚焦 e2e volume-plan＋workbench-features **19 passed**；全量 e2e 见 10.8
- [x] 10.8 全量 e2e（换基后）：隔离栈 **174 passed / 0 failed / 17 skipped（8.4min）**（含换基后新增的
  6 条用例）；`settings-forms` 首轮曾因我把该文件整份取回旧版（#458 已改过它）而红——已改为「保留 main 版＋
  我的 3 处最小改动」，复跑绿

## 11. 入口分叉（用户 2026-09-22 追加口径）

口径：**加号（各处「＋ 新增一卷」／树头「＋」）＝手动建卷 → 恒进四问手写页，让作家填空（不分档位）**；
三选一抽卡只从右栏「规划第N卷（AI）」进（该入口仍按档分流：付费＝抽卡、免费＝四问页）。

- [x] 11.1 `useVolumePlan.open(volNo, isPro, mode)` 增 mode（默认 "ai"）：`mode==="manual"` 恒 `deskOpen`；
      仅 AI 入口且付费才 `pickOpen`＋`drawCards`
- [x] 11.2 `NovelWorkspace` 拆两条入口：`openPlanVolumeManual`（5 处加号＋树头走它）与
      `openPlanVolume`（右栏 `onPlanVolume` 保持 AI 语义）；埋点仍记 `plan_entry_open{tier}`（口径不变）
- [x] 11.3 测试：vitest 新增「PRO 档加号＝四问页（不弹抽卡）＋抽卡只从右栏进」与 hook 级
      「open(mode)：manual 恒四问页／ai 按档」；`creation-flow.spec` 两处加号断言改四问页（原先钉的是旧口径）
- [x] 11.4 spec 增量改口径：workbench 的 N4 建卷 bullet＋场景「新增一卷按档分流」（改为「加号＝手填页；
      按档分流只发生在右栏 AI 入口」）＋我 ADDED 需求同款 bullet＋**新增 书内顶栏 的 MODIFIED 块**
      （bar-here 空书卡按钮口径）；volume-plan-ai 的「两条并行入口」补手动入口恒进手写页
- [x] 11.5 原型与登记：拆纲稿 `openPlan(n, manual)`（`manual-vol` 传 true）＋ ADJUSTMENTS 第 7 条
- [x] 11.6 门禁：tsc 0 error；vitest **77 文件 / 753 passed**；`openspec validate --strict` 绿；
      隔离栈（重建镜像）聚焦 e2e creation-flow＋volume-plan＋workbench-features **25 passed**；
      全量 e2e 见 11.7
- [x] 11.7 全量 e2e（换基后第二轮）：隔离栈 **174 passed / 0 failed / 17 skipped（8.4min）**

## 12. 手动入口的手写页撤 AI 动作（用户 2026-09-22 追加）

口径：加号打开的四问手写页是**纯手动页**，SHALL NOT 出现「让 AI 铺完剩下的问题」；四问提示文案也不承诺
「答不出的交给 AI」，改为一句指向右栏 AI 入口的说明。右栏 AI 入口打开的手写页（免费档）**保留**铺空缺
按钮与 PRO 说明（AI 链路的唯一可达页）。

- [x] 12.1 `useVolumePlan.state.openMode`（`open()` 落）＋ `VolumePlanModal` 的 `manual` 分支：
      手动入口下撤 `desk-expand`＋其说明，lead 改「答不出的可以空着」、Q1 注改「可空」，
      push 区改「想让 AI 铺空缺：用右侧 AI 助手的「规划第N卷（AI）」」
- [x] 12.2 测试：vitest 新增「手动入口：手写页不出现 AI 动作，只留直接创建＋指向右栏的说明」
      （含「不再承诺交给 AI」断言）；`creation-flow.spec` 树头加号用例补 `desk-expand` 计数 0 断言
- [x] 12.3 spec：workbench 的 N4 建卷 bullet 补「该页 SHALL NOT 出现任何 AI 动作＋须给右栏指引」；
      volume-plan-ai 的「两条并行入口」手动入口 bullet 同款
- [x] 12.4 原型与登记：拆纲稿 `state.manual` ＋ desk 动作条件渲染；ADJUSTMENTS 第 8 条
- [x] 12.5 门禁：tsc 0 error；vitest **77 文件 / 754 passed**；`openspec validate --strict` 绿；
      隔离栈（重建镜像）聚焦 e2e creation-flow＋volume-plan **11 passed**（含加号页无 AI 动作断言）
- [x] 12.6 全量 e2e：隔离栈 **174 passed / 0 failed / 17 skipped（8.5min）**

## 13. 归档（2026-09-22）

- [x] 13.1 增量同步进主 spec：`workbench`（新增「页签回默认主页（写作／设定／预览）」；改 N4／右栏「AI 辅助」／书内顶栏
      三块）、`preview-reader`（新增「预览定档＝全书首章」）、`volume-plan-ai`（新增「抽卡卡片自带进场（上接）」；
      改「两条并行入口」／「卷纲体检（卷级验证）」）；`openspec validate --specs` **60 passed / 0 failed**
- [x] 13.2 归档操作口径核对：本次未新增令牌/档位/语气词，`pk-in` 只是 book.css 业务层的截断修饰类
      （`design:lint` 严格范围通过）→ 无需回填 `design-vocab.mjs`；未用 uikit 候选组件；
      未更名/新增共享类（未触 `base.css`／`server/`）→ 免 `cross-end` 回填；Capability 不属 `design-system`
- [x] 13.3 change 目录移入 `openspec/changes/archive/2026-09-22-c-write-home-rail-anchor/`
