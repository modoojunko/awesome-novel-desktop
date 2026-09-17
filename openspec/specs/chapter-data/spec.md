# chapter-data Specification

## Purpose
TBD - created by archiving change 004-free-workspace. Update Purpose after archive.

## Requirements

### Requirement: useChapterData hook

- The system SHALL provide `hooks/useChapterData.ts` exposing `{ chapter, prose, summary, status, isDirty, saveState, wordCount, targetWords, setTargetWords, save, retry, archive, unarchive, loading, error }`.
- On load, the hook SHALL fetch the chapter (`GET /novels/{projectId}/chapters/{ref}`) and populate prose / outline summary / status.
- Auto-save SHALL debounce at **1500ms** after the last content change (N8: reduced from the legacy 3000ms).
- The save state SHALL be one of exactly four: `autosaving | saved | unsaved | failed`; the failed state SHALL expose a `retry()` action.
- `wordCount` SHALL count non-whitespace Chinese characters, consistent with the backend `/tree` metric (B5).
- `targetWords` SHALL persist (localStorage or chapter metadata) and be adjustable via `setTargetWords`.
- When no target has been set, `targetWords` SHALL fall back to **2500** — the backend write-pipeline default — so the UI progress display and text generation share one default.
- `isDirty` SHALL be `prose !== initialProse || summary !== initialSummary || status !== initialStatus`.
- The hook SHALL flush unsaved changes on unmount or chapter switch (no lost-window).
- The save endpoint SHALL prefer `PUT .../chapters/{ref}/prose` with body `{prose}` (backend #12); while that endpoint is absent it SHALL degrade to `PUT /chapters/{ref}` with the full merged body.

#### Scenario: Debounced autosave after idle
- Given a chapter with prose loaded and a change typed
- When the user stops typing for 1.5 seconds
- Then the chapter auto-saves and the save state transitions to `saved`

#### Scenario: Save failure shows retry
- Given the save request rejects
- When the save finishes
- Then the save state is `failed` and a retry action is available

#### Scenario: Word count counts Chinese chars without whitespace
- Given prose `"你好 世界\n\n。"`
- When `wordCount` is computed
- Then it equals 5

#### Scenario: Default target aligns with generation pipeline
- Given a chapter with no stored target value
- When the hook initializes `targetWords`
- Then it equals 2500, matching the backend generation default

#### Scenario: Flush on unmount
- Given a chapter with unsaved edits
- When the editor unmounts or the chapter changes
- Then the pending edits are flushed to the server

### Requirement: Free-tier chapter editor

- The system SHALL refactor `components/novel/ChapterEditor.tsx` so that the AI surface is hidden on free tier while the code remains (N14/P0-6): the prompt tab, 「AI 写本章」, 「质量检查」, and RightToolbar wiring SHALL be wrapped in `<TierGate feature="ai-generate">`.
- The prose body SHALL remain a `textarea` in this phase (ProseEditor is a later change).
- `onAIStateChange` SHALL NOT be wired in the free tier (the parent RightToolbar render chain is removed).
- Save logic SHALL move to `useChapterData`; the `ChapterEditorHandle` SHALL be retained with AI methods degraded/no-op on free tier.
- The manual save + 1.5s autosave SHALL both be available on free tier; a save failure SHALL show a 「重试」 action.

#### Scenario: Free tier hides AI controls
- Given a free-tier user editing a chapter
- When the editor renders
- Then no 「AI 写本章」, prompt tab, or 「质量检查」 control is present, but the textarea, manual save, and autosave work

#### Scenario: Pro tier restores AI path
- Given a paid user editing a chapter
- When the editor renders
- Then the AI write/quality-check/prompt controls are present as before

#### Scenario: Archived chapter is read-only
- Given an archived chapter being edited
- When the editor renders
- Then the prose area is read-only and an archive indicator is shown

### Requirement: 章档案新增列的持久化与导出（加键兼容）

- `chapters` SHALL 增加两列并经幂等 ALTER 对存量库升级：`style_shadow`（JSON 文本，默认 `{}`——本章文风影子）与 `ghost_of`（可空字符串——旧稿支线的来源章号）。
- 章装配（assemble_chapter）SHALL 输出 `style_shadow`（解析后的对象；损坏 JSON 回落 `{}` 且不阻塞读取）与 `ghost_of`（set 时输出）；两者 SHALL 随章档案导出并随导入回写（加键兼容：缺失键按默认值处理）。
- 既有章读取契约 SHALL NOT 因新增键破坏：未设置影子/非支线章的装配结果语义与字段等价于新增前。

#### Scenario: 影子随导出导入往返
- **WHEN** 某章设置了影子行后导出并重新导入
- **THEN** 该章的影子行原样保留

#### Scenario: 损坏影子不阻塞读取
- **WHEN** 某章 style_shadow 存了非法 JSON
- **THEN** 章装配成功，shadow 为空对象

#### Scenario: 支线来源随章保留
- **WHEN** 某章转入旧稿支线（ghost_of=目标章号）后导出
- **THEN** 导出包含 ghost_of，导入后支线关系保留

### Requirement: 重写旧稿支线章（后缀 ref）

- 重写产生的旧稿支线章 SHALL 以 `{源章 ref}-r{sha256(正文)[:8]}`（内容寻址）为 ref 落库，`ghost_of` 指向源章 ref；同一章不同内容重写产生多个旧稿，同内容重放命中既有 ref（幂等，不重复落）。
- 该支线章 SHALL 携带：标题（源章当时标题）、正文（快照全文）、`ghost_of`；章纲/收尾等派生数据 SHALL NOT 复制（旧稿是文稿快照，不是第二份主线数据）。
- 装配与导出契约 SHALL 与既有支线章一致（`ghost_of` 加键直出、随导出包往返、导入 ref 重绑规则不变）；书级统计（字数/章数/归档数）与主线端点 SHALL 继续排除支线章（既有口径，零改动）。
- 后缀 ref SHALL NOT 参与 `-ch-(\d+)` 章号解析链的正章匹配（解析取最后一段 `-ch-N` 之后再遇 `-r` 后缀的须按支线处理；实现侧统一走 ghost_of 判定，不做数字猜测）。

#### Scenario: 多次重写产生多个旧稿
- **WHEN** 同一章先后以不同内容重写两次
- **THEN** 旧稿支线出现该章两个快照（内容寻址 ref 不同），均可只读查看

#### Scenario: 同内容重放幂等
- **WHEN** 对同一章以未变更的正文重复发起重写
- **THEN** 命中既有旧稿 ref，不新增快照（ghost_created=false）

#### Scenario: 旧稿随导出包往返
- **WHEN** 含旧稿支线章的书导出并重新导入
- **THEN** 旧稿章与 `ghost_of` 关系保留，主线统计不因旧稿变化
