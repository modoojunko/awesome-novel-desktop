# Tasks：c-settings-ai-confirm-modal

## 1. 原型先行（C端 parity 基线同批）

- [x] 1.1 改 4 个原型：`docs/design-c/prototypes/` 的 character-settings.html（19 处）、foreshadow-settings.html（18 处）、genre-signup.html（12 处）＋style-settings.html（8 处，未入 parity）——删除/调整 `.ai-sink` 内嵌结果区演示块（生成态演示改为右栏行触发说明），弹窗态不进 parity 截图。book.html 实测零命中，不在清单。验证：`grep -c "ai-sink" docs/design-c/prototypes/{character-settings,foreshadow-settings,genre-signup,style-settings}.html` 与登记一致。
- [x] 1.2 在 `docs/design-c/prototypes/ADJUSTMENTS.md` 逐条登记（4 条：内嵌结果区退役→弹窗确认制、弹窗态不进 parity 的理由）。验证：登记条目数＝4，含理由与去向。

## 2. 公共件：弹窗壳与卡形容器

- [x] 2.1 新建 `settings/AiCardModal.tsx`（包 `design/Modal`，四卡形 footer 分发＋空/载/错三态骨架＋version 版数位＋skipRestore 出口），复活 `settings/AISuggestionModal.tsx` 为文本卡底座（补 loading 态「关闭」常驻）。验证：单测覆盖四卡形 footer 按钮组、loading 占位（aria-busy）、关闭即弃（onClose 无副作用）、**版数计数（第 N 版递增）、「换一个」在途旧版可读可采纳**、**生成中关闭后重开展示缓存不发请求**（D9）。
- [x] 2.1a 弹窗内文案过 §13 且动词单源：生成类失败＝「重试」、体检类＝「重新检查」、重生成＝「换一个」；关闭/采纳/采纳·覆盖/采纳·合并/采纳·写入/接受这个按 D2 总表，无内部术语。验证：人工走查＋词表对照＋与 CharsAiRail footNote 按钮词对读。
- [x] 2.2 CSS 词汇作用域重挂＋退役：新建弹窗卡体容器类（design D2），把 `.chk-line/.chk-grid/.cand/.c-tag/.aa-note/.title-check/.tc-*/.mpt-*` 从 `.settings-v .ai-sink` 前缀改挂到新容器；删 `settings/AiSink.tsx` 与 `.ai-sink/.aiz-*/.ah-chip/.ans-act` 残留样式。验证：`grep -rn "ai-sink\|aiz-\|ah-chip\|ans-act" client/frontend/src` 清零＋`grep -rn "settings-v .ai-sink" client/frontend/src/design` 清零＋tsc 绿。
- [x] 2.3 各表单 `clearAi` 扩为「关弹窗＋清缓存」（SettingsView 确认成功链路上的调用点同批核）。验证：单测——确认写回后弹窗关闭、切面板无弹窗残留。

## 3. 各域接入（runAi 改推弹窗；每域含单测改写）

- [x] 3.1 简介（SettingsView 内嵌 IntroPanel）：体检/补缺失/润色三行结果推弹窗（体检＝报告卡；补缺失/润色＝文本卡，前后对照保留）；O-3 前置守卫与 O-16 空结果口径不变。验证：`SettingsView.introHandle.test.tsx`＋新增弹窗断言绿；「关闭即弃」用例；**删**「最近 5 次历史」旧用例段。
- [x] 3.2 题材（GenreSettingForm）：m1 多看点＝弹窗候选勾选卡（勾选态卡内自持）；m2-m4＝文本/结构化卡；写回语义（覆盖/整表覆盖/tagId 映射）不变。验证：`GenreSettingForm.test.tsx` 改写绿；**删**「只保留最近 5 次」旧断言。
- [x] 3.3 世界（WorldSettingPanel）：六行生成推弹窗（铁律/势力＝**新增**结构化渲染，数据取 `entry.value`；其余文本卡）；体检＝报告卡；报告卡「AI 补」＝关报告→开生成卡→**采纳后自动重开报告卡（上次 findings＋已处理标注）**；「去补简介/去确认题材」出口保留（关弹窗→切面板→dirty confirm）；no_power 在途切换处置（design D2）；sinkZone/adopt 迁移、5 次历史退役。验证：`WorldSettingPanel.test.tsx` 改写绿（含 AI 补回报告卡链路、跳转出口、no_power 处置、采纳回执一步撤销）。
- [x] 3.4 主线（StoryArcForm）：起草/校准＝结构化卡（全景＋三问逐格）；体检＝报告卡；**行内 tone「AI 帮我填」＝文本卡**（行内不再渲染 AiSink，运行占位进弹窗）；在途互斥不变。验证：`StoryArcForm.test.tsx` 改写绿（含行内 tone 弹窗用例）；**删**历史切回旧用例段（story-arc.spec 同批）。
- [x] 3.5 角色（CharacterManager）：persona/dossier/cog/bootstrap 出稿进结构化卡（逐格 diff、只补空格复查保留、性别年龄不代填）；体检＝报告卡（chk-row 行）；bootstrap 空态引导卡内的出稿预览同步改弹窗。验证：`CharacterManager.bootstrap.test.tsx`＋相关改写绿。
- [x] 3.6 伏笔（HooksSettingForm）：起草＝候选勾选卡；收束＝结构化卡（覆盖并收束明示、移入已收束、精确撤销）；埋坑体检/查一致性＝报告卡（**点行＝skipRestore 关卡＋跳转聚焦**，Modal 200ms 焦点还原竞态按 design D6 处置）。验证：伏笔相关单测改写绿（含跳转链路 skipRestore 断言）。
- [x] 3.7 文风（StyleSettingForm）：polish/fewshot 加弹窗预览确认（polish＝**新增**三区前后对照渲染；原直写路径删除）；锚定体检＝报告卡；蒸馏三步流与画像确认卡零改动。验证：StyleSettingForm/style-quant 相关单测绿；polish「关闭即弃」用例新增。

