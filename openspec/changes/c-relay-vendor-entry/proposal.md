# c-relay-vendor-entry — 供应商网格独立「中转站 API」入口

## Why

内测中转站反馈链（2026-10-08 lunarfox 案，PR #747 修调用层）暴露的入口层缺口：中转站用户今天只能挤进「OpenAI 兼容」通用格——但该格的引导是 Gemini 兼容层优先（c-api-config-foreign-vendors），用户对着「配模型」页不知道中转站该选哪个、/v1 怎么填、403「分组权限」是不是自己 Key 坏了。中转站是国内用户接 Claude/Gemini 的主流路径，值得一个一等公民入口（2026-10-08 用户拍板：独立格子，与「OpenAI 兼容」并存）。

## What Changes

- **供应商网格新增「中转站 API」按钮**（vendor_id=`relay`，插在 Ollama 与「OpenAI 兼容」之间；桌面网格 4 列改 3 列凑 3×3，窄屏维持 2 列）。选中展示中转站口径引导：Base URL 填站方地址（通常以 `/v1` 结尾）、Key 用站方后台令牌、清单拉不到（如 403 分组权限）直接手填模型 id、连接测试会实际验证对话路径。
- **保存显式登记 vendor**：中转站 URL 无法被域名检测识别（relay 站域名形态任意），选「中转站 API」保存时 SHALL 传 `vendor_override=relay`，后端登记 vendor=`relay`＋展示名「中转站 API」；探测/调用复用既有 openai 协议路径（vendor 仅 ollama 有特例，relay 无新调用实现）。既有「OpenAI 兼容」保存行为不变（仍走 URL 检测＋兜底）。
- **「OpenAI 兼容」引导收窄回自建端点口径**：Gemini 官方兼容层地址＋手填模型 id 说明保留，反代/转发句改为指向「中转站 API」按钮。
- **登记值纪律不变**：「中转站 API」无登记预填（站方地址各不相同，无据不登记——c-api-config-vendor-defaults 纪律沿用），Base URL/模型均手填。
- 明确不做：为 relay 增设独立调用实现或探针分支（协议两套已覆盖）；存量 openai-compat 配置迁移（保持原样展示，无真实存量用户；内测已有配置不受影响）；relay 候选模型登记（各站模型清单不同，无从有据）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`：ADDED「中转站接入入口」要求（独立按钮＋中转站口径引导＋vendor_override 显式登记）；MODIFIED「未列厂商兼容模版引导」（反代/转发句改指向中转站按钮）。

## Design Impact

- **受影响屏**：模型配置页「添加 API Key」弹层供应商网格＋引导文案（原型 `docs/design-c/prototypes/model-config.html`）。
- **对象状态**：复用既有 vbtn/cf-hint 形态，零新组件；网格列数 4→3 为布局参数调整。
- **共享段**：不触碰（model-config.css 的 .vgrid 列数为 capability 私有样式）。
- **原型先行**：需要——原型网格补「中转站 API」格＋列数调整，偏差登记 `ADJUSTMENTS.md`。
- **设计工件产出**：实现侧自查（design:lint/design:check 门禁）。

## Impact

- `client/frontend/src/types/api-config.ts`：`VendorId` 联合类型加 `relay`。
- `client/frontend/src/components/api-config/ProviderIcon.tsx`：VENDORS/VENDOR_LABELS 加 relay。
- `client/frontend/src/components/icons.tsx`：VENDOR_ICON 加 relay 转发箭头图形。
- `client/frontend/src/components/api-config/ApiConfigForm.tsx`：relay 引导 cf-hint；「OpenAI 兼容」hint 反代句改指向。
- `client/frontend/src/pages/ApiKeyConfigPage.tsx`（或 useApiConfigs）：relay 保存传 `vendor_override`。
- `client/frontend/src/design/model-config.css`：.vgrid 列数 4→3。
- `client/backend/api_configs/vendor.py`：resolve_vendor 覆写分支展示名映射（relay＝中转站 API；顺带 openai-compat＝OpenAI 兼容）。
- 测试：后端 vendor 展示名用例；前端 apiConfigForm/apiVendorDefaults 用例＋config-page e2e 引导文案用例。
- 原型：model-config.html＋ADJUSTMENTS.md。
- 依赖：基于 PR #747 分支叠放（引导文案引用的 403 分组权限行为由 c-relay-compat-probe 落地）。
