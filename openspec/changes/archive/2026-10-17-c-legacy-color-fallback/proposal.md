# c-legacy-color-fallback — 旧内核颜色兼容层（构建期生成，原产物不动）

## Why

2026-10-17 真机现场（v0.34.4，Windows 11）：作家打开桌面应用，窗口内页面白底黑字、全部样式失效。三份日志把定性钉死：

- `startup.log` 第 2 行 `webview2=108.0.1462.46`——机器上的 WebView2 运行时停留在 Chromium 108（2022 年底）；
- `startup.log` 同时有 `app page loaded`、无 `auto relaunch`、无 `browser fallback`——窗口装载正常、浏览器兜底没有触发，**不是** 360 或兜底路径的问题；
- `app.log` 里 `GET /`、CSS、JS 全 200，应用数据面完全正常。

根因：设计系统颜色令牌全部是 `oklch()`，派生色全部是 `color-mix(in oklch, …)`（构建产物 139 个表达式），这两个函数需要 **Chromium 111+**。108 上颜色声明整条失效，只剩布局与默认黑字。目标用户是作家，不具备「升级 WebView2 / 换浏览器 / 看日志」的能力；产品必须自己解决，且已拍板**不改动现有编译产物**、不要求用户安装任何东西、不把 243MB 的固定版运行时塞进 33MB 的安装包。

## What Changes

- **构建期新增兼容表**：`client/frontend` 构建末尾生成 `dist/legacy-colors-<hash>.css`——原样式表的**完整副本**，把每个 `oklch()` / `color-mix()` 替换为构建期算好的具体 `rgb()/rgba()`（表达式去重后以 `--lgc-N` 令牌承载），主题相关的表达式按 `:root[data-theme="<key>"]` 展开为各主题的具体值。
- **内联样式收口**：把 28 处内联 `oklch()`/`color-mix()`（用量饼图调色板、版本对比、引导卡、导入区、朱雀条等）收成设计令牌；动态徽标色改走 `withAlpha()` 运行时助手输出 rgba。构建新增 TS/TSX 扫描闸门，内联颜色函数直接构建失败。这批 C端组件专用令牌落位在 `@cross-end` 之后（共享段保持与 S端逐字一致，`design:cross` 校验）。
- **条件加载**：构建期在 `dist/index.html` 的原样式表之后注入一段同步特性检测脚本；仅当内核不支持 `oklch()` 或 `color-mix()` 时 `document.write` 加载兼容表。现代内核不加载、不应用，渲染路径与今日完全一致。
- **整份替换而非后置补丁**：兼容表是原表的完整副本（规则顺序、选择器、`@media`、`@keyframes` 全部保留），旧内核上后加载即整表生效——避免「追加覆盖层」在同权重规则上的层叠错位。
- **生成期三道闸门**（任一失败＝构建红）：① 结构对拍：副本与原表逐节点比对规则/选择器/声明顺序/`!important`；② 残留检查：副本声明值不得再有 `oklch(`/`color-mix(`；③ 可解性：未知变量、未知语法（含 `color-mix` 非 oklch/srgb 空间）直接抛错，不静默产出错色。
- **原产物零改动**：原 CSS 文件字节不变（构建后哈希对拍）；不新增运行时依赖、不改后端、不改 S端。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `design-system`: 新增「旧内核颜色兼容层（构建期生成）」要求——发布产物 SHALL 为不支持 `oklch`/`color-mix` 的内核提供整份编译副本，现代内核 SHALL NOT 加载；源文件的 oklch/color-mix 规范不变（兼容表是构建产物，不是源码里的裸 hex/rgb）。

## Impact

- `client/frontend/scripts/gen-legacy-colors.mjs`（新增）：颜色数学（oklch/sRGB、color-mix 预乘 alpha、Chromium 短弧色相行为）、主题展开、结构对拍、CLI。
- `client/frontend/scripts/gen-legacy-colors.test.mjs`（新增）：16 条单测（色值数学、srgb/oklch 混色、主题覆写、结构保真、未知变量报错、色相方法拒绝、百分比 alpha、落盘幂等）。
- `client/frontend/package.json`：`build` 末尾接生成器；新增 `design:legacy` 手动入口。
- `client/frontend/vitest.config.ts`：`include` 纳入 `scripts/**/*.test.mjs`。
- `client/frontend/src/lib/color.ts`（新增）：`withAlpha()` 运行时混色助手（hex/rgb → rgba；不支持的形态回落 `--fg-soft`）。
- `client/frontend/scripts/check-inline-colors.mjs`（新增）：TS/TSX 内联颜色函数扫描闸门，接入 `npm run build`。
- 构建产物：新增 `dist/legacy-colors-<hash>.css`（≈204KB）与 `index.html` 中一段条件加载脚本；原 CSS 0 字节改动。
- 验证：`design:cross`（模拟 S端＝origin/main 共享段）零差异；Chromium 对拍 139 个表达式 × 6 套主题（默认 + 5 主题色）＋ 42 个颜色令牌 × 6 套主题 ＝ 1086 项，新旧色值 **0 差异**；原 CSS 哈希构建前后一致；全量 vitest 135 文件 / 1692 用例绿。
- 明确不做：运行时缺失/损坏的 WebView2 修复（另案）；108 不支持的其它 CSS 能力（当前产物无）；固定版运行时随包（已按 ROI 否决，243MB vs 33MB）；S端同名令牌（独立仓，另案）。
