# Tasks: c-kb-entry-detail-fields

## 1. 通用字段段

- [x] 1.1 `payloadRows` 纯函数：字符串/数字直出、数组顿号连、套对象紧凑 JSON、空值（""/null/空数组）跳过、按存储序
- [x] 1.2 详情抽屉「字段」段：键名 mono 原样＋值渲染，段空隐藏

## 2. 测试

- [x] 2.1 payloadRows 平铺两钉（存储序＋空值跳过；null/对象/数组元素套对象/数字）
- [x] 2.2 抽屉渲染钉（迁移卡形 payload 逐键可见/空键不出行/四段照旧）＋退场钉

## 3. 验收与合入

- [x] 3.1 全量 vitest --coverage 绿（含阈值）
- [x] 3.2 openspec validate 绿
- [ ] 3.3 真机验收：知识库点开刘望津，档案格逐键可见
- [ ] 3.4 sync＋归档随实现 PR 走
