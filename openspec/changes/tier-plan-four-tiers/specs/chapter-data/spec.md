## MODIFIED Requirements

### Requirement: Free-tier chapter editor

- The system SHALL refactor `components/novel/ChapterEditor.tsx` so that the AI surface is hidden on free tier while the code remains (N14/P0-6): the prompt tab, 「AI 写本章」, and RightToolbar wiring SHALL be wrapped in `<TierGate feature="ai-generate">`; 「质量检查」 SHALL NOT be gated（纯本地规则检查，后端撤会员门后全档可用——tier-plan-four-tiers 拍板）：its control SHALL stay visible/usable for all tiers。
- The prose body SHALL remain a `textarea` in this phase (ProseEditor is a later change).
- `onAIStateChange` SHALL NOT be wired in the free tier (the parent RightToolbar render chain is removed).
- Save logic SHALL move to `useChapterData`; the `ChapterEditorHandle` SHALL be retained with AI methods degraded/no-op on free tier.
- The manual save + 1.5s autosave SHALL both be available on free tier; a save failure SHALL show a 「重试」 action.

#### Scenario: Free tier hides AI controls

- Given a free-tier user editing a chapter
- When the editor renders
- Then no 「AI 写本章」 or prompt tab control is present, but 「质量检查」 stays usable（纯本地检查，全档免费）, and the textarea, manual save, and autosave work

#### Scenario: Pro tier restores AI path

- Given a paid user editing a chapter
- When the editor renders
- Then the AI write/prompt controls are present as before; 「质量检查」 remains available（不再随 ai-generate 门控）

#### Scenario: Archived chapter is read-only

- Given an archived chapter being edited
- When the editor renders
- Then the prose area is read-only and an archive indicator is shown
