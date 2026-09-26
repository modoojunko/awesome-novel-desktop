## ADDED Requirements

### Requirement: 剧情条目列（plot_items）

- `chapters` SHALL 增加 `plot_items` 列并随版本换代自动建出（JSON 文本列，默认 `[]`、server_default `[]`；无任何显式版本常量或 DDL 步骤，照 db-generation 既有纪律）。
- 章装配（assemble_chapter）SHALL 输出 `plot_items`（解析后的字符串数组；空串或损坏 JSON 回落 `[]` 且不阻塞读取）。
- 章档案导出/导入 SHALL 携带 `plot_items`（加键兼容：缺失键按 `[]` 处理）。
- 落库缺键语义 SHALL 为 presence-gate：缺键保留现值、显式 `[]` 清空（与 `style_shadow` 同口径）。

#### Scenario: 旧库升级章读取

- **WHEN** 旧版本库升级后读取既有章
- **THEN** plot_items 输出为空数组，读取不报错、无显式回填步骤

#### Scenario: 损坏值不阻塞读取

- **WHEN** 某章 plot_items 存了非法 JSON
- **THEN** 装配输出空数组，章读取不报错

#### Scenario: 导出导入往返

- **WHEN** 一章含 4 条剧情导出章档案后导入
- **THEN** 4 条原样回写；导入包缺失该键时按空数组处理
