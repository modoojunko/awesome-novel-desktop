# 爱小说（ai-novel）前端交互原型 — 设计与实现规范

本目录是「爱小说」前端的**交互式 HTML 原型**，在 OpenDesign 里直接渲染预览。本文件是**原型层的权威规范**（视觉 token 逐字值 / 组件类尺寸 / 页面清单 / 避坑），只对本目录四个 HTML 的像素与交互基线负责；语义、词汇、状态语言与组件档位的**标准层**是仓库内 `docs/ux/design-language.html`（全端一致性裁决见 `docs/ux/cross-end.html`，机器强制层为两端 `scripts/design-vocab.mjs`）。两层冲突时以标准层为准，并在 `ADJUSTMENTS.md` 登记本文件的对应修订。后续任何 agent 复刻或新增页面时，必须先读本文件，并逐条遵守。目标是与真实 React 代码库在功能上对齐、在视觉上 100% 复刻本设计系统。

## 0. 参考代码（只读）

真实实现位于 `/Users/modoojunko/Desktop/coding/ai-novel`（React）。只读参考，**不要改它**，本目录的 HTML 原型才是交付物。

关键参考文件：
- `client/frontend/src/types/api-config.ts` — `VendorId`（8 个供应商，**没有 Gemini**）、`ConnectionStatus`（7 种状态）
- `client/frontend/src/components/api-config/ProviderIcon.tsx` — 供应商标签（参考代码用 emoji 图标，**原型改用 SVG 单线图标**，见 §5）
- `client/frontend/src/components/api-config/ApiConfigForm.tsx`、`ApiConfigCard.tsx` — 表单校验、卡片结构

## 1. 设计原则（不可违背）

1. **中性暖底 + 单一墨绿强调色**。全站只有一种主色（墨绿 oklch accent），错误用暖红、警示用琥珀、成功用绿，全部来自 token。
2. **宋体做展示、黑体做正文、等宽做数字**。标题/书名/章节名用 `--font-display`（Noto Serif SC），正文用 `--font-body`，数字/计数/时间/Key 用 `--font-mono` + `tabular-nums`（配 `.num` 类）。
3. **所有颜色用 oklch token，禁止裸 hex / rgb / hsl**。派生色一律 `color-mix(in oklch, …)`。
4. **禁止 emoji 图标**。所有图标都是内联 SVG 单线（monoline），描边 `stroke="currentColor"`、`stroke-width="1.7"`、`stroke-linecap/linejoin="round"`、`fill="none"`、`viewBox="0 0 24 24"`。
5. **数字诚实**。用量、字数、进度、时间必须来自状态或可解释的种子数据，不许写死虚假的大数字充数。
6. **文案用简体中文**，语气克制、不卖萌、不加感叹号。保留用户数据里的英文（如供应商名、Base URL、模型名）。
7. **登录/授权不在范围内**。账号相关 UI 只做占位（如「免费版 · 单机使用」），不实现真实鉴权流程。

## 2. 设计 Token（每个 HTML 的 `:root` 必须原样包含）

```css
--bg:      oklch(98% 0.004 240);
--surface: oklch(100% 0 0);
--fg:      oklch(20% 0.02 240);
--muted:   oklch(50% 0.018 240);
--border:  oklch(90% 0.006 240);
--accent:  oklch(48% 0.11 170);
--accent-strong: oklch(41% 0.10 170);
--accent-soft:   color-mix(in oklch, var(--accent) 12%, transparent);
--ok:    oklch(52% 0.11 155);  --ok-soft:   color-mix(in oklch, var(--ok) 14%, transparent);
--warn:  oklch(50% 0.13 75);   --warn-soft: color-mix(in oklch, var(--warn) 16%, transparent);
--err:   oklch(50% 0.17 25);   --err-soft:  color-mix(in oklch, var(--err) 12%, transparent);
--fg-soft:   color-mix(in oklch, var(--fg) 5%, transparent);
--shadow-card: 0 1px 2px color-mix(in oklch, var(--fg) 5%, transparent),
               0 12px 32px -12px color-mix(in oklch, var(--fg) 14%, transparent);
--font-display: 'Noto Serif SC', 'Songti SC', 'STSong', 'Iowan Old Style', Georgia, serif;
--font-body: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', system-ui, sans-serif;
--font-mono: ui-monospace, 'SF Mono', Menlo, 'JetBrains Mono', monospace;
--radius: 10px; --radius-lg: 16px;
```

