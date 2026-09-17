# Tasks

## 1. A 组：伏笔页签＋设定投影

- [x] 1.1 `HooksPane.tsx`：台账投影（编号/描述/埋点章/状态、本章高亮、汇总行、空态引导）——验证：`storylineHooksAndLore.test.tsx`「本章埋下与回收条目高亮」绿
- [x] 1.2 `ChapterWorkspace`：页签 7→8（角色关系后插「伏笔」，全档位）——验证：`NovelWorkspace.test.tsx` 免费态 7 页签断言更新并通过
- [x] 1.3 `SettingsChangelogPane`：截至本章投影并入 world history/factions/extra（origin 章过滤，开书恒显）——验证：`storylineHooksAndLore.test.tsx`「未来章条目排除」绿
- [x] 1.4 e2e：伏笔页签空态与投影渲染——验证：`workbench-features.spec.ts` ⑩ 通过

## 2. B 组：右栏 AI 辅助面板

- [x] 2.1 `AiAssistPanel.tsx`：八页签引导语＋统计卡＋动作清单；未实现动作＝禁用＋「规划中」占位——验证：`AiAssistPanel.test.tsx` 章纲/正文/提示词/伏笔四例绿
- [x] 2.2 已实现动作接线：章纲（AI 起草/剧情推演经 railData 回调）；正文工具卡收窄到正文页签——验证：同测试「已实现动作真按钮」与 e2e ⑨
- [x] 2.3 统计懒取与静默降级（prompt-sources/baseline/graph/hooks/world；失败显示「—」）——验证：`AiAssistPanel.test.tsx`「懒加载仅在激活页签」绿
- [x] 2.4 `Rail`/`ChapterWorkspace` 数据管道（tab/ogStats/回调进 railData；projectId 透传）——验证：`tsc` 零错误＋e2e ⑨「面板随页签切换」通过
- [x] 2.5 样式（`.rail-assist/.rail-stats/.rail-acts/.hp-*`）＋design:lint 通过——验证：`npm run design:lint` 无新增阻断

## 3. 回归与归档

- [x] 3.1 vitest 全量（334→342）＋tsc＋design:lint——验证：本机执行全绿
- [x] 3.2 e2e 全量（含新增两例）——验证：本机 docker 栈执行
- [x] 3.3 ADJUSTMENTS #27 增补 ⑦伏笔页签 ⑧右栏 AI 辅助面板（含占位口径）；openspec 本变更归档 sync——验证：`openspec validate workbench-storyline-panels --strict` 与归档输出
