# Proposal: c-model-list-cap-300

## Why

火山方舟 `/models` 现返回 **137 条**且**最老在前**排序，而模型清单归一化的截断上限是 100（c-api-config-auto-models 拍板，防供应商长清单无界落库）——前 100 恰好全是退役/老模型，`doubao-seed-2-1-pro-260915`、`doubao-seed-evolving` 等全部在役新模型被系统性截掉。2026-10-24 用户实锤：豆包配置测试连接「成功」、清单落库，但写作模型选择器里找不到任何现役模型。上限成了按「最老在前」供应商排序的新型模型过滤器。顺带：#938 设的火山图像预设头 `doubao-seedream-5-0-260128` 在 `/models` 里已标 Retiring，在役的是 `5-0-flash-260915`，预设头应换成在役款。

## What Changes

- 清单上限 100 → **300**：`_normalize_models` 的截断窗与手动路径超限报错阈值同步抬（自动路径截断保留前 300；手动路径 >300 仍 422）；保头语义（默认模型置结果首位、不被挤出截断窗）不变。
- 火山图像预设头 `doubao-seedream-5-0-260128` → `doubao-seedream-5-0-flash-260915`（前端 `IMAGE_PROVIDERS` 与原型 `model-config.html` 同批；`4-5`/`4-0` 兜后不动）。cover-avatar spec 的预设场景写的是「Seedream 5.0 系」，flash 仍是 5.0 系，无规格漂移。

## Capabilities

- Modified: model-api-config —— Requirement「模型清单自动拉取」的截断句从泛化「上限 N」钉为 300，超长清单场景补火山案 WHEN。

## Impact

- 后端：`client/backend/api_configs/service.py`（`_normalize_models` 常量与报错文案）＋测试（自动路径 137 条全量落库、手动 301 报 422、边界 300、保头仍钉）。
- 前端：`client/frontend/src/lib/imageApi.ts` 火山预设头；`docs/design-c/prototypes/model-config.html` 同批＋ADJUSTMENTS 登记。
- 不动：拉取端点/归一化算法/保头实现（均已符合）、S端、图像测试端点。

## Design Impact

- 受影响端：仅 C端。
- 受影响屏/弹层：模型配置弹窗的模型选择器（清单内容变化——从「前 100 老模型」变为「全量至 300」）；图像模型弹窗（火山预填字符串换在役 id）。无版面/组件/状态语言改动。
- 共享段：不触碰。
- 原型先行：不需要（无版面改动）；预设字符串同步进既有原型资产并在 ADJUSTMENTS 登记条目。设计工件由实现侧自查产出。