差异（有意为之，别「统一」掉）：`book.html` 用 `--radius-lg: 14px`；`list.html` 与 `index.html` 不定义 `--err`/`--err-soft`（它们没有错误态 UI，需要时再加）。`body`：`font-family: var(--font-body); font-size: 14px; line-height: 1.55;`（`index.html` 是 15px / 1.6）。

实现层补充令牌（**不要求原型包含**，React/Vue `base.css` 与 `docs/ux/` 五份文档的 `:root` 同名同值；2026-08-29 起六处规范块逐字一致）：`--on-accent: oklch(100% 0 0);`（accent 实底上的反白，禁止再用 `var(--surface)` 冒充）、`--shadow-pop: 0 18px 50px -12px color-mix(in oklch, var(--fg) 26%, transparent);`（Modal / Toast / 下拉 / 悬浮菜单专属浮层投影）。

## 3. 通用组件类（跨页复用，语义一致）

- 按钮 `.btn`：默认 `inline-flex; align-items:center; justify-content:center; gap:7px; height:34px; padding:0 15px; border-radius:var(--radius); font-size:13.5px; font-weight:500`。变体：`.btn-primary`（墨绿实底白字）、`.btn-secondary`（描边）、`.btn-ghost`（透明）、`.btn-danger`（红）、`.btn-sm`。
- 徽标 `.b`（或 `.badge`）：`inline-flex; padding:2px 9px; border-radius:999px; font-size:11px`。状态色：`.b.ok` / `.b.err` / `.b.warn` / `.b.muted`。**实现层**按 ux 标准 §6.2 把全站 13 种胶囊收敛为 `.pill-*` 四角色（`uikit/uikit.css` 有实物）；原型暂保留 `.b`，改名属跨页机械替换，须先在 `ADJUSTMENTS.md` 登记，不得两套类名长期并存。
- 分段控件 `.seg`：外层灰底圆角容器，内 `.seg button`，选中 `.on`（`background:var(--surface); color:var(--fg); box-shadow: 0 1px 2px …`）。
- 弹窗：`.scrim`（半透明遮罩）+ `.modal`（居中）+ `.mcard`（`width:min(440–460px, 92vw)`、`border-radius:16px`、`box-shadow:var(--shadow-card)`）。头部 `.mcard-head`（标题用 `--font-display` 17px）+ `.mcard-body` + `.mcard-foot`（右对齐按钮）。打开/关闭：给 `.scrim`/`.modal` 加 `.show` 类，用 200ms `setTimeout` 后再 `hidden`。
- Toast：`.toast-wrap`（右下角固定）+ `.toast`（`background:var(--fg); color:var(--surface); padding:9px 16px; border-radius:10px`），带 `toast-in` 动画，自动消失。
- 顶栏 `.appbar`：`.logo`（`.logo-mark` = 墨绿圆角方块内「爱」字 + 「爱小说」宋体，字标 `letter-spacing: 0.08em` 与全站品牌字标统一）+ `.nav`（当前页 `class="on"` + `aria-current="page"`）+ `.spacer`。工作台页另用 `.back` 返回链接。品牌规则（2026-08-29 拍板）：「爱」方标只存在于系统层（appbar/窗口/安装图标），内容层一律纯文字字标。
- 面板 `.panel`：`background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-lg); padding:20px 22px`，头部 `.panel-h` 标题用宋体。
- 表单 `.field`（列布局）+ `.input`（`width:100%; padding:9px 12px; border:1px solid var(--border); border-radius:9px`，focus 用墨绿 outline）+ `.alt` 辅助说明。
- 空状态 `.empty`：虚线描边、居中、`.serif` 标题 + 灰说明。
- 页面头 `.page-head`：左侧 `h1`（宋体 30px）+ `.sub` 副标题，右侧操作按钮；窄屏改为竖排。
- 数字 `.num` / 等宽：`font-family:var(--font-mono); font-variant-numeric:tabular-nums`。

## 4. 页面清单与导航

