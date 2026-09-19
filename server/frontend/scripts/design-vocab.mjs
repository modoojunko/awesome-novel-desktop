// 设计词汇表（lint 白名单）——机器可读的单一事实源，从 C端
// client/frontend/scripts/design-vocab.mjs 复制裁剪。
// 规则：S端 src 全量收编换装 v2 终态后，源码里出现的类必须落在
// 词汇表档位/登记簿内；出现未登记任意值、档位外 opacity、裸 hex/rgb、
// emoji、daisyUI 语义类回归 → design:lint 退出码 1。
// S端 无一对一原型文件（换装按 C端 已收编惯例实现），故不扫原型，
// 也不建像素 parity（C端 才有 DESIGN_PARITY 层）。

// ── 严格模式的扫描范围 ──────────────────────────────────────────
// 换装 PR1–PR4（#191–#194）后 src 全量已在设计系统上，整目录严格。
// 原型 html 在 C端 仓库 docs/design-c/prototypes/，不属 S端 扫描范围。
export const strictGlobs = [];
export const strictSrcGlobs = ["src/**/*.{vue,ts}"];

// ── 只统计、不阻断的范围（存量冻结，供定档观察）────────────────
// 无存量：严格范围已覆盖全部源码。
export const reportGlobs = [];

// ── 任意值登记簿 ────────────────────────────────────────────────
// Tailwind 任意值语法（[...]）默认一律禁止；确需使用的在此登记并注明用途。
// （非类名字符串 —— CSS 选择器含 [attr] 语法 —— 也在此登记，注明是选择器）
export const allowedArbitrary = new Set([
  "a[href],", // AppModal 焦点圈选择器片段（querySelectorAll，非类名）
  "lg:text-[44px]", // 落地页 hero 主标题（36→44px，介于 4xl/5xl 之间，PR3 定档）
]);

// ── opacity 档位（按属性族）────────────────────────────────────
// 与 C端 同档：文本灰度四档 /30 /40 /60 /80；边框允许低档做发丝线；
// bg/shadow 允许浅色晕染档与表面混合档。
export const allowedOpacity = {
  text: [30, 40, 60, 80],
  border: [10, 20, 30, 40, 60],
  bg: [5, 10, 20, 60, 70, 80],
  shadow: [5, 10, 20],
  default: [30, 40, 60, 80],
};

// ── 禁用的原生色板（必须用 oklch token / 组件类替代）───────────
export const paletteRegex =
  /^(?:stone|amber|slate|gray|zinc|neutral|red|orange|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|yellow)-\d{2,3}(?:\/\d+)?$/;

// ── 裸色值 / emoji / daisyUI 回归 ──────────────────────────────
// 颜色一律走 design/*.css 的 oklch token（或 color-mix 派生），
// 源码里出现裸 hex / rgb()/rgba() 字面量即违规。
// 负向后行断言排除锚点 href="#features"（#fea 会伪装成三位色值）、
// SVG url(#ref) 与路由 /#/hash 片段——它们不是颜色。
// 负向先行断言 (?!\s*\p{Script=Han}) 排除注释里「#414 评审」这类 issue 号引用
// （3/6/8 位数字后跟空白+中文）——与 C端 design-vocab 同批修改，两端同源。
export const hexRegex =
  /(?<!["'`(/])#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])(?!\s*\p{Script=Han})/u;
export const rgbRegex = /\brgba?\(\s*\d/;

// 图标一律走 @/components/ui/icons 注册表（原型 SVG 路径照抄）；
// 含 emoji 区段（含 ✓✦ 等 dingbats）即违规。U+2190-21FF 文本箭头不在禁列。
export const emojiRegex = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

// daisyUI 已退役（PR #195）：语义色/组件类不允许回归（token 级全词匹配；
// btn-ghost / btn-block 等设计系统同名类不受影响）。
// 退役类名禁令（s-ui-alignment）：.b / .strip 已被 .pill / .notice 取代
// （裁决 docs/ux/cross-end.html §3.1/§3.2），token 级全词匹配防回流；
// 全词锚定：循环变量绑定等不带类名语境的片段不误伤（HeroSection 循环变量已改名 bk）。
// C端 同一禁令暂缓：其存量 .b（NovelListPage:287 与 prototypes）尚未收编，
// 由 C端 批次同批启用同一表达式（禁令表达式本身保持两端逐字相同的契约）。
export const retiredClassRegex = /^(?:b|strip)$/;

export const bannedDaisyRegex =
  /^(?:(?:text|bg|border)-(?:primary|secondary|accent|neutral|error|success|info|warning|base-100|base-200|base-300|base-content)|base-content\/\d+|modal-box|modal-action|modal-backdrop|modal-open|join-item|select-bordered|link-primary|link-secondary|link-hover|btn-square|btn-circle|btn-outline|step-primary|skeleton|loading-(?:spinner|dots|ring|ball|bars|infinity))$/;
