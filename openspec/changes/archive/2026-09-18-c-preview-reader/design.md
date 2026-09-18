## Context

现状：预览视图是两栏（左树 + 中栏只读正文），选中章与排版都从既有状态借用——正文用 `.editor.fs-m.lh-comfy`，字号/行距来自写作偏好（`pref.book.{pid}.fs|lh`，见 `lib/prefs.ts`）。数据面已有 `WorkbenchChapter{word_count, has_prose, archived, stale}`，无需新接口。

约束（不可破）：
- ADJUSTMENTS #12/#13：预览是纯只读通读，选中为预览本地态——写作视图常驻挂载，隐藏态切章有正文脏丢风险。
- 原型先行 + parity：`docs/design-c/prototypes/*.html` 是像素基线，实现前先收编原型并在 ADJUSTMENTS 登记。
- 令牌纪律：实现只用现有 token，设计稿里的 `--accent-ink`/`--hl`/`--faint`/`--radius-sm`/`--radius-pill` 等新名不得私开。

## Goals / Non-Goals

**Goals:**
- 预览三栏成型、目录行带字数与成稿状态、章级导航可用。
- 阅读配置四轴三档、书级持久化、立即生效、只作用预览。
- 零新增接口、零影响写作视图状态。

**Non-Goals:**
- 下载成稿弹层与后端（属 change `c-manuscript-download`）。
- PDF 格式、阅读进度的跨设备同步、朗读/翻页动画。
- 章纲三态 dot 在预览中的保留——本 change 有意移除（见 Decisions）。

## Decisions

**1. 组件归属：重写 `PreviewView.tsx` 为三栏，不拆新页。**
预览仍是 `WorkspaceView` 的 `archives` 值，`NovelWorkspace` 只调整 props 与视图标签文案。避免新增路由态与壳层改动面。

**2. 字号/行距不共用写作偏好，另立 `pref.book.{pid}.read.*`。**
用户已拍板「预览独立」。写入/读取走 `lib/prefs.ts` 新增的四个 getter/setter（size/line/font/theme），默认值 中号 · 衬线 · 舒适 · 白纸。`pref.book.{pid}.fs|lh` 保持原样，写作视图与 `BookPrefsModal` 不受影响。
替代方案：复用写作偏好——被否，字号/行距的语义不同（写作是输入舒适度，预览是阅读舒适度），且主题若共用会污染编辑器。

**3. 阅读配置用样式类 + CSS 变量作用在预览根容器上，不用内联样式散点。**
中栏阅读区根节点挂 `pv-read`，由根容器上的 `pv-size-*` / `pv-line-*` / `pv-font-*` / `pv-theme-*` 类切换 CSS 变量。理由：与既有 `.editor.fs-*` 同思路、易测（断言类名而非计算样式）、主题三档可在一处定义正文底色与文字色。
替代方案：React 内联 style——配色要复算 color-mix，且 e2e 难以稳定断言。
注意：设计稿的主题类只定义了 `--pv-bg/--pv-fg/--pv-muted` 变量但没有任何规则消费 `--pv-bg`（夜间档会浅底浅字不可读）——收编时补 `background: var(--pv-bg)` 并在 ADJUSTMENTS 登记；护眼/夜间的 oklch 字面量按设计稿固定值登记入库（token 化例外，进 ADJUSTMENTS）。

**3b. 布局修饰类自立 `preview-v`，不搭 `.view.on.three-col` 便车。**
`book.css` 的 `three-col` 断点（≤1024 藏 `.col-ai`、≤860 塌两行）会劫持预览布局。`.view.on.preview-v` 用自有栅格（250px / minmax(0,1fr) / 264px）与自有 1024/640 断点，与既有 two-col/three-col 规则零冲突。旧预览专属的死 CSS（`.preview-head`/`.pv-title`，及 `.view.on.two-col` 若核对后确认唯一消费者是旧 PreviewView）随本 change 清理。

**4. 阅读配置不导致 `PreviewView` 重挂载。**
`volumes`/`outline` 等 props 变化触发重渲染时，配置从 localStorage 读一次进入 state，之后仅本地 set。避免每次切换都读盘与重建 DOM 子树。

