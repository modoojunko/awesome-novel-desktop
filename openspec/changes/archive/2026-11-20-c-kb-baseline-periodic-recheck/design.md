# c-kb-baseline-periodic-recheck · 设计

## Context

现状（2026-11-20）：

- 启动补偿：`main.py` lifespan → `kb.baseline.schedule_sync()` → 后台 `sync_baseline()`，验签
  通过且版本不同就整层替换，不弹窗、不需要登录。
- 登录钩子：`maybe_sync()` 只在层为空时补装，已装零外呼。
- 页面触达：知识库页挂载 `GET /kb/baseline/probe`（只读），有新版本弹窗让用户确认。
- 没有会话内定时器：`update_check` 对**应用自身更新**有 1 小时节流复查，知识基线没有对应物。
- `sync_baseline()` 的返回：`synced / current / skipped / failed`；`skipped` 的 reason 有
  `syncing / retired / not_configured / format_newer`。前端弹窗只判 `failed`。

## Decisions

### D1 周期复查而不是推送

C端 是本地 FastAPI + 桌面壳，知识分发完全走 CDN 静态托管，S端 不参与。真推送需要 WebSocket/
SSE 长连接与服务端通道，收益是一份几百 KB 静态 JSON 的时效（小时级足够），成本是新的连接生
命周期、鉴权与断线重连——不做。

### D2 复查直接同步（自动应用），不只探测

启动补偿本来就是无条件应用新版；周期复查沿用同一语义，用户不必理解「有更新但没装」。基线层
是设备级只读 lower 层，整层事务替换不触碰用户条目与覆盖记录，后台应用安全。

「暂不更新」锚只存在于前端 localStorage，语义是**压制弹窗提醒**（既有 spec 场景：同版不重
弹），不是同步否决——启动补偿不读它，周期复查也不读。若未来要「暂不更新＝不装」，需要把锚
搬到设备级 KV 并改既有场景，另立项。

### D3 失败用短间隔重试，首跳也短

启动期网络抖动/代理环境（fake-ip 主域失败再走兜底域）会让一次同步失败。若固定 1 小时后再
试，用户可能一整天都拿不到新版。失败后 5 分钟重试、成功/跳过恢复 1 小时；首跳同样用 5 分钟
（给启动补偿留收尾，启动同步失败的会话也能在分钟级兜住）。常量可被测试 monkeypatch，不新增
env（避免未要求的可配置性）。

### D4 单飞与测试闸复用

周期复查调用同一个 `sync_baseline()`：`_syncing` 保证与手动同步、启动补偿互斥；任务体在
`KB_BASELINE_SYNC=0` 时根本不创建（与启动补偿同闸，测试进程不联网、不抢 SQLite 写锁）。
模块级 `_recheck_task` 持引用防 GC，重复 `schedule_periodic_recheck()` 不叠加任务。

### D5 skipped 的界面口径

- 不新增弹窗状态：照 `PromptPackModal` 对 `min_client_version` 的先例，用 info toast 说明，
  然后关窗（`finishDialog("kb-sync")`）。
- 文案分原因：`syncing`＝「后台正在更新，稍后会自动完成。」；`format_newer`＝「这份知识要用
  新版客户端才能装上；本机的官方知识保持现状。」；其余＝「这次没有可更新的内容。」。无内部术
  语，不出现「门控/代际/format」等词。
- 跳过时写该 CDN 版本的「暂不更新」锚：`format_newer` 的包本端永远装不上，不写锚会每次进知
  识库页都自动弹窗（探测只看版本号，不看格式闸）。
- `status=current` 保持算更新完成（竞态下他路已装同版）。

## Risks

- 常驻进程每小时一次 HTTPS 请求（latest.json，8s 超时）：可忽略；失败不重试风暴（5 分钟）。
- 周期同步与用户正在编辑基线条目副本：只读层替换不动用户层；merged 视图读的是提交后的层。
- 测试进程若忘了 `KB_BASELINE_SYNC=0`：conftest 已全局默认 0，新增用例显式开闸并等待任务体
  跑完再断言。
