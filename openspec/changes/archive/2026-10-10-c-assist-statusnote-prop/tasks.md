## 1. 修复

- [x] 1.1 `AiAssistPanel.tsx`：statusNote 从 children 挪回 props 列表（注释随迁，位置在 `data-od-id` 前）；验证：卡面不再渲染「statusNote=」字面量

## 2. 防回归

- [x] 2.1 `AiAssistPanel.test.tsx` 新增回归 describe 三例：og 页签无字面量／prose＋朱雀关→注记经 prop 上屏／prose＋朱雀开→无注记；验证：修复前前两例必红
- [x] 2.2 测试隔离核对：`setZhuqueShow` 写的 localStorage 在末例复位 true，`beforeEach` 只重置 api mock，与开关无耦合；验证：该文件 13/13 绿
- [x] 2.3 全量类型检查与耦合面扫描；验证：`tsc --noEmit` 零错＋e2e 零引用＋全仓仅此一处 statusNote 用法

## 3. 交付

- [x] 3.1 评审（逐项核查根因考古／prop 契约／回归钉有效性／隔离）结论 No findings；验证：评审记录在案
- [x] 3.2 PR #809 合 main（squash＝b08eded1，CI 绿）
- [x] 3.3 openspec 补档归档（skip_specs 无 sync，纯文档 PR）；验证：archive 目录就位
