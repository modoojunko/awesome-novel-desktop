# Proposal: c-image-config-ux-fix

## Why

v0.39 图像模型配置弹窗有两处对作家不友好：①「模型清单」输入格在整条链路上没有任何功能用途（生成只消费 default_model 兜底，清单仅作展示），却与「默认模型」并排双格子且预填同值，作家以为是让填两遍、且换模型要改两处；②连接测试/试画被推迟（弹窗明示「后续版本开放」），Key/Base URL/模型 id 填错要到生成任务失败才暴露。另外内置火山预设仍是 Seedream 4.0 系，作家切供应商会被预填过时模型 id。

## What Changes

- 配置弹窗收敛为单一「模型」输入：保存时未显式携带清单则自动派生 `models = [default_model]`；移除独立「模型清单」textarea 与配置卡片上的模型 chips 列表（改显默认模型）。
- 新增「测试连接」：后端新增图像配置测试端点，用当前配置参数真实调用一次最小生成请求（试画），结果写入预留的 `last_test_status / last_test_error / last_tested_at` 三列；弹窗内按钮即时呈现通过与失败摘要。挂 `image-generate` 权益门（试画=真实消耗供应商额度）。
- 供应商预设刷新：火山引擎预填模型更新为 Seedream 5.0 系（模型 id 取自封面/头像设计说明的登记清单）。
- 弹窗底部「连接测试 / 试画 / 拉取模型清单在后续版本开放」提示随功能落地移除；「拉取模型清单」不立项（有了试画其意义消失）。

## Capabilities

- Modified: cover-avatar —— 新增 Requirement「图像模型配置表单与连接测试」（单模型收敛与派生、测试端点行为与权益门、测试状态字段、预设预填）。不触碰在途 c-image-generation delta 的生成/权益/批量 Requirement，无相撞。

## Impact

- 前端：`client/frontend/src/components/image/ImageConfigPanel.tsx`（表单收敛＋测试按钮＋结果行＋卡片改版）、`client/frontend/src/lib/imageApi.ts`（火山预设刷新＋测试 API 封装）。
- 后端：`client/backend/image_assets/router.py`（测试端点）、`service.py`（models 派生＋测试实现，复用 generation.py 六家适配器与错误分类）。
- 权益：测试端点挂 `ai_feature("image-generate") + require_tier_access`，与生成端点同属 KEYLESS_GATE_KEYS 语义（用自家 Key、不要求配置写作大模型）。
- 数据：`image_configs` 复用既有 last_test_* 三列，无迁移；旧配置的多模型清单在下次保存时收敛为 `[default_model]`（清单当前无消费方，无功能损失；备份/导入显式携带 models 的请求仍被尊重）。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏/弹层：模型配置页「添加/编辑图像模型」弹窗、图像配置卡片；书架/工作台其余屏不动。
- 对象状态：配置卡片与表单结果行新增测试状态呈现——通过=ok 语气、失败=err 语气，复用既有 `.b` 胶囊与 info/ok/warn/err 语气词表，不新增第四种胶囊形态、不引入 success/danger 词；按钮沿用 btn/vbtn 家族。
- 共享段：不触碰两端共享段（base.css 令牌与基础组件类零改动），design-cross 无需跑。
- 原型先行：需要——`prototypes/model-config.html` 图像模型弹窗与配置卡片先改，ADJUSTMENTS.md 登记偏差；由实现侧自查产出设计工件。
