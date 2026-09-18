## Why

「预览」目前是只读通读页：左树折叠、正文排版写死（字号/行距只能在写作视图或弹窗里改），没有上一章/下一章，也不显示任何字数与状态信息。作者完稿前要检查通读效果，需要能看到每章字数、知道哪些章还没写、能顺手翻页、能按自己的阅读习惯调字号字体行距与底色——这些在 `docs/design-c/drafts/preview.html` 里已画好。

## What Changes

- **预览工作台改三栏**：左＝全书目录（卷头 + 章节行：章号/题名/字数/状态标签），中＝阅读区（顶部「上一章 / 下一章」+ 定位位；正文前卷签 + 大标题 + 元信息行 第 N 章 · 状态 · 字数），右＝阅读配置 + 全书概览。
- **阅读配置独立**：字号三档、字体三档（衬线/黑体/楷体）、行距三档、主题三档（白纸/护眼/夜间）。**书级、只作用预览**——不读也不写写作视图的字号/行距偏好（`pref.book.{pid}.fs|lh` 保持不动），另立 `pref.book.{pid}.read.*`；默认值 = 中号 · 衬线 · 舒适 · 白纸。
- **目录行状态改用成稿口径**：显示 拟定（章纲未完成）/ 草稿（有正文未归档）/ 已归档 + 字数；预览侧不再渲染章纲三态 dot（章纲细节属于写作视图，通读场景只需要成稿状态）。
- **全书概览卡**：章节数、总字数、归档/草稿/拟定计数。数据全部来自已在内存的 `WorkbenchVolume.chapters`（含 `word_count`/`has_prose`/`archived`），**零新增接口**。
- 保持既有约束：预览选中章与阅读配置均为**预览本地态**，离开即弃、不回写写作视图（ADJUSTMENTS #12/#13 的脏正文保护不破）。

## Capabilities

### New Capabilities

- `preview-reader`: 预览阅读器的行为契约——三栏结构、目录行信息（字数/状态标签）、章级导航与元信息、阅读配置（四轴 × 三档、书级持久化、默认值、只作用预览）、全书概览统计。

### Modified Capabilities

- `workbench-3-label`: 「预览小说」打开的视图语义从「归档预览」改写为「阅读预览 + 阅读配置」；nav 文案与本视图内容对齐。
- `novel-workspace`: PRO container 条款里的导航 label 字面量「预览小说」同步改为「预览」（纯文案对齐，行为不变）。
- `topbar-nav-merge`: 顶栏 label 字面量同步改「预览」；已退役的 `ArchivePage` 归档浏览器条款（归档计数标题 + 搜索栏）改写为「由 preview-reader 三栏阅读器取代，SHALL NOT 复活」。
- `design-system`: 新增原型组件词汇（`.pv-card` / `.pv-seg` / `.pv-ch` 目录行等）需登记；预览目录行的对象状态表达从三态 dot 改为状态标签（成稿口径），需更新「同一对象两处呈现」的场景口径。

## Design Impact

- 受影响端：**仅 C端**（`client/frontend`）。
- 受影响屏/弹层：书工作台「预览」视图（`PreviewView`）；不新增弹层（下载成稿弹层属 change `c-manuscript-download`）。
- 对象状态（对照状态语言总表）：章节对象新增一种呈现口径——成稿状态标签 `拟定 / 草稿 / 已归档`（由 `status` 派生），与写作视图的三态 dot（章纲缺口）并存但不同屏；无新增状态词。
- 是否触碰两端共享段：**否**（不落 `base.css` 共享 `@cross` 段；新增类只进 `book.css`）。原型新增的 `--accent-ink` / `--hl` / `--faint` / `--radius-sm` / `--radius-pill` 若确需入库，按标准层流程登记，不允许实现侧私开。
- 是否需要原型先行：**要**。`docs/design-c/drafts/preview.html` 收编为 `docs/design-c/prototypes/preview.html`（**原型即基线，入库**；`baselines/` 的比对 PNG 才是本地产物不入库），成为 parity 基线；收编时同批完成设计稿修订：下载弹层区域的归属与文案（「导出成稿」→「下载成稿」）随 change `c-manuscript-download` 修订，本 change 基线先按收编稿落位；`book.html` 的 `#viewPreview` 两栏预览段同步下线，`design-parity-book` 的 preview 场景迁移到新屏，均在 ADJUSTMENTS 登记。
- 设计工件产出者：设计侧会话已产出 `drafts/preview.html`；实现侧负责收编与登记。

## Impact

- 代码：`client/frontend/src/components/novel/workbench/PreviewView.tsx`（三栏重写）、`lib/prefs.ts`（新增 reading 偏好读写）、`design/book.css`（新增 `.pv-*` 类）、`NovelWorkspace.tsx`（挂载 props 与视图标签口径）。
- 数据面：无接口改动；复用 `WorkbenchChapter` 已有字段。
- 基线：`docs/design-c/prototypes/` 新增 `preview.html` 与 ADJUSTMENTS 登记；`npm run design:check` 需为新屏建基线。
- 测试：新增预览三栏/导航/配置持久化的 vitest 与 e2e 断言。
