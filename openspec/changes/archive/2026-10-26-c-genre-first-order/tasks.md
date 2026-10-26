# c-genre-first-order — Tasks

## 1. 前端：顺序与落点

- [x] 1.1 `SettingsView.tsx`：`SETTINGS_ITEMS` 前两项对调为 题材→简介，顺序注释补 2026-10-26 拍板；`normalizePanel` 默认回落改 `"genre"`；homeSeq 相关注释改「第一项『题材』」；题材右栏脚注补空简介口径。验证：`grep -n "intro.*genre\|genre.*intro" src/components/novel/workbench/SettingsView.tsx` 目视复核数组序。
- [x] 1.2 `CreateProjectModal.tsx`：按钮「创建，去写简介」→「创建，去定题材」；提示语对调；注释补拍板。验证：vitest 建书相关用例绿（如有）。
- [x] 1.3 `NovelWorkspace.tsx` 注释口径（默认面板第一项）、`CharacterManager.tsx` 空态引导「01 简介」→「02 简介」。验证：`grep -rn "01 简介" client/frontend/src` 仅剩历史归档类注释。

## 2. 后端：题材 AI 兜底与 readiness 同序

- [x] 2.1 `settings/ai_router.py` `generate_field`：genre 路径简介为空时不再 400，注入空简介声明兜底。验证：pytest 新增用例（空简介 → 200 且提示词含声明文案）。
- [x] 2.2 `workflow/readiness.py` `READINESS_CHECKERS`：synopsis/genre 两行对调＋注释更新。验证：`pytest tests/test_readiness.py` 全绿。

## 3. 测试对齐

- [x] 3.1 e2e 建书按钮文案全量替换（约 28 个 spec 的「创建，去写简介」→「创建，去定题材」）。验证：`grep -rn "创建，去写简介" client/frontend/e2e | wc -l` 为 0。
- [x] 3.2 顺序断言更新：`settings-forms.spec.ts`（前两步用例翻转＋题材确认→前进到简介；旧「新顺序：题材→世界」注释清理）、`creation-flow.spec.ts`（hint 断言、确认前进注释）、`ui-spec-parity.spec.ts`（默认 h2 简介→题材）、`design-parity-book.spec.ts`（默认落点等 story→等 genre 响应＋注释）。验证：目标 e2e 文件定向跑绿。
- [x] 3.3 vitest：`CharacterManager.bootstrap.test.tsx`「02 简介」断言同步；`SettingsView.*`、`introPanel.guide` 回归。验证：`vitest --coverage` 全绿。
- [x] 3.4 后端用例：空简介题材 AI 兜底（新增）＋既有 ai_router / readiness 回归。验证：`pytest` 全量绿。

## 4. 收尾

- [x] 4.1 `openspec validate --change c-genre-first-order` 通过；主 spec 的 intro-genre-settings Purpose 行在 sync 时同步为「① 题材 → ② 简介」。
- [x] 4.2 PR：实现＋delta sync＋归档随 PR 走（openspec-archive-in-implementation-pr 规矩）。
