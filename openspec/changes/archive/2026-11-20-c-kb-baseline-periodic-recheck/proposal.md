# 官方知识基线会话内周期复查（c-kb-baseline-periodic-recheck）

## Why

CDN 上的官方知识基线目前只在三个点被触达：应用启动补偿、登录/校验成功（仅层缺失时补装）、
知识库页挂载探测。桌面应用经常一次开好几天，期间内容仓发布的 CDN 新版不会进入本机——要等
下次重启或打开知识库页才吃到。用户问「CDN 更新能不能推到 C 端」，本质上缺的是**会话内的复
查**，而不是一条长连接。

同时，`POST /kb/baseline/sync` 在「正在同步中 / 格式代际不兼容（format_newer）/ 已撤回」时
返回 `{"status":"skipped"}`，更新弹窗只把 `failed` 当失败，其余一律当成功——会提示「官方知
识已更新到 vM」，实际什么都没装。内容仓发布新一代格式包时，老客户端会每进一次知识库页弹一
次窗，点「立即更新」再谎报一次成功。

定位：补一条「常驻期间最多一小时自动跟上 CDN」的兜底，并把同步跳过结果改成诚实反馈。不是真
推送（C端 是本地 FastAPI＋桌面壳，S端 不参与知识分发，为一份静态 JSON 加 WebSocket/SSE 不
划算）；也不改「暂不更新」锚的语义——它压制的是弹窗提醒，不是同步本身（启动补偿本来就无条
件应用新版）。

## What Changes

- **会话内周期复查**：启动补偿之外，后台任务在启动约 5 分钟后首跳（兜住启动补偿失败），
  之后每 `RECHECK_INTERVAL`（默认 1 小时）执行一次 `sync_baseline()`；发现新版即整层替换，
  无需重启、无需打开知识库页、不弹窗。失败保持旧层，缩短到 `RECHECK_RETRY_INTERVAL`
  （默认 5 分钟）后重试。
- **与既有闸/单飞同源**：周期复查共用 `KB_BASELINE_SYNC=0` 测试闸与 `_syncing` 单飞（手动同
  步在途时本轮自动跳过）；同进程只挂一个任务，重复调用不叠加。
- **跳过结果诚实反馈**：更新弹窗收到 `status=skipped` 时不再走成功态；按原因给 info 提示
  （后台同步中／这份知识要用新版客户端才能装上），并记下该 CDN 版本的「暂不更新」锚，避免
  装不上的包每次进知识库页都弹一次。
- **非目标**：真推送（WebSocket/SSE/S端 通道）；知识树（taxonomy）周期复查（另行立项）；改
  「暂不更新」语义；改 CDN 发布格式或验签链。

## Capabilities

### New Capabilities

- 无

### Modified Capabilities

- `knowledge-baseline`: 「merged 视图与消费」的同步时机从「仅启动补偿点」扩为「启动补偿点＋
  会话内周期复查点」，两处都静默；「更新探测与触达」新增周期复查与跳过结果诚实反馈的要求。

## Design Impact

- 受影响端：C端（本地后端生命周期＋知识库页官方知识弹窗），不触 S端、不触两端共享段。
- 受影响屏/弹层：知识库页「官方知识」弹窗（`KnowledgeSyncModal`）——只在既有状态机里把
  `skipped` 从「成功」分支摘出，改为关闭弹窗＋info toast；不新增组件形态、不新增颜色/字号。
- 对象状态：使用既有 info 语气（提示条/toast 词表固定 info/ok/warn/err），无新状态语义。
- 共享段：无；无需原型先行（该弹窗无原型基线，改动为文案与分支，无版式变化）。
- 设计工件：实现侧自查。

## Impact

- `client/backend/kb/baseline.py`：新增 `schedule_periodic_recheck()` / `_recheck_loop()` /
  `_next_recheck_delay()` 与两个间隔常量；复用 `sync_baseline()` 的幂等与单飞。
- `client/backend/main.py`：lifespan 在启动补偿之后挂周期复查（失败不挡启动）。
- `client/frontend/src/components/kb/KnowledgeSyncModal.tsx`：`startRun` 处理 `skipped`——按
  reason 出 info 提示、写版本锚、关窗；不再落到「已更新」态。
- 测试：`client/backend/tests/test_kb_baseline_sync_ui.py` 增周期复查用例（到点同步、失败缩
  短间隔、测试闸、重复挂载单实例）；`client/frontend/src/__tests__/KnowledgeSyncModal.test.tsx`
  增 skipped 两臂（syncing／format_newer）。
- 兼容性：不改 CDN 载荷、不改数据库结构、不改既有端点契约；`status=current` 仍算更新完成。
- 运维：周期复查同样走主域→兜底域与出站守卫；日志事件 `kb_baseline_recheck` 只在
  synced/failed 时落，避免每小时刷 `current`。
