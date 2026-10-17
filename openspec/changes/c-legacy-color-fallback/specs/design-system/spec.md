# design-system Delta — 旧内核颜色兼容层

## ADDED Requirements

### Requirement: 旧内核颜色兼容层（构建期生成）

C端发布构建 SHALL 在保留原样式表字节不变的前提下，额外生成一份完整等价的旧内核兼容表 `legacy-colors-<hash>.css`：把样式表中的每个 `oklch()` 与 `color-mix()` 表达式求值为具体 `rgb()/rgba()`，并按 `:root[data-theme="<key>"]` 展开主题相关值。兼容表的规则顺序、选择器、`@media`、`@keyframes` 与 `!important` SHALL 与原样式表逐条同构；生成器 SHALL 在结构漂移、残留颜色函数、表达式不可解（未知变量/非 oklch·srgb 的混色空间）时使构建失败，SHALL NOT 产出带错误的兼容表。

应用 SHALL 仅在不支持 `oklch()` 或 `color-mix()` 的内核上加载兼容表（特性检测，同步于首帧前完成）；支持这两个函数的内核 SHALL NOT 加载或应用兼容表，其生效规则与兼容层引入前逐字节一致。

组件内联样式 SHALL NOT 直接使用 `oklch()`/`color-mix()`；动态颜色 SHALL 引用设计令牌或经运行时助手输出 rgba。构建 SHALL 扫描 `src` 下的 `.ts`/`.tsx`，命中颜色函数即失败。

本要求不改变源文件规范：`src/design/base.css` 等源文件中的色令牌 SHALL 继续以 `oklch`/`color-mix` 声明（见「One shared token palette and theme」）；兼容表中的 `rgb/rgba` 属于构建产物，不受「源文件禁止裸 hex/rgb」约束。

#### Scenario: 旧内核上颜色不丢失
- **WHEN** 桌面应用在不支持 `oklch()`/`color-mix()` 的内核（如 Chromium 108 的 WebView2）中打开
- **THEN** 页面加载兼容表，令牌与组件颜色按默认主题或所选主题正确呈现，布局与文字不受影响

#### Scenario: 现代内核零变化
- **WHEN** 应用在支持 `oklch()`/`color-mix()` 的内核中打开
- **THEN** 兼容表不被加载，原样式表字节与生效规则与引入兼容层之前完全一致

#### Scenario: 主题派生色逐主题展开
- **WHEN** 用户选择 ink / bamboo / rouge / wisteria / celadon 任一主题
- **THEN** 依赖 `--accent`/`--accent-strong` 的派生色取该主题的具体值，与 `oklch`/`color-mix` 原生计算一致（允许 ±1 通道的 8bit 舍入）

#### Scenario: 内联样式不在旧内核掉色
- **WHEN** 旧内核渲染用量饼图、版本对比、引导卡等使用组件内联样式的界面
- **THEN** 内联样式只引用令牌或运行时算好的 rgba，颜色与 111+ 一致

#### Scenario: 生成期闸门拦截回归
- **WHEN** 样式源出现生成器不支持的语法，或生成结果的结构/选择器/声明顺序与原表不一致
- **THEN** 构建失败并指明具体选择器、属性或表达式
