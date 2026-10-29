# c-modelconfig-help-guide 设计

## 现状与落点

- 添加/编辑配置弹窗＝`client/frontend/src/components/api-config/ApiConfigForm.tsx`（Modal＋vgrid 方块区＋cf-hint 提示体系）；列表页＝`client/frontend/src/pages/ApiKeyConfigPage.tsx`（page-head 内「添加 API Key」btn-primary）。
- 原型（已拍板）：`docs/design-c/drafts/ai-novel-c端-模型配置-配置步骤指南-原型.html`，文案为产品文案终稿，**实现逐字取用原型文案**（含标点），不重新发挥。

## 方案

### 组件

新增 `client/frontend/src/components/api-config/ConfigGuideModal.tsx`：

- 复用 `components/design/Modal`（open/onClose/width），`width={880}`；固定高 760px 落在指南专属样式类（`.guide-modal`）上：`.mcard` 高度固定、body `overflow-y:auto`——注意 Modal 现有宽度语义是 `min(Npx, 92vw)`，880px 在 ≥960px 视口即为固定值，与拍板「固定尺寸」一致；<960px 视口下按现有 Modal 兜底缩放（原型同口径，桌面应用实际窗口远大于此）。
- 三页签复用 `.seg` 分段控件；内容三段（适用范围 chips／四步／FAQ）为指南专属类（`guide-*` 前缀，样式入 `theme.css` 设计系统段——见样式落点）。
- 文案与数据全部内聚为组件内常量：`GUIDE_TABS`（三页签）、`GUIDE_CONTENT`（每页签适用范围 chips＋步骤数组＋FAQ 数组）、`OPENAI_KEY_SOURCES`（领 Key 地址表数据），地址表条目＝`{ name, url, note? }`，便于发布前人工复核与后续增补。
- 导出 `guideTabForVendor(vendorId): GuideTab`：Anthropic／opencode-go-claude→`anthropic`；gemini→`google`；其余（含空）→`openai`。单源供两处入口用。

### 两处入口

1. `ApiKeyConfigPage.tsx`：page-head 中「添加 API Key」按钮外包一层 `div.guide-actions`（`display:flex; gap:10px`——page-head 是 space-between，两钮必须成组，原型判例），内放「配置指南」`btn btn-secondary`（打开指南，默认 openai 页签）。
2. `ApiConfigForm.tsx`：新增可选 prop `onOpenGuide?: () => void`；非编辑态在 `.vgrid` 之后渲染引导行（cf-hint 同款）：「不知道怎么填？<链接>看三步配置指南</链接>——领 Key → 贴 Key → 测试连接。」点击回调 `onOpenGuide`；`onOpenGuide` 未传时不渲染（编辑态不渲染）。页面侧组装：`openGuide(guideTabForVendor(formVendorId))`——表单当前选中供应商由页面持有态镜像（`useRef` 记录 form 最近一次选中 vendor，经新 prop `onVendorChange?` 上报），保证定位正确。

### 样式落点

`client/frontend/src/styles/theme.css` 追加 `guide-*` 段（跟随现有组件样式组织；全部使用既有 token 变量 `--border/--fg/--muted/--accent/--paper-bg` 等，不新增颜色字面量——legacy-colors 构建闸对 oklch 字面量有扫描约束）。要点类：`.guide-actions`、`.guide-modal`（固定高）、`.guide-tabs`、`.guide-scope`（chips）、`.guide-steps/.guide-step`（编号圆）、`.guide-kv`（两列地址表网格）、`.guide-faq`（details 折叠）。

### 不做

- 不做分步向导、不做指南内跳转注入（保持只读手册）；不做移动端断点专项（桌面应用）。
- Google 系页签不提 OpenCode Go 订阅内 gemini 的直连可能性（应用无原生 google 格式，待后续 change 落地再补文案）。

## 测试

- `src/__tests__/configGuideModal.test.tsx`：三页签渲染与切换（内容面板互斥、弹窗不关）；`guideTabForVendor` 映射矩阵（anthropic/opencode-go-claude→anthropic、gemini→google、deepseek/openai-compat/空→openai）；文案黑名单断言（协议/SDK/端点/探针/兼容层不出现在可见文案）；地址表含全部 8 家。
- `src/__tests__/apiConfigParts.test.tsx` 增补：表单内引导行渲染＋点击回调带定位；`onOpenGuide` 未传不渲染。
