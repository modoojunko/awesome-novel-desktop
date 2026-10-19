# 拆书运行监控面板 — 实施任务

## 1. 后端

- [x] 1.1 `service.monitor_view(task)`：queued/running 聚合单元账——l1 批 done/total、
      近 300s 速度窗（done/fail/avg_ms/out_tokens/累计）、最近 8 条流水（at/stage/
      duration_ms/tokens_out/ok/reason=error_kind）、并发度；`reduce_state` 排除；
      只取计数列不读 `output_json`；终态返回 None。验证：pytest 聚合/窗口/排除/终态用例。
- [x] 1.2 `router.get_task` 挂 `monitor`。验证：详情响应含 monitor；既有用例不回归。

## 2. 前端

- [x] 2.1 `deconstructApi` 类型（`DeconstructMonitor`＋detail.monitor）。
      验证：tsc。
- [x] 2.2 `TaskDetailPage` 运行态监控面板：`.pbar` 总进度条＋「批次 N/M · 卡片 N/M ·
      并发 N」摘要；维度文字行换进度条（em 文案原串保留）；速度行；最近流水列表
      （本地时钟 HH:MM:SS，UTC-naive 走 serverTimeMs 单源）。验证：toolsDetail 用例。
- [x] 2.3 「测试模型」按钮：复用探针 `/api-configs/{id}/test`，成功/失败 toast 两臂。
      验证：vitest 两臂。
- [x] 2.4 `.mon-*` 样式（index.css tools 段，仅令牌；`.pbar` 复用 book.css）。
      验证：`check:inline-colors`＋`design:lint`。

## 3. openspec 与设计工件

- [x] 3.1 本变更 proposal／tasks／spec delta（ADDED「运行监控面板」）。
      验证：`openspec validate c-deconstruct-monitor --strict`。
- [x] 3.2 原型 `ai-novel-c端-拆书.html` 运行态补监控面板注记＋`ADJUSTMENTS.md` 登记。
- [ ] 3.3 归档：实现合入后按惯例归档（无需等 resilience——delta 为独立 ADDED）。
