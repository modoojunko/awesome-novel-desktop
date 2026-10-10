# c-chapter-default-words

## Why

内测反馈 #10（「【章节默认字数 2500】这里需能修改（手动设定）」）逐条核对后的残余缺口
（issue #782）：逐章「本章目标字数」可改，但藏在章纲编辑折叠区（用户没找到）；而
**全局默认 2500 是硬编码**——前端 `useChapterData.ts:83 DEFAULT_TARGET`、
`chapterForm.ts`/`OgPane.tsx` 三处字面量，后端 `write/chapter_writer.py:44
WORD_TARGET_DEFAULT`。作品偏好弹窗（本书偏好）只有字号/行距/归档摘要，没有这一项——
想「全书按 3000 字一章写」的用户只能逐章手填。

## What Changes

- **作品偏好新增「章节默认字数」**（per-book，范围沿用 500-6000，缺省 2500）：
  - 后端：新 KV 键 `book-prefs`（`settings/book-prefs.yaml` → project_settings KV，
    仿 threads/style-quant 专用键，不进 `PATH_TO_KEY`）＋专用端点
    `GET/PUT /api/novels/{id}/settings/book-prefs`（字段缺省＝无操作；
    null/空＝清除设置；越界/非整数 400）。
  - 生成链：`build_chapter_context` 章纲未填 `word_target` 时按本书偏好兜底
    （夹取守卫 `clamp_word_target(value, default=...)` 同源）；未设置＝2500，
    **存量项目零迁移、行为不变**。
  - 前端：`lib/chapterTarget.ts` 单源模块（区间/缺省常量＋localStorage 展示缓存＋
    变更订阅＋后端读写）；本书偏好弹窗加一栏数字输入，保存时**先写后端再收尾**
    （写失败保持弹窗可重试）。
- **文案/校验/进度目标跟随**：章纲「留空默认 XXX」提示、placeholder、查看态「默认
  XXX」与保存前拦截提示（`ogFormIssues`）都改读本书偏好（缺省仍 2500）；
  工作台进度目标兜底（`useChapterData` 的 `targetWords`）同源。
- **逐章优先不变**：章纲填了字数目标仍以章纲为准（现状语义不动）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：新增 Requirement「本书偏好弹窗章节默认字数」（本书偏好弹窗的 UI 与
  读写贯通契约）。
- `prose-writing`：MODIFIED Requirement「按目标字数生成」——「未填按既有默认值兜底」
  明确为「按本书偏好『章节默认字数』兜底（未设置＝2500）」；MODIFIED Scenario
  「未填目标走默认」。

## Impact

- 代码（后端）：`settings/book_prefs_model.py`（新，常量与归一单源）、
  `settings/book_prefs_router.py`（新）、`filesystem/paths.py`（专用键路由）、
  `main.py`（路由注册，先于 `/settings/{type}` 兜底）、
  `write/chapter_writer.py`（常量改从 book_prefs_model 引入 + 未填章取本书默认）。
- 代码（前端）：`lib/chapterTarget.ts`（新，覆盖率契约登记）、
  `components/novel/BookPrefsModal.tsx`、`components/novel/workbench/OgPane.tsx`、
  `components/novel/workbench/chapterForm.ts`、
  `components/novel/workbench/ChapterWorkspace.tsx`、`hooks/useChapterData.ts`。
- 测试：后端 `tests/test_book_prefs.py`（新）、`tests/test_chapter_writer_context.py`
  （未填章取本书默认的集成钉）、`tests/test_db_storage.py`（专用键路由）、
  `tests/test_shared_constants_parity.py`（前后端区间/缺省对拍）；
  前端 `__tests__/chapterTarget.test.ts`（新）、`__tests__/ogWordTarget.test.tsx`（新）、
  `chapterForm.promptGrid.test.ts`（动态提示文案）；
  e2e `modals-pr5.spec.ts`（本书偏好弹窗改字数→后端落库＋回读）。
- 用户面：改「章节默认字数」后，新建章纲留空即按新默认生成；未设置的用户行为不变。
- **Design Impact**：受影响端＝C端（纯 C端，不触两端共享段：`.pref-row` 是 C端
  base.css 自有类，S端 无本书偏好弹窗）。受影响弹层＝工作台「设置 · 写作偏好」。
  对象状态无新增（普通设置行，无四态/门控语义）。**原型先行缺口**：`book.html
  #modalPrefs` 尚未含该行、`ADJUSTMENTS.md` 未登记（本会话硬约束＝只改 client/，
  不改 docs/）——待设计侧会话补原型与该登记项后，`design:check` 像素基线再对齐。
