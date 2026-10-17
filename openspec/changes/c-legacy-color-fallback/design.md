# design — c-legacy-color-fallback

## 约束与取舍

| 方案 | 结论 |
|---|---|
| A1 直接改写现有 CSS 产物（颜色就地替换） | 否——用户拍板「不改现有编译结果」；且现代内核拿到的是编译值，失去 oklch 源语义 |
| A2 追加「覆盖层」样式表（`@supports not (...)` 包裹） | 否——所有兼容规则都排在原表之后，同权重下会压过原表中更靠后的正常覆盖，层叠错位不可静态证明安全 |
| **A2′ 完整副本 + 条件加载（本 change）** | **是**——副本与原表同构同序，旧内核整表替换，层叠关系不变；现代内核不加载 |
| B 随包带 WebView2 Fixed Version | 否——安装包 33MB → 约 270MB（cab 243.5MB），每次更新同量；且只治「运行时缺失/过旧」，治不了浏览器兜底；固定版获取链还依赖微软动态下载页 |

## 机制

1. **完整副本**：解析构建产物 CSS（含 Tailwind 展开后的全部规则），在内存中逐条声明改写，树结构、规则顺序、选择器、`@media`/`@keyframes`/`!important` 全部原样保留；新增的只有文件末尾的 `--lgc-*` 令牌定义规则。
2. **表达式去重**：每个不同的颜色表达式分配一个 `--lgc-N`；声明值里只写 `var(--lgc-N)`。同一表达式在多处复用同一个令牌。
3. **主题展开**：`:root` 令牌表 + `:root[data-theme=…]` 覆盖（当前只有 `--accent`/`--accent-strong` 随主题变）。生成器对每个表达式分别用默认主题与 5 套主题的令牌表求值；只在值确实变化时，才在该主题的 `:root[data-theme="…"]` 里追加覆写。
4. **内联样式收口**：旧内核兼容表只能覆盖样式表，内联样式里的 `oklch()`/`color-mix()` 无法在构建期替换。把 28 处内联用法收成 `base.css` 令牌（`--accent-2/5/6/8/20/35`、`--fg-4/30/75`、`--ok-15/25/72`、`--warn-72`、`--err-8/15/25/35/72`、`--chart-1..6`）；动态徽标色走 `withAlpha()` 运行时助手算成 rgba。构建前扫描 `src` 下的 `.ts/.tsx`，命中颜色函数即失败。令牌定义落位在 `@cross-end` 之后的 C端本地段——不能写进 `@cross` 共享段，否则与 S端逐字校验漂移。
5. **条件加载**：`dist/index.html` 原样式表之后注入同步脚本——
   `if (!(CSS.supports('color','oklch(…))' && CSS.supports('color','color-mix(in oklch, red, blue)'))) document.write('<link rel="stylesheet" href="./legacy-colors-<hash>.css">')`。
   `document.write` 在解析期同步插入，样式表按渲染阻塞资源处理，旧内核首帧即有样式，无闪烁。
5. **为什么现代内核可以完全不加载**：原 CSS 字节不动、链接不动；脚本条件为真时不产生任何 DOM 变化。

## 颜色数学（与 Chromium 对齐的实测判例）

- `color-mix()` 预乘 alpha 插值；`transparent` 的色相**无力**（沿用另一色相）。
- **不透明无彩色（C=0，如白色 `oklch(100% 0 0)`）按 hue=0 参与短弧插值**——Chromium 实测 `color-mix(in oklch, oklch(48% .11 170) 50%, white)` 得 `oklch(0.74 0.055 85)`，不是「白色色相无力沿用 170」。首版算法按「C=0 即无力」实现，Chromium 对拍抓出 32 处色差（4–9/通道），已按实测校正并加行为钉。
- `in srgb` 混色同样支持（产物里 `.pk-corner` 用了它）；显式 `longer`/`increasing`/`decreasing hue` 直接构建失败（不静默按短弧算）。
- `rgb()/rgba()` 的百分比 alpha 按 0–1 解析，不再当成 0–255 数值。
- 输出统一 `rgb()/rgba()`（逗号旧语法，108 可解析）；色值 8bit 四舍五入，允许 ±1 通道差异。

## 闸门

1. **结构对拍**：生成前对原树/新树逐节点比对——类型、选择器、at-rule 参数、声明属性顺序、`!important`；声明值必须等于「原值把每个颜色函数替换为对应 `var(--lgc-N)`」。
2. **残留检查**：成品所有声明值不得再出现 `oklch(`/`color-mix(`（`@supports` 参数不参与，当前也无）。
3. **可解性**：未知变量、变量循环、非 oklch/srgb 空间、at-rule 参数里的颜色函数，一律抛错中止构建。
4. **内联扫描**：build 前扫描 `src` 下的 `.ts/.tsx`（跳过注释与测试），命中 `oklch()`/`color-mix()` 即失败——内联样式只允许引用令牌或运行时算好的 rgba。
5. **幂等**：生成器排除自身注入的 `legacy-colors-<hash>.css` 链接，二次运行产物字节一致（首版未排除导致体积翻倍，已被幂等单测钉住）。

## 验证证据（2026-10-17 本机）

- Chromium（Playwright 1234）：139 表达式 × 6 主题 + 42 个颜色令牌 × 6 主题 = **1086 项，0 差异**。
- `design:cross`（S_SERVER_DIR 指向以 origin/main 共享段模拟的 S端）：共享段零差异。
- 原 CSS 哈希：构建 → 生成器前后一致；`npm run build` 连跑两次 legacy 产物哈希一致。
- 全量 vitest：135 文件 / 1692 用例全绿；design:lint 无新增违规；内联扫描无命中。
- 注入分支：模拟 `CSS.supports=false` 时页面出现且仅出现一个 `legacy-colors-<hash>.css` 链接；默认现代内核 0 个。

## 风险与非目标

- 风险：旧内核上兼容表是整份副本，任何生成遗漏都会造成部分样式与原表不一致——由结构对拍 + 残留检查兜底；颜色数学由 Chromium 对拍兜底。
- 非目标：WebView2 完全缺失/损坏时的自愈；108 不支持的其它 CSS 能力（当前产物无 `:has`/`dvh`/`@layer`/`@container`）；S端（独立仓）。