**5. 目录行为：改为「扁平目录」，但保留卷分组头，折叠能力删除。**
设计稿的目录是常展开的。现状的 `collapsed` 折叠态删除，理由：通读场景需要全局视野，折叠会造成「章不可见」的错觉；且删除可减少一棵与设计稿不符的状态树。
替代方案：保留折叠默认展开——被否，多一处未被设计稿定义的状态。

**6. 章节状态标签由成稿状态派生，与写作视图三态 dot 并存但不同屏。**
映射：`has_prose=false` → 拟定；`has_prose && !archived` → 草稿；`archived` → 已归档。**不用 `outline_status`**。替代方案：沿用 `outline.chapterStatuses` 三态 dot——被否，通读场景里章纲缺口是噪音，状态口径应以「读者能读到什么」为准。此改动同时修改 `design-system` 与 `workbench-3-label` 的既有条款。

**7. 导航顺序用一次排序生成的扁平数组，而非每次现算。**
`useMemo` 产出 `flatChapters: {ref, v, c}[]`，`prev/next` 直接数组相邻元素；首/末章用 `aria-disabled` + 阻止点击（与设计稿一致，不隐藏按钮）。

**8. token 落位：设计稿新名映射到现有 token，不新开。**
`--accent-ink`→`--accent-strong`、`--hl`→`--fg-soft`、`--faint`→`color-mix(in oklch, var(--muted) 45%, var(--bg))` 就地写、`--radius-sm/pill`→现有 `--radius` 与 `999px`。理由：`docs/ux/design-language.html` 是标准层，私开新 token 会让 parity 与 design-vocab 双轨分裂；确需入库时按标准层流程单独登记。

**9. 卷章标题显示沿用 `nodeLabel`。**
目录行与阅读区标题继续走 `lib/nodeTitle.ts` 单源，避免中文数字口径再次分叉。

## Risks / Trade-offs

- [三栏在窄屏挤坏阅读区] → `.preview-v` 自有断点：1024px 收起右栏（阅读区保底 ≥40ch，行长上限 66ch），640px 单列上下排；不触碰既有 `two-col`/`three-col` 断点。
- [预览写 localStorage 与写作偏好同源读写互相覆盖] → 新 key 独立命名空间、独立函数，回归测试断言「改预览不改 `pref.book.{pid}.fs|lh`」。
- [status 口径与 `outline_status` 分叉导致两处状态不一致] → 目录行只显示成稿状态并删除 dot，视觉上不再并存两种状态语言；在 ADJUSTMENTS 与 spec 中明确写入「章纲细节归写作视图」。
- [移除折叠可能让超长书的目录难以定位] → 目录保持 `overflow:auto` 与既有滚动条；后续若需要再单独提「卷锚点/搜索」，不在本 change 夹带。
- [夜间主题影响既有像素基线] → 基线场景固定为默认（白纸）渲染，主题只在交互断言中出现，不进 parity 截图。

## Migration Plan

1. 设计侧收编 `drafts/preview.html` → `prototypes/preview.html`（**原型即基线，入库**；`baselines/` 比对 PNG 是本地产物不入库——分层口径见 `docs/design-c/README.md`），ADJUSTMENTS 登记全部偏差：删除折叠、新增成稿状态标签（`.tag`→`.pill` 族）、设计稿第四态「待写」移除、阅读配置持久化为新增（草稿只持久化选中章）、夜间主题补 `--pv-bg` 消费规则、卷头拼串 bug（`'第 '+v.name`→`v.name`）修正、token 新名映射、下载弹层区域归属 c-manuscript-download、目录头补「不含旧稿」说明。
2. `design-vocab.mjs` 的 `strictGlobs` 显式加入 `prototypes/preview.html`（逐文件枚举，不加 = 免检空转）；`npm run design:lint` 通过。
3. parity 场景代码：`design-parity-book.spec.ts` 的 preview 场景迁移为新屏场景（对齐其打桩模式）。
4. 实现：`lib/prefs.ts` → `PreviewView.tsx` 三栏 → `book.css` → `NovelWorkspace` props/标签 → e2e 断言（含 `settings-forms.spec.ts` 预览段改写）→ `design:check` <0.2%。
5. 回滚：本 change 无数据面改动，回滚 = 还原组件与样式，localStorage 残留新 key 不影响旧版本（旧版本不读它）。

## Open Questions

无。收编时卷分组头显示以修订后的原型渲染为准（`nodeLabel` 单源口径不变）。