| 文件 | 用途 | data-od-id 数 |
|---|---|---|
| `index.html` | 落地页 / 设计说明：展示 token、字体、原则、四个页面入口 | 8 |
| `home.html` | 静态首页（welcome 入口卡）六变体评审稿：玄墨/卷首/朱印/断章/悬丝/对仗（右下角切换器非基线） | 8 |
| `list.html` | 书架「我的作品」（v2 换代 2026-09-20）：页头工具栏（搜索/四态筛选 chips/排序）+ 卡片列表（无筛选＝单网格，单态＝生命周期分组） + 分页（12/页＋加载更多） + 首启三步引导（零书，应用侧扩展保留）+ 满额锁定墙与 quota 提示条（`ainovel.member='0'` 注入免费待遇，应用侧扩展保留）+ 新建 + 偏好设置弹窗。注入键 `od.works.v1`（书含 `state`/`createdAt`/`updatedAt` 数字时间戳） | 15 |
| `book.html` | 书工作台（核心）：设定 / 写作 / 预览 三大视图 | 50 |
| `model-config.html` | 模型配置：API Key 管理 + 用量统计 | 8 |

导航链路（三个 appbar 页一致）：`我的作品(list.html)` · `模型配置(model-config.html)` · `示例书 · 书工作台(book.html)`。logo 始终链回 `index.html`。`list.html` 的偏好弹窗里有「模型配置 · API Key → 去配置」行。

## 5. SVG 图标规范

- 每个供应商一个单线图标，路径必须**归一化到约 14 单位、居中于 24×24 viewBox**（即图形大致落在 x/y ∈ [5,19]）。不要有的图形占满 16 单位、有的只占 8 单位，否则视觉大小不一致。
- 渲染统一走 `iconSvg(id, size = 22)`：返回 `<svg width height viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`。**size 参数要真的用上**（写到 width/height 属性，CSS 仍可覆盖）。
- 已归一化的 8 个供应商图标路径见 `model-config.html` 的 `VENDORS` 数组，直接复用，勿自造。

## 6. 各页要点

### list.html（书架）
- 数据 `localStorage['ainovel.books']`，seed 若干本书（封面用 `.mono` 方块 + 首字）。卡片显示：书名（宋体）、状态徽标、字数（`.num`）、更新时间。
- 交互：新建书、打开书（跳 `book.html`）、偏好设置弹窗（含「模型配置」入口行与「账号」占位行）。

### book.html（工作台，核心）
- `localStorage['ainovel.book.v2']`，状态对象 `S`（含 `view:'outline'|'write'|'preview'`、`selVol`、`selCh`、`fs`、`lh`、`chTab`、`expanded`、`archiveAiSummary`）。
- 三大视图由 `.modnav` 切换（设定 / 写作 / 预览）。
  - **设定**：卷/章树（可展开、选中）、右侧面板（章纲、提示词等）。
  - **写作**：左侧章树 + 正文编辑器。正文用 `contenteditable`（`.editor`，宋体 17px、行高 2.0、max-width 680px 居中）。
  - **预览**：只读排版视图。
- **删章分级确认**：删除章节时弹 `#modalDelete`，内部 `#delInventory` 用 `.inv-chip` 列出该节点实际包含的内容（章纲 / 提示词 / 正文 / 空节点），有内容的章显示警示，空节点直接删——既允许删有内容的章，又做好防误删。
- **只读章 AI 入口**：归档章正文只读（`.editor` 上 `contenteditable=false` + 只读横幅），写作视图对归档章显示「AI 解锁/续写」入口，弹 `#modalUnlock` 确认后解锁。
- **归档时 AI 摘要**：这是**每本书的配置**（不是全局模型配置）。在偏好弹窗里以 `.seg[data-od-id="seg-archsum"]` 呈现，绑定 `S.archiveAiSummary`；开=归档时用 AI 生成章节摘要，关=截取正文开头作摘要。
- 偏好弹窗里所有 `.seg` 必须用 `data-od-id` 映射状态（`seg-fontsize`→`S.fs`、`seg-lineheight`→`S.lh`、`seg-archsum`→`S.archiveAiSummary`），**禁止按 index 映射**。

