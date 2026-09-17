# chapter-data 变更（增量）

## ADDED Requirements

### Requirement: 章档案新增列的持久化与导出（加键兼容）

- `chapters` SHALL 增加两列并经幂等 ALTER 对存量库升级：`style_shadow`（JSON 文本，默认 `{}`——本章文风影子）与 `ghost_of`（可空字符串——旧稿支线的来源章号）。
- 章装配（assemble_chapter）SHALL 输出 `style_shadow`（解析后的对象；损坏 JSON 回落 `{}` 且不阻塞读取）与 `ghost_of`（set 时输出）；两者 SHALL 随章档案导出并随导入回写（加键兼容：缺失键按默认值处理）。
- 既有章读取契约 SHALL NOT 因新增键破坏：未设置影子/非支线章的装配结果语义与字段等价于新增前。

#### Scenario: 影子随导出导入往返
- **WHEN** 某章设置了影子行后导出并重新导入
- **THEN** 该章的影子行原样保留

#### Scenario: 损坏影子不阻塞读取
- **WHEN** 某章 style_shadow 存了非法 JSON
- **THEN** 章装配成功，shadow 为空对象

#### Scenario: 支线来源随章保留
- **WHEN** 某章转入旧稿支线（ghost_of=目标章号）后导出
- **THEN** 导出包含 ghost_of，导入后支线关系保留