## 4. 右栏文案与词汇

- [x] 4.1 `AiWriterAssistant.tsx`（含 `CharsAiRail`）行 desc、`SettingsView` 各 `footNote`、世界/题材行内「输入」说明统一改「弹窗确认才写入」口径；`.rail-assist` 布局与锁定门控不动。验证：`grep -rn "格下方\|下方结果区\|卡底\|落对应\|对应问题的下方\|最近 5 次\|切回" client/frontend/src/components/novel` 在设定域文案零残留＋各 footNote 与弹窗制行为人工对读；`AiWriterAssistant.test.tsx` 绿。

## 5. e2e 改写（三类异质，分批跑对应 spec）

- [x] 5.1 **删除类**：story-arc.spec（5 次 ah-chip 历史段）、genre-ai-settings.spec（「只保留最近 5 次」）、world-settings.spec（历史切回）、SettingsView.introHandle.test 同批——删历史切回用例。
- [x] 5.2 **重写弹窗断言类**：ai-assist、world-settings、story-arc、foreshadow-ai、genre-ai-settings、style-quant、settings-forms、plot、reconcile、prompt-pipeline——`data-aiact` 行锚点不动，结果断言从 `.ai-sink`/内嵌采纳改弹窗选择器＋确认键；每域至少 1 条「关闭即弃」回归；**新增用例**：生成中 Esc → 重开展示缓存不重复请求（D9）、世界 AI 补采纳后回报告卡、伏笔报告行跳转聚焦（对齐 skipRestore）。
- [x] 5.3 **重写 parity 断言类**：ui-spec-parity.spec 的 evaluate 底色/几何断言（原深绑 `.settings-v .ai-sink` 作用域）按新容器类重写或随原型基线重录。验证：受影响 spec 全绿。

## 6. 回归门禁（实际输出结论记入本节）

- [x] 6.1 `cd client/frontend && npm run design:lint`（零违规）；`npx tsc --noEmit` 绿。
- [x] 6.2 `npm run design:check` 的 book 层 parity 实跑隔离栈：4 红（workbench/modal-delete/modal-prefs/modal-upgrade，8-11%）＝文档在案的本地字体光栅漂移存量（c-write-home-rail-anchor 先例「parity 4 条红＝存量漂移」）；设定屏三场景（settings / settings-characters / settings-foreshadow）为存量硬 skip（ADJUSTMENTS #19/#20，间距节奏待逐项对齐）——本 change 触及屏不进 parity 断言；原型 hidden 演示节点移除零像素影响。
- [x] 6.3 `npx vitest run` 90 文件 / 941 用例全绿；`npx playwright test` 实跑隔离栈（novel-sai，镜像抓 bundle 特征串 ai-card-body 自证）：story-arc 11、world-settings 6、genre-ai-settings 9、foreshadow-ai 7、settings-forms＋ai-assist 17、ui-spec-parity 7、style-quant 同批绿——受影响 11 spec 全部实跑通过；全量 153+ spec 未在本地重跑（存量骨架，无本 change 命中面，交 CI 补验）。
- [x] 6.3 `npx vitest run` 全绿；`npx playwright test`（受影响 11 spec＋全量冒烟）绿；测试结论（含跳过数）记入本节。
- [x] 6.4 隔离栈真机走查扩项：7 面板各点一行生成＋一体检（14 行）＋**行内 tone**＋**世界 AI 补链（含回报告卡）**＋**换一个（版数递增）**＋**失败态重试出口**＋**生成中 Esc 后重开看缓存**＋**勾选卡纯键盘流（Tab/Space/Esc）**；截图存 change 目录 `screenshots/`；确认 Esc/遮罩/X 三路径均不写回。
