# c-chars-stale-reconfirm — 任务

## 1. 原型先行

- [x] 1.1 `docs/design-c/prototypes/character-settings.html`：新增 `gateSnapshot()`（后端 `gate_fingerprint` 同构简化版）＋`UI.snap`（确认/重新确认时快照）＋`isStale()`；`syncFoot` 的 note 与徽标/进度改按「内容有变」判定（不再拿「门禁不齐」当过期），补 stale 让位文案；确认按钮回执区分「已确认 / 已重新确认」。
      验证：`npm run design:lint` 全绿（严格扫描 31 文件 0 违规）
- [x] 1.2 `docs/design-c/prototypes/foreshadow-settings.html`：`#hookOkNote` 由静态句改三态（内容有变 / 已确认 / 未确认），未确认态文案不变（parity 首帧不受影响）。
      验证：同上
- [x] 1.3 `docs/design-c/prototypes/ADJUSTMENTS.md`：追加 `## c-chars-stale-reconfirm` 段（stale 模型、让位口径、徽标判据从「门禁不齐」改「内容有变」、演示可达性说明）。
      验证：条目落文末（2026-10-08）

## 2. 实现

- [x] 2.1 `hooks/useOnboarding.ts`：`charStale` 回填改**精确值**（`confirmed && stale`；catch 保持现值）＋抽出并暴露 `refreshCharStale()`；原 effect 改调它（deps 不变）。
      验证：`useOnboarding.test.tsx` 新增 3 例（精确清假 / 失败保持现值 / 无存档 false）全绿
- [x] 2.2 `NovelWorkspace.tsx` → `SettingsView.tsx` → `CharacterManager.tsx`：新增 `onRefreshConfirmState` 透传；`CharacterManager.reloadList` 成功后调用（进入面板、单卡保存落库、增删合并都走它）。
      验证：SettingsView 单测「进入面板的数据刷新后也会重取」；e2e 角色链实测生效
- [x] 2.3 `SettingsView.tsx`：`panelStale` 判据（角色＝charStale；伏笔＝上报的 stale）＋页脚让位（chars note 与 hooks panelNote 的 stale 分支、done-note 在 stale 期不渲染、缺口优先）＋重新确认成功后 `onRefreshConfirmState()`。
      验证：`SettingsView.charsFoot.test.tsx` 新增 5 例（让位文案 / 缺口优先 / 非 stale 原样 / 重新确认后重取 / 数据刷新后重取）全绿
- [x] 2.4 `HooksSettingForm.tsx`：上报对象与类型加 `stale`（既有本地派生值，仅透出）。
      验证：foreshadow e2e ⑦ 的让位断言

## 3. 测试与回归

- [x] 3.1 单测：`npx vitest run` → **109 files / 1285 tests passed**（基线 1277 + 本批 8；连线跑两次计数稳定）。
      验证：两测试文件全绿 + 全量两跑
- [x] 3.2 e2e（隔离栈：容器 `chars-stale-*`、端口 5187/8013/19013、worktree 内数据目录；容器 bundle 特征串「内容改过了」自证）：`settings-forms.spec.ts` + `foreshadow-settings.spec.ts` → **22 passed**。角色链新增段：清空→补回并补齐门禁项 → 离开再回面板（徽标「内容有变 · 待重新确认」＋页脚「内容改过了——点「重新确认」即可，改动已自动保存」＋无 `.done-note`）→ 点「重新确认」→ 徽标与页脚**当场**恢复（不刷新页面）。伏笔 ⑦ 同口径。
      验证：22 passed (1.7m)
- [x] 3.3 门禁：`npx tsc --noEmit` 0 错；`npm run design:lint` 绿；角色屏 parity 记录值 **7.157%**（与上一批同值——被改的两态不在首帧）；`design-parity` 书架+预览 7 passed / 1 failed（`quota` 2.693%＝已登记存量红）。
      验证：输出摘要如上
