# Tasks: c-kb-field-labels

- [x] 1.1 `kbFieldLabels.ts`：通用键→中文标签字典（角色域同源并入）＋概念消歧层
- [x] 1.2 `kbValueLabel`：布尔/枚举值转中文，未知值回退原值
- [x] 1.3 抽屉接入：字段名中文标签渲染；payloadRows 标量值走 kbValueLabel
- [x] 2.1 kbFieldLabels.test.ts（档案/认知/消歧/跨概念/未知键/枚举/布尔/回退）
- [x] 2.2 knowledgeBasePage 抽屉断言改中文＋未收录键回退原键钉
- [x] 2.3 coverage-contract 登记 kbFieldLabels.ts
- [x] 3.1 全量前端 vitest --coverage 绿＋tsc 绿
- [x] 3.2 openspec validate 绿；sync＋归档随 PR
- [ ] 3.3 真机：刘望津抽屉字段全部中文（名字/一句话人设/别名/性别/年龄/剧情定位…）
