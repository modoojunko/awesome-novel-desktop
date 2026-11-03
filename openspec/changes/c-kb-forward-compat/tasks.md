# c-kb-forward-compat · Tasks

## 1. 同步端（C 端）

- [x] 1.1 条目数校验改为「子集容错」：`entries` 非空即落层，`skipped` 计数随结果返回
- [x] 1.2 整包不可识别（`entry_count > 0` 且 0 条可用）→ `failed/entry_count`，保旧层
- [x] 1.3 判据注释钉住语义：判据＝「本端看得懂的边界」，不是「包是否合法」
- [x] 1.4 单测四条：新概念跳条、未知维度跳条、未知顶层字段照收、整包不识别保旧层

## 2. 内容仓口径

- [ ] 2.1 publish 说明补：新增概念/维度不必抬 `min-client`；`format_version` 才是不兼容闸
