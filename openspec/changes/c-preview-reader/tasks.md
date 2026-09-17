## 1. 原型收编与设计登记（先行）

- [x] 1.1 把 `docs/design-c/drafts/preview.html` 收编为 `docs/design-c/prototypes/preview.html`，并同批完成设计稿修订（每项均为 ADJUSTMENTS 待登记项）：① 删除章纲三态 dot，目录行改 `.pill` 成稿状态标签（拟定/草稿/已归档，已归档优先；设计稿 `statusText` 的第四态「待写」移除）；② 原两栏折叠树下线（扁平目录）；③ 夜间/护眼主题补 `background: var(--pv-bg)` 消费规则（设计稿只定义变量无消费）；④ 卷头拼串 bug 修正（`'第 '+v.name` → `v.name`）；⑤ 目录头补「不含旧稿」说明；⑥ 阅读配置持久化（设计稿只持久化选中章）；⑦ 右栏「导出成稿」卡改名「下载成稿」且**不进本 change 基线截图场景**（弹层与入口像素基线归 change `c-manuscript-download` 修订后落位）；⑧ token 新名映射到现有 token（`--accent-ink`→`--accent-strong`、`--hl`→`--fg-soft`、`--faint`→就地 color-mix、`--radius-sm|pill`→`--radius`/999px）；护眼/夜间主题的固定 oklch 字面量作为登记例外保留
- [x] 1.2 在 `prototypes/ADJUSTMENTS.md` 登记上述 ①-⑧ 全部偏差（含「上一章/下一章」作为翻页控件例外记入按钮动词口径的说明、`#viewPreview` 两栏段自 book.html 下线）
- [x] 1.3 `client/frontend/scripts/design-vocab.mjs` 的 `strictGlobs` 显式加入 `prototypes/preview.html`（逐文件枚举，漏加 = 免检空转），核对 server 端 `scripts/design-vocab.mjs` 无需同步（C端原型 glob 仅在 C端）；`npm run design:lint` 通过
- [x] 1.4 parity 场景代码：把 `e2e/design-parity-book.spec.ts` 的 preview 场景迁移为新屏场景（`design-parity-preview`，对齐其打桩与 pageSettled 模式）；本阶段只迁移代码不断言像素（实现完成后再验）

## 2. 阅读偏好（数据层，先于 UI）

- [x] 2.1 `lib/prefs.ts` 新增 `getBookReadingPrefs/setBookReadingSize/…`（key `pref.book.{pid}.read.{size|line|font|theme}`，默认 中号·衬线·舒适·白纸，白名单校验 + try/catch 回退），并在 `__tests__` 补单测：默认值、往返读写、非法值回退默认
- [x] 2.2 补一条回归断言：写阅读偏好后，`getBookFontSize/getBookLineHeight`（写作偏好）保持原值不变 —— 验证「预览配置不污染写作视图」

## 3. PreviewView 三栏重写

- [x] 3.1 目录列：扁平全书目录（**目录头**「主线 N 章 · N 卷 · 不含旧稿」、卷分组头含卷名与章数、章节行含 `nodeLabel` 题名/字数/状态标签——已归档优先），删除折叠态与章纲 dot；`word_count` 取 `WorkbenchChapter` 既有字段不重算
- [x] 3.2 阅读列：顶部「上一章 / 下一章」+ 定位行，正文前卷签/大标题/元信息行（第 N 章 · 成稿状态 · 字数 · 旧设定角标）；首末章按钮 `aria-disabled`；**保留 initialRef 失效回退链（selRef → initialRef → 首章）**；切章仍为预览本地态（不回写写作视图）
- [x] 3.3 右栏：阅读配置四组分段控件（字号/字体/行距/主题，读写 `read.*` 偏好）+ 全书概览卡（章节数/总字数/归档·草稿·拟定计数）+ 空态给去写作视图的出口；右栏只读改配置、不触发 `volumes` 重取
- [x] 3.4 `design/book.css` 新增 `.view.on.preview-v` 自有栅格与断点（≤1024 藏右栏、阅读区保底 ≥40ch、行长上限 66ch；≤640 单列），不触碰 `two-col`/`three-col` 断点；新增 `.pv-*` 类（目录行/阅读排版/配置卡/主题三档含 `--pv-bg` 消费规则），配色全走现有 token
- [x] 3.5 `NovelWorkspace.tsx` 挂载与标签口径同步（「预览」）；确认 `PreviewView` 仍只在 `archives` 视图挂载、写作视图常驻不受影响；核对并清理旧预览专属死 CSS（`.preview-head`/`.pv-title`；`.view.on.two-col` 先核对是否唯一消费者是旧 PreviewView，是则删）
- [x] 3.6 改写 `e2e/settings-forms.spec.ts` 预览段断言（约 709-756 行）：`.pv-title`→新定位行/大标题 testid、tree-head 文案、`.arch-tag`→pill 标签、空章文案、**重进预览回初始章（initialRef 语义保留）**
- [x] 3.7 新增 `__tests__/previewReader.test.tsx`：三栏渲染、目录头计数、目录行状态标签（无正文→拟定 / 有正文未归档→草稿 / 归档（含字数 0）→已归档）、首末章按钮禁用、切章不调用写作侧选中、initialRef 章已删回退首章、阅读配置改后 UI 生效且落 localStorage —— `npx vitest run` 全绿
- [x] 3.8 `npx tsc --noEmit` 通过；`npm run design:lint` 通过

## 4. 端到端与门禁

- [x] 4.1 `e2e/workbench-features.spec.ts`（或新 spec）补预览场景：进入预览 → 三栏可见 → 点目录切章 → 上一章/下一章跨卷 → 改字号/主题后离开再进仍在 → 断言写作视图选中章未变
- [x] 4.2 本机 docker 栈跑受影响 e2e：`settings-forms.spec.ts`（已改写）、`design-parity-book.spec.ts`（场景已迁移）、`free-writing-flow` / `modals-pr5` 的 modnav 文案断言，再跑全量确认无回归
- [x] 4.3 `npm run design:check` 全绿（<0.2%，含新 preview 场景；基线=入库的原型，baselines/ PNG 不入库）；回归小节注明 `design-cross` 不需跑（本 change 不触共享段）
