// 设计词汇表（lint 白名单）——机器强制层；标准正文唯一在 docs/ux/design-language.html。
// 档位/禁令改动由标准派生，两端（client/server scripts/design-vocab.mjs）同批修改。
// 规则：原型与「已收编」屏的源码里出现的类，必须落在下列档位/登记簿内；
// 出现未登记的任意值、档位外 opacity、裸 hex/rgb、emoji、daisyUI 语义类回归
// → design:lint 失败。

// ── 严格模式的扫描范围 ──────────────────────────────────────────
// 原型永远严格；strictSrcGlobs 是「已收编」屏的源码，随校准逐屏加入。
// PR 1 收编：书架屏 + 设计系统地基（图标/弹窗/Toast/PrefsModal + 旧弹窗收编）。
// PR 7 收编：daisyUI/lucide 退役迁移面（结构树/版本对比/导入×3/设定弹窗×3/
//           会员拦截/引导卡/用量图 + 登录页/营销页轻重皮）。
export const strictGlobs = ["../../docs/design-c/prototypes/list.html", "../../docs/design-c/prototypes/model-config.html", "../../docs/design-c/prototypes/book.html", "../../docs/design-c/prototypes/index.html"];
export const strictSrcGlobs = [
  "src/pages/NovelListPage.tsx",
  "src/components/Footer.tsx",
  "src/components/Navbar.tsx",
  "src/components/AcctMenu.tsx",
  "src/components/icons.tsx",
  "src/components/design/Modal.tsx",
  "src/components/novel/CreateProjectModal.tsx",
  "src/components/novel/RenameModal.tsx",
  "src/components/novel/DeleteConfirmModal.tsx",
  "src/lib/toast.tsx",
  "src/lib/prefs.ts",
  "src/lib/auth.ts",
  // ── PR 7 收编（daisyUI/lucide 退役迁移面）──
  "src/components/novel/StructureTree.tsx",
  "src/components/novel/VersionDiff.tsx",
  "src/components/novel/OnboardingCard.tsx",
  "src/components/novel/ImportNovelModal.tsx",
  "src/components/novel/ImportPreviewTree.tsx",
  "src/components/novel/ImportUploadZone.tsx",
  "src/components/novel/settings/AISuggestionModal.tsx",
  "src/components/novel/settings/GenreEditModal.tsx",
  "src/components/novel/settings/CharacterCreateModal.tsx",
  "src/components/novel/license/MemberBlockPrompt.tsx",
  "src/components/api-config/UsagePieChart.tsx",
  "src/pages/LoginPage.tsx",
  "src/pages/LandingPage.tsx",
];

// ── 只统计、不阻断的范围（存量冻结，供定档观察）────────────────
export const reportGlobs = ["src/**/*.{tsx,ts}"];

// ── 任意值登记簿 ────────────────────────────────────────────────
// Tailwind 任意值语法（[...]）默认一律禁止；确需使用的在此登记并注明用途。
// （非类名字符串 —— CSS 选择器含 [attr] 语法 —— 也在此登记，注明是选择器）
export const allowedArbitrary = new Set([
  "min-h-[100px]", // 书列表虚线卡最小高（tailwind 3.4 无 100px 档）
  "a[href],", // Modal 焦点圈选择器片段（querySelectorAll，非类名）
  "min-h-[120px]", // AI 建议弹窗内容最小高（加载态不塌陷）
  "max-h-[300px]", // AI 建议弹窗内容最大高（长建议内滚动）
  "w-[900px]", // 营销页 hero 主光斑宽（装饰性径向渐变）
  "h-[700px]", // 营销页 hero 主光斑高
  "w-[300px]", // 营销页 hero 侧光斑宽
  "h-[300px]", // 营销页 hero 侧光斑高
  "top-[40%]", // 营销页 hero 左光斑定位
  "top-[30%]", // 营销页 hero 右光斑定位
  "left-[15%]", // 营销页 hero 左光斑定位
  "right-[15%]", // 营销页 hero 右光斑定位
]);

// ── opacity 档位（按属性族）────────────────────────────────────
// 文本灰度四档 /30 /40 /60 /80；边框允许低档做发丝线；bg/shadow 允许浅色晕染
// 档与表面混合档。档位外（如 /50 /70 /15 /25）在严格范围内即违规。
export const allowedOpacity = {
  text: [30, 40, 60, 80],
  border: [10, 20, 30, 40, 60],
  bg: [5, 10, 20, 60, 70, 80],
  shadow: [5, 10, 20],
  default: [30, 40, 60, 80],
};

// ── 禁用的原生色板（必须用主题语义色 base-/primary-/… 替代）────
export const paletteRegex =
  /^(?:stone|amber|slate|gray|zinc|neutral|red|orange|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|yellow)-\d{2,3}(?:\/\d+)?$/;

// ── PR 7 新增：裸色值 / emoji / daisyUI 回归 ───────────────────
// 颜色一律走 design/*.css 的 oklch token（或 color-mix 派生），
// 源码里出现裸 hex / rgb()/rgba() 字面量即违规（原型 CSS 同理）。
export const hexRegex = /#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![0-9a-fA-F])/;
export const rgbRegex = /\brgba?\(\s*\d/;

// 图标一律走 @/components/icons 注册表（原型 SVG 路径照抄）；
// 含 emoji 区段（含 ✓✦ 等 dingbats）即违规。注意 U+2190-21FF 文本箭头（← →）不在禁列。
export const emojiRegex = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}]/u;

// daisyUI 已退役：语义色/组件类不允许回归（token 级全词匹配，
// card-skeleton / btn-block / btn-ghost 等设计系统同名类不受影响；
// 裸 loading 是常见状态字符串，只禁 loading-spinner 等具体变体）。
export const bannedDaisyRegex =
  /^(?:(?:text|bg|border)-(?:primary|secondary|accent|neutral|error|success|info|warning|base-100|base-200|base-300|base-content)|base-content\/\d+|modal-box|modal-action|modal-backdrop|modal-open|join-item|select-bordered|link-primary|link-secondary|link-hover|btn-square|btn-circle|btn-outline|step-primary|skeleton|loading-(?:spinner|dots|ring|ball|bars|infinity))$/;
