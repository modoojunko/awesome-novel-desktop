# chapter-data 增量

## MODIFIED Requirements

### Requirement: useChapterData hook

- The system SHALL provide `hooks/useChapterData.ts` exposing `{ chapter, prose, summary, status, isDirty, saveState, wordCount, targetWords, setTargetWords, save, retry, archive, unarchive, archiveJob, loading, error }`.
- On load, the hook SHALL fetch the chapter (`GET /novels/{projectId}/chapters/{ref}`) and populate prose / outline summary / status.
- Auto-save SHALL debounce at **1500ms** after the last content change (N8: reduced from the legacy 3000ms).
- The save state SHALL be one of exactly four: `autosaving | saved | unsaved | failed`; the failed state SHALL expose a `retry()` action.
- `wordCount` SHALL count non-whitespace Chinese characters, consistent with the backend `/tree` metric (B5).
- `targetWords` SHALL persist (localStorage or chapter metadata) and be adjustable via `setTargetWords`.
- When no target has been set, `targetWords` SHALL fall back to **2500** — the backend write-pipeline default — so the UI progress display and text generation share one default.
- `isDirty` SHALL be `prose !== initialProse || summary !== initialSummary || status !== initialStatus`.
- The hook SHALL flush unsaved changes on unmount or chapter switch (no lost-window).
- The save endpoint SHALL prefer `PUT .../chapters/{ref}/prose` with body `{prose}` (backend #12); while that endpoint is absent it SHALL degrade to `PUT /chapters/{ref}` with the full merged body.
- `archive()` SHALL 改为受理语义：受理成功 SHALL 只置归档任务态 `archiveJob`（提取中/失败/跳过/完成），SHALL NOT 乐观置 `status: "archived"`；`chapter:archived` 事件 SHALL 只在轮询探测到服务端真置位后派发；失败 SHALL 经 `archiveJob` 或归档失败事件暴露（含重试入口）。
- 归档任务进行中（archiveJob＝提取中）SHALL 向消费方暴露锁定信号：正文编辑与归档/取消归档入口禁用；任务态 SHALL 以服务端为准，切章返回后从服务端恢复，SHALL NOT 只存在于内存。

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

#### Scenario: 受理不等于归档完成
- Given 本书已配置模型，作者点归档且受理成功
- When 受理响应返回
- Then `status` 保持原值，`archiveJob` 为提取中，树/徽标不变；服务端真置位后才派发 `chapter:archived` 并刷新 status

#### Scenario: 归档失败暴露重试
- Given 提取四域中一域失败
- When 轮询读到失败终态
- Then `archiveJob` 为失败（含原因），章保持未归档，UI 出现重试入口
