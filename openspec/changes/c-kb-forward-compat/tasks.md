# c-kb-forward-compat · Tasks

## 1. 同步端（C 端）

- [x] 1.1 条目数校验改为「子集容错」：`entries` 非空即落层，`skipped` 计数随结果返回
- [x] 1.2 整包不可识别（`entry_count > 0` 且 0 条可用）→ `failed/entry_count`，保旧层
- [x] 1.3 判据注释钉住语义：判据＝「本端看得懂的边界」，不是「包是否合法」
- [x] 1.4 单测四条：新概念跳条、未知维度跳条、未知顶层字段照收、整包不识别保旧层
- [x] 1.5 格式代随客户端版本走：`FORMAT_CLIENT="0.45.0"`＋`_FORMAT_INT_BY_CLIENT` 映射，
      manifest 双写 `format_client`（真身）＋`format_version`（老读法）；未登记代际静默跳过
      （单测：已登记照收、更新代际跳过、client 优先于整数）
- [x] 1.6 评审补修（三条）：
  - 「读不懂」≠「下架」：包内仍发布但不入闸的条目沿用旧层原文（`carried`），
    不缩水、不触发副本误提升；只有整包无该 src_key 才算移除
  - 可见性：`skipped>0` 记 warning；`kb_baseline_last_sync` 摘要随 `/baseline/status` 透出
  - 两仓 `format_client` 清单 parity 钉（内容仓在本机时对拍，单边登记即红）
  - 发布闸补：manifest 缺 `format_client` 拒绝发布（否则会被当第一代照收）

## 2. 内容仓口径

- [x] 2.1 publish/build 说明补：新增概念/维度不必抬 `min-client`；格式代用 `--format-client`
      声明（默认 `0.45.0`），未登记代际拒绝构建
- [ ] 2.2 下一次发版把 README 的「格式代=客户端版本」映射表随新代际更新（0.50.0 等）