### model-config.html（模型配置）
- `localStorage['ainovel.apiconfigs']`。供应商 8 个（**无 Gemini**）：openai / anthropic / deepseek / glm / kimi / qwen / ollama / openai-compat（「OpenAI 兼容」）。
- 连接状态 7 种：ok / auth_error / timeout / network_error / rate_limited / unknown / untested，映射到徽标与卡片描边色（`CARD_BORDER`）。
- 页面结构：`.page-head`（标题 + 添加按钮）→ `.notice`（墨绿提示条）→ `.panel` 用量统计（`.stat-tiles` 三块 + `.usage-row` 条形列表）→ `.cards` 配置卡网格。
- 配置卡：`.cfg-top`（图标 + 名称 + Base URL + 状态徽标）、掩码 Key（`.keyline`）、模型 chips、底部「测试连接 / 编辑 / 删除」。
- 交互：添加/编辑弹窗（选供应商自动填 Base URL；Ollama 无需 Key）、测试连接、删除确认 + 撤销 toast。
- 掩码 Key：`sk-` 前缀 + `••••••••` + 末 4 位（`maskKey()`）。

## 7. 硬性避坑（踩过的坑，务必遵守）

1. **CSS Grid 等宽列**：`grid-template-columns: repeat(N, 1fr)` 会因内容里最长的不可断词把某一列撑宽，导致整页对不齐。**必须用 `repeat(N, minmax(0, 1fr))`**。本目录四个文件的所有网格（卡片、统计、供应商格、用量条）都已改好，新增网格照此办理。
2. **图标归一化**：见 §5，否则图标视觉大小不一致。
3. **jsdom 测试注意**：`contenteditable` 在 jsdom 里是 property 不是 attribute，断言要读 `.contentEditable` 属性而非 `getAttribute('contenteditable')`；弹窗关闭是 200ms 延迟 `hidden`，测试要等 >200ms。
4. **`data-od-id`**：每个可交互/有语义的模块都要挂，命名用 kebab-case（如 `modal-config`、`seg-archsum`、`btn-add-key`），供 OpenDesign 预览与测试定位。
5. 每个 HTML 都是**自包含单文件**（内联 CSS + vanilla JS，无构建、无外部依赖、无 emoji）。

## 8. 验证

冒烟测试用 Open Design 自带的 Node 运行时执行 jsdom 脚本：

```bash
OD_NODE_BIN="/Applications/Open Design.app/Contents/Frameworks/Open Design Helper.app/Contents/MacOS/Open Design Helper"
"$OD_NODE_BIN" /tmp/odcheck/test-model-config.js   # 21/21
"$OD_NODE_BIN" /tmp/odcheck/test-*.js
```

改完任何页面至少重跑对应测试确认无回归。改动大时，在浏览器里把黄金路径（新建/编辑/删除/撤销、视图切换、弹窗开关）和边界都点一遍。

## 9. 历史记录

`spec-review-report.md` 是早期 23 项 spec 核对清单（9 项 spec 对 / 8 项代码对 / 3 bug / 3 次要），以及两个已落地改动（删章分级确认、只读章 AI 入口）。它只作历史留档，**以本文件为准**。

## 10. 已知遗留（open item，勿当作已完成）

以下条目**尚未解决**，复刻或改代码前视为待办，不要默认已处理。多数属 React 代码库层，HTML 原型未建模。

**真 bug（React 代码库层）**
1. 右栏 AI 无锁态门控：章归档后正文只读，但右栏「继续写作 / 润色 / 扩写」仍可点、可写入只读章——`RightToolbar` 缺与 `ChapterEditor` 相同的 `locked` 判断。
2. 「AI 触发自动切编辑」路径不存在：spec 要「点 AI 自动从只读切回编辑」，代码没有这条路径。
3. 版本历史入口错位：完整版本历史在正文 tab 内的整页版，右栏只有前 5 条简版，与 spec「右栏五块」结构对不上。

**轻微措辞 / 不一致（可顺手统一）**
- 序号混用：树里中文数字「第三卷」 vs 卷页 meta 阿拉伯「第 3 卷」。
- 「+建章」只在已有子节点的卷 hover 出现，空卷建章得走顶部按钮，体验割裂。
- 设定页「变更历史 / 用量统计」面板标题 vs spec「变更时间线 / 本书用量面板」。

（核对报告第一节～第四节其余条目属 React 代码库层，`book.html` 原型未建模；改真实代码前以 `ai-novel` 当前源码复核对应条目。）
