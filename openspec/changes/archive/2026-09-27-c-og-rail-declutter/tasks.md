## 1. 右栏章纲页签统计卡退役＋头部徽章行（补录：实现已于 PR #506 落地）

- [x] 1.1 `AiAssistPanel.tsx`：og 页签撤 `raStats` 四项统计卡，保留引导语＋「还缺」＋动作清单＋AI 帮写剧情；`OgStats` 接口注释逐字段标明消费方（reqOk→操作页签、planWords→正文页签、plotCount/castCount 随通道保留）。完成证据＝PR #506 diff＋`AiAssistPanel.test.tsx` og 用例断言 `.rail-stats` 为 null
- [x] 1.2 `ChapterWorkspace.tsx`：e-head 徽章行扩为六枚（状态/字数/归档门槛 N/2/计划字数/剧情 N 条/出场角色 N 人），口径与 `onRailData` 上抛一致（ogGaps 分母派生、wt→targetWords 兜底）；`onRailData` effect 一行不动（render-loop 规避，design D1）。完成证据＝`chapterWorkspace.plotFlow.test.tsx` 新增头部 meta 行用例（归档门槛 2/2、剧情 2 条、出场角色 0 人断言）通过
- [x] 1.3 头部字号/行距 seg 退役＋`typo` 单一 state 只读回显（prefs 数据层不动，改值入口在账号菜单「本书偏好」）。完成证据＝同用例断言 `.e-head .seg` 为 null；vitest 871 全绿

## 2. 版本历史/归档迁位

- [x] 2.1 版本历史移页签条右端（`.ch-history`＋`book.css` 两条对齐规则；`HistoryModal` 弹窗不变）。完成证据＝plotFlow 用例断言 `.ch-tabs .ch-history` 存在且 `.e-head .ch-history` 为 null；`modals-pr5` 版本历史弹窗用例照常通过
- [x] 2.2 归档移「操作」页签首卡（`data-od-id=archive-card`/`archive-btn`；守卫不变；`!ghostOf` 与重写/回退卡拉齐，design D4）。完成证据＝`chapter-rewrite`/`settings-forms`/`free-writing-flow`/`modals-pr5` 四文件归档链路 e2e 全绿
- [x] 2.3 工作台双截图目检（章纲页签：头部六徽章＋页签行右端版本历史＋右栏无统计卡；操作页签：归档卡置灰态）。完成证据＝`/tmp/ograil-og.png`、`/tmp/ograil-actions.png`（隔离栈实拍，已随 PR 描述归档）

## 3. e2e 适配与门禁

- [x] 3.1 四处按名字点「归档本章」的用例加「点操作页签」一步（settings-forms/free-writing-flow/chapter-rewrite/modals-pr5）。完成证据＝隔离栈四文件 27 条 e2e 全绿
- [x] 3.2 四处 `S_API` 硬编码改吃 `E2E_S_API`（不设 env 回落原默认，CI nightly 兼容；design D6）。完成证据＝同批 e2e 以 `E2E_S_API=http://localhost:19600/api/web` 注入通过
- [x] 3.3 门禁全绿：tsc、vitest 871、`npm run build`、design:lint。完成证据＝PR #506 checks 描述＋本地门禁记录
- [x] 3.4 `ADJUSTMENTS.md` 登记原型偏差（章纲统计上移/seg 退役/版本历史与归档迁位/parity 基线待重录）。完成证据＝PR #506 内 ADJUSTMENTS diff

## 4. 收尾

- [x] 4.1 PR #506 合入 main（squash=98f4cff8；CodeQL/打包在 main 连续多日秒挂为基建层故障，前端真门禁本地全绿后按先例 admin 合并）。完成证据＝mergeCommit 98f4cff8
- [x] 4.2 归档本 change（本 PR）：specs delta 同步 `workbench` 主 spec 后移入 `archive/2026-09-27-c-og-rail-declutter`
