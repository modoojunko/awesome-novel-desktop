## MODIFIED Requirements

### Requirement: 商品目录数据驱动三档矩阵

（Requirement 名保留 sync 连续性；内容自本 change 起为「档位 × 时长」数据驱动矩阵，档位数由 DB 决定，不再限定三档。）

GET /api/pay/skus（公开商品目录）SHALL 返回足以渲染「档位 × 时长」矩阵的全量配置，档位、时长、价格、折扣、权益卖点、上下架状态 SHALL 全部来自数据库配置，前端零硬编码；运营改库即生效，改套餐不发版。

#### Scenario: 档位卖点随配置下发

- **WHEN** tiers 表某档 selling_points 配置为 JSON 数组（如 `["AI 生成正文（流式）","设定与章纲融入 AI"]`）
- **THEN** 该档 tiers[] 返回 `selling_points` 为解析后的字符串数组（非原始 JSON 串）；未配置时返回空数组

#### Scenario: 四档矩阵随 DB 出列

- **WHEN** tiers 表含 free/standard/pro/max 四行且各自 SKU on_sale
- **THEN** 目录返回四档，standard/max 行 label/is_live/is_planned 及其 skus[] 按 DB 配置出列

#### Scenario: planned 档返回但不可购

- **WHEN** 某档 status='planned' 且其 SKU 均 on_sale=false 或不存在
- **THEN** 该档仍出现在 tiers[] 且 `is_planned: true`、`is_live: false`；其 SKU 不出现在 skus[]（pg_http 与 sqlite 双分支过滤口径一致：on_sale 且所属档 status='live'）；live 档 is_planned 恒为 false

#### Scenario: retired 档不返回

- **WHEN** 某档 status='retired'
- **THEN** 该档不出现在 tiers[]，其 SKU 亦不出现在 skus[]

#### Scenario: 档位与规格级字段齐备

- **WHEN** 目录正常返回
- **THEN** tiers[] 每行含 `key/label/is_live/is_planned/selling_points`；skus[] 字段与既有契约一致（只增不删，时长名称由 period 映射在调用方侧单源）；既有字段语义与取值不变

#### Scenario: 折扣徽标单源

- **WHEN** 某 SKU discount_permille=900
- **THEN** 该 SKU `discount_display` 为「9折」；时长 tab 徽标、卡面折扣角标均以该字段为唯一文案来源，前端不自行计算折扣文案

#### Scenario: 契约只增不删

- **WHEN** 旧客户端按旧字段消费目录
- **THEN** 既有字段（purchase_enabled/agreement_version/tiers[].key/label/is_live/skus[].* /popular_sku）全部保持原语义返回，无删除、无改名

## ADDED Requirements

### Requirement: 档位等级序（tier rank）

tier 归属（同一用户多行已激活权益取等级最高档）SHALL 依赖档位等级序，等级序机制与 DB 单源要求归 tier-catalog 能力（tiers 表 rank 列）；本能力只约定消费行为：License 归属计算 SHALL 按该等级序取最高档，且 SHALL 走带缓存的读取路径（不逐请求直查）。

#### Scenario: 持有多档取最高

- **WHEN** 用户同时持有生效的 standard 行与 pro 行
- **THEN** 有效档位为 pro（rank 高者）

#### Scenario: 调整等级序改库生效

- **WHEN** 运营调整某档 rank（如把某新档插到 pro 之上）
- **THEN** 归属计算按新等级序生效，无代码发布
