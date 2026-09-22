## 1. 处置（实现已合并：PR #469，squash 91278140）

- [x] 1.1 `client/frontend/src/design/book.css`：`.e-empty` 段补回 `.be-mark` 档
      （mono 10px／字距 .14em／`--accent`／margin 0 0 10px），注释改写为四档角色
  - 证据：`design:lint` exit 0（严格范围无违规）；`be-mark` 出现在容器内构建产物的 CSS 里
- [x] 1.2 `client/frontend/src/components/novel/NovelWorkspace.tsx`：三张卡改挂
      眉标→`.be-mark`、提问→`.be-k`、说明→`.be-t`；`.be-desc` 退役（全仓已无使用点）
  - 证据：`git grep be-desc client/frontend/src` 为空；`home-progress` testid 保留在眉标上
- [x] 1.3 原型与登记：拆纲稿「实现侧类名角色」注释同步为 `be-mark 眉标 / be-k 主句 / be-t 说明 / be-acts 动作`；
      `prototypes/ADJUSTMENTS.md` 新增一节（问题、处置、影响面：`.e-empty` 只在中栏默认页用，不在 parity 基线）
- [x] 1.4 验证（真实栈走查，一次性）：三张卡档位顺序断言均为 `["be-mark","be-k","be-t","be-acts"]`；
      对照截图 `/tmp/card-1-empty.png`、`/tmp/card-2-landing.png`、`/tmp/card-3-home.png`、
      `/tmp/card-3-home-1024.png`（1024 无溢出：按钮行 506/558）

## 2. 回归

- [x] 2.1 `npx tsc --noEmit` 0 error；`npx vitest run` 77 文件 **754 passed**（无断言依赖这些类名，未改测试）；
      `npm run design:lint` exit 0
- [x] 2.2 隔离栈全量 e2e：**174 passed / 0 failed / 17 skipped（8.5min）**
- [x] 2.3 不触共享段复核：diff 仅 `book.css`（业务层）＋`NovelWorkspace.tsx`＋两份 docs；无 `base.css`、无 `server/`
      → 免 `design:cross`；未新增令牌/档位 → 免 `design-vocab.mjs` 回填

## 3. 归档

- [x] 3.1 增量（`design-system`）sync 进主 spec；`openspec validate --specs` 复核
- [x] 3.2 change 目录移入 `openspec/changes/archive/2026-09-22-c-empty-card-hierarchy/`
