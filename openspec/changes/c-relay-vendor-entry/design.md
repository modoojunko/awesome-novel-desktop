# c-relay-vendor-entry — 设计

## Context

调用与探测层自 PR #747 起已对中转站现实调优（裸域名版本段归一、清单 403 降级、对话探针判据），且协议面天然两套（openai/anthropic）——vendor 在探测层仅 ollama 有特例。入口层的缺口纯在 UI 与身份登记：中转站用户挤在「OpenAI 兼容」通用格里（引导是 Gemini 口径），且保存链路靠 URL 域名检测定 vendor（`resolve_vendor` 兜底 openai-compat），中转站域名形态任意、检测必然落兜底。见 proposal.md。

## Goals / Non-Goals

**Goals:**
- 「中转站 API」成为网格一等公民：专属引导（/v1 填法、403 分组权限说明、手填模型 id 主路径）。
- 保存身份可靠：relay 经 `vendor_override` 显式登记，不赌 URL 检测。
- 探测/调用零新分支——relay 与 openai-compat 在协议路径上同径。

**Non-Goals:**
- 不迁移存量 openai-compat 配置（保持原样；内测配置不受扰）。
- 不做 relay 预填/候选登记（无据不登记纪律）。
- 不动「OpenAI 兼容」的保存行为（仍走 URL 检测＋兜底——该格的语义就是「地址说了算」）。

## Decisions

1. **vendor_id 定名 `relay`、按钮插在 Ollama 与「OpenAI 兼容」之间**：与调用层术语解耦（relay 是入口概念，不是协议概念）；紧邻 openai-compat 便于「两格什么区别」的对照认知。
2. **vendor_override 只对 relay 显式传**：前端仅当选中 relay 时在保存负载附 `vendor_override: "relay"`，其余按钮维持现状（URL 检测＋兜底）。备选「所有按钮恒传 override」语义上更正确（用户选了谁就存谁），但会翻转「OpenAI 兼容＋DeepSeek 地址存 deepseek」等既有行为与测试契约（TC-VENDOR 系），超出本 change 边界——留待后续拍板。
3. **网格 4 列改 3 列（3×3）**：9 按钮在 4 列下尾行孤格难看；3 列恰齐。窄屏维持 2 列（5 行尾孤格可接受，移动端列表惯例）。原型同步。
4. **展示名映射放 vendor.py 覆写分支**：`resolve_vendor` 的 override 命中 VENDOR_PATTERNS 之外的 id 时查 `{relay: 中转站 API, openai-compat: OpenAI 兼容}`（顺带修掉 override=openai-compat 时展示裸 id 的旧瑕疵）。
5. **引导文案双格分工**：relay 格＝中转站口径（/v1、站方令牌、403 手填）；openai-compat 格＝Gemini 官方兼容层＋自建端点，反代句改指向 relay 格（spec「未列厂商兼容模版引导」MODIFIED 收编）。

## Risks / Trade-offs

- **网格列数变更触碰 model-config 页像素**：design:check 基线若含该弹层需重录（门禁跑后如实处置，同 #689 前例）。
- **override 只救 relay 的不对称**：其他按钮仍可能被 URL 检测改写身份（如 OpenAI 兼容＋DeepSeek 地址存成 deepseek）——现状即如此且有测试钉，翻转成本另案。
- **e2e/scheduled 栈**：新增引导用例依赖 mock 桩形态（照 #741 openai-compat 引导用例同款写法），前端 CI 无 playwright 不影响门禁。
