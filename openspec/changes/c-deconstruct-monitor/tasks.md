# 拆书运行监控面板 — 实施任务

## 1. 后端

- [x] 1.1 `service.monitor_view(task)`：queued/running 聚合单元账——l1 批 done/total、
      近 300s 速度窗（done/fail/avg_ms/out_tokens/累计）、最近 8 条流水（at/stage/
      duration_ms/tokens_out/ok/reason=error_kind）、并发度；`reduce_state` 排除；
      只取计数列不读 `output_json`；终态返回 None。验证：pytest 聚合/窗口/排除/终态用例。
- [x] 1.2 `router.get_task` 挂 `monitor`。验证：详情响应含 monitor；既有用例不回归。
- [x] 1.3 **调度即现（boss 2026-10-19 反馈）**：管线 6 类站点派发即写 running 行
      （`_unit_running`）；run_task 终局 `_sweep_running` 清残留（failed/cancelled）；
      monitor 增 `in_flight` 真实在途＋流水行 `label`（第N章/维度·阶段）＋running 态。
      验证：pytest 在途/清扫/倒序用例；ruff。

## 2. 前端

- [x] 2.1 `deconstructApi` 类型（`DeconstructMonitor`＋detail.monitor）。
      验证：tsc。
- [x] 2.2 `TaskDetailPage` 运行态监控面板：`.pbar` 总进度条＋「批次 N/M · 卡片 N/M ·
      并发 N」摘要；维度文字行换进度条（em 文案原串保留）；速度行；最近流水列表
      （本地时钟 HH:MM:SS，UTC-naive 走 serverTimeMs 单源）。验证：toolsDetail 用例。
- [x] 2.3 「测试模型」按钮：复用探针 `/api-configs/{id}/test`，成功/失败 toast 两臂。
      验证：vitest 两臂。
- [x] 2.5 **Token 消耗展示（boss 2026-10-20「这个页面要有本次任务的 token 消耗数量，
      根据任务进展更新」）**：monitor 增 `tokens{in,out,total}`（完成时入账）；
      运行态「Token 消耗 · 输入/输出/合计」行随轮询刷新；完成态调用统计尾缀
      「Token 合计」（从 stats 聚合，monitor 终态 null）。验证：pytest tokens 块＋
      vitest 两态断言。
- [x] 2.4 `.mon-*` 样式（index.css tools 段，仅令牌；`.pbar` 复用 book.css）。
      验证：`check:inline-colors`＋`design:lint`。

## 3. openspec 与设计工件

- [x] 3.1 本变更 proposal／tasks／spec delta（ADDED「运行监控面板」）。
      验证：`openspec validate c-deconstruct-monitor --strict`。
- [x] 3.2 原型 `ai-novel-c端-拆书.html` 运行态补监控面板注记＋`ADJUSTMENTS.md` 登记。
- [x] 3.2.1 **真界面基线原型（v3 配方，boss 2026-10-19 指示「先把原型搞出来」）**：
      `ai-novel-c端-拆书监控-原型.html`（src＋build-decmonitor-proto.py＋monitor-captures/
      可重放资产）——独立栈真跑本分支（uvicorn:8101＋vite:5291，私有 DATA_ROOT＋
      dispatcher off，免 OAuth），按 service 序列化形状种 jobs＋units 真数据
      （13路末班车 82万字/258 章镜像），真系统渲染后 Playwright 逐字抓取
      real.css＋.app-shell；file:// 自检零报错、面板五件套齐全。
- [ ] 3.3 归档：实现合入后按惯例归档（无需等 resilience——delta 为独立 ADDED）。
