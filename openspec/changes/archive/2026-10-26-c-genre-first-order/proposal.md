# c-genre-first-order — 设定前两步重排：题材第一、简介第二

## Why

写小说的第一步是定题材，题材定了才知道简介往哪个方向写；现流程「① 简介 → ② 题材」与创作直觉相反（用户 2026-10-26 拍板：「作家写小说，先定题材，才想如何写简介的」）。现顺序是 2026-09-11 `genre-signup-redesign` 特意对调的，本次基于同一用户的新拍板再翻回来——但不能再当 revert 做：题材面板如今带 01 题材目录与右栏 AI 四问，其中 AI 四问在后端被简介硬门（简介空 → 400），顺序对调后新书第一屏 AI 全死，必须同批解除。

## What Changes

- 设定前两步重排为 **① 题材 → ② 简介**：`SETTINGS_ITEMS` 对调，确认即前进顺序随之变为 题材 → 简介 → 世界 → …；新书进书默认落在题材面板。
- 建书弹窗文案随流程走：按钮「创建，去写简介」→「创建，去定题材」，提示语「先写简介、再定题材」→「先定题材、再写简介」。
- **BREAKING（后端行为）**：题材 AI 四问解除简介硬门——简介为空不再 400「No story premise found」，改为注入空简介声明，AI 仅凭题材目录＋书名＋候选池出候选（提示词模板不动、不发提示词包）。
- 设定项序号引用修正：角色面板空态引导与角色 AI 的「01 简介」文案改为「02 简介」（题材顶到 01）。
- 后端 `READINESS_CHECKERS` 同步对调（synopsis/genre），保持与左栏菜单同序的既有 SHALL。
- 简介三件套（体检/补缺失/润色）继续不注入题材——原「反向依赖会成环」拍板沿用，不随本次翻案。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `specs/intro-genre-settings/spec.md`: 前两步顺序与左栏菜单顺序两条 Requirement 对调（① 题材 → ② 简介）；题材 AI 四问新增「简介未写时仍可用」的 SHALL 与场景；Purpose 措辞同步。
- `specs/novel-workspace/spec.md`: 空书默认落设定的场景由「简介面板」改为「题材面板」。

## Impact

- 前端：`SettingsView.tsx`（SETTINGS_ITEMS／normalizePanel 默认落点／题材右栏脚注）、`CreateProjectModal.tsx`（按钮与提示文案）、`NovelWorkspace.tsx`（注释口径）、`CharacterManager.tsx`（空态引导文案）。
- 后端：`settings/ai_router.py`（generate_field 题材路径空简介兜底）、`workflow/readiness.py`（判定表顺序）。
- 测试：e2e 约 28 处建书按钮文案、settings-forms／creation-flow／ui-spec-parity／design-parity-book 的顺序与默认落点断言；vitest「01 简介」断言；后端新增空简介题材 AI 用例。
- 提示词仓：**不动**（模板占位符照旧，空简介兜底在后端注入）。
