# c-kb-baseline-periodic-recheck · 任务

## 1. 边界与判定

- [x] 1.1 界面影响判定：本 change 只在既有 `KnowledgeSyncModal` 状态机里把 `skipped` 从成功分支摘出（info toast＋关窗），无新增组件形态/颜色/字号、不触两端共享段——依据 proposal「Design Impact」免原型先行；该弹窗无原型基线（`docs/design-c/prototypes/` 无对应文件），改动为文案与分支，无版式变化
- [x] 1.2 明确非目标：不做 WebSocket/SSE/S端 推送，不做知识树周期复查，不改「暂不更新」锚语义（压制弹窗提醒，不是同步否决）——写进 design.md D1/D2

## 2. 后端：会话内周期复查

- [x] 2.1 `kb/baseline.py` 新增 `RECHECK_INTERVAL`（3600s）/`RECHECK_RETRY_INTERVAL`（300s）、`_next_recheck_delay(result)`、`_recheck_loop()`、`schedule_periodic_recheck()`；复用 `sync_baseline()` 的 `_syncing` 单飞与 `KB_BASELINE_SYNC=0` 测试闸；模块级 `_recheck_task` 持引用且重复调用不叠加
- [x] 2.2 `_recheck_loop` 首跳用 `RECHECK_RETRY_INTERVAL`（兜住启动补偿失败），之后只在 `synced/failed` 时落 `event=kb_baseline_recheck` 日志（`current` 不刷屏）；失败后按 `RECHECK_RETRY_INTERVAL` 重试，成功/跳过回到 `RECHECK_INTERVAL`
- [x] 2.3 `main.py` lifespan 在启动补偿之后挂 `schedule_periodic_recheck()`，独立 try/except，挂接失败只 warning 不挡启动（源级钉：`test_lifespan_挂载周期复查`）

## 3. 前端：跳过结果诚实反馈

- [x] 3.1 `KnowledgeSyncModal.startRun`：`status=skipped` 时按 reason 出 info toast（`syncing`＝「后台正在更新，稍后会自动完成。」；`format_newer`＝「这份知识要用新版客户端才能装上；本机的官方知识保持现状。」；其余＝「这次没有可更新的内容。」），不 toast 成功、不落「已更新」态
- [x] 3.2 跳过时写该 CDN 版本的「暂不更新」锚并关窗（`writeKbUpdateDismissed`＋`setStage("idle")`＋`setOpen(false)`＋`finishDialog("kb-sync")`），避免 `format_newer` 的包每次进知识库页都弹
- [x] 3.3 `status=current` 仍算更新完成（竞态下他路已装同版），既有用例语义未改

## 4. 回归

- [x] 4.1 后端：`pytest tests/test_kb_baseline_sync_ui.py tests/test_kb_baseline_sync.py tests/test_kb_baseline_merged.py tests/test_kb_baseline_gate_parity.py tests/test_kb_revocation.py -q` → **76 passed**（5.50s）
  - `test_kb_baseline_fullchain.py` 本机挂起：主检出同版本代码 A/B 复现同样挂起（与本次改动无关的存量环境问题），未纳入本轮；改动不触该用例的 CDN 夹具路径
- [x] 4.2 前端：`npx vitest run src/__tests__/KnowledgeSyncModal.test.tsx` → **11 passed**；`knowledgeBasePage.test.tsx` → **23 passed**；全量 `npx vitest run` → **182 files / 2283 passed / 1 skipped**
- [x] 4.3 类型与规范：`npx tsc --noEmit` → exit 0；`openspec validate c-kb-baseline-periodic-recheck --strict` → valid；`openspec validate --specs` → **83 passed, 0 failed**
- [x] 4.4 门禁判定：本 change 无前端视觉改动（无新增类/令牌/版式），不触共享段，`design-cross.mjs` 免跑；`npm run design:lint` 唯一红项为 `docs/design-c/prototypes/preview.html` 的存量 emoji（本 change 未触 docs）
- [x] 4.5 诚实性自查：周期复查失败路径断言「保持旧层＋短间隔重试追回新版」（`test_周期复查_失败保持旧层并继续重试`）；skipped 三条 reason 在弹窗测试里断言「无 success toast＋有 info＋锚已写＋关窗」
