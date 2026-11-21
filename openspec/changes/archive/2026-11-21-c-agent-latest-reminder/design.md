## Context

见 `proposal.md`。DeepSeek 文档的 latest_reminder 角色需紧挨 user 消息；我们当前窗口由
`assistant/context.py::build_outbound_window` 组装（text 只留 user/assistant，native 留
user/assistant/tool），没有该 role。

## Goals / Non-Goals

**Goals:**
- DeepSeek openai 助手每轮在当前 user 消息前带一条本地日期/星期提醒。
- 提醒不落库、不进 compact、不进历史；其它 vendor 零变化。
- 与缓存友好前缀一致：提醒在尾部当前 user 前，历史/系统前缀不动。

**Non-Goals:**
- 不持久化历史提醒（日期会过期；DeepSeek 文档说不回传只降低命中）。
- 不改 non-DeepSeek 供应商；不新增前端 UI。
- 不改跨日历史标记（`_history_transcript` 既有口径）。

## Decisions

### 1. 窗口层插入，不做 transcript 行
`build_outbound_window(..., reminder=...)` 在 apply compact 之后、过滤之前，把
`{"role":"latest_reminder","content":...}` 插到最后一条 user 消息之前；text/native 的
role 白名单在该 role 存在时放行。
- 理由：提醒是每轮外发侧车，不进会话文件/compact；插入点唯一，测试好锁。
- 备选：transcript 追加（会被 compact/落盘投影污染，否决）。

### 2. 能力位门控 + 时间格式
`AIClient.supports_latest_reminder()`：openai 协议＋vendor=deepseek；`latest_reminder_text()`
用 `ZoneInfo("Asia/Shanghai")`、中文星期、空 location、App/中文。
- 理由：role 是 DeepSeek 专用，其它端点可能拒未知 role；本地日期按产品展示时区。
- 备选：所有 vendor 都发（未知 role 风险，否决）；用 UTC 日期（中国用户跨日错位，否决）。

### 3. LoopConfig 透传
router 在 client 就绪后生成提醒并放进 `LoopConfig.latest_reminder`；loop 的 text/native
两分支调用窗口时带 `reminder=self.cfg.latest_reminder`；`_maybe_compact` 的估算不带
（提醒仅 ~20 token，不进 compact 判定）。
- 理由：loop 不感知 vendor；窗口参数单一来源。
- 备选：router 直接改 transcript（污染历史，否决）。

## Risks / Trade-offs

- [DeepSeek 端点/代理不认 latest_reminder role] → 仅 DeepSeek openai 发；若真机 400，退回把日期拼进 user 文本（另案）。真机烟测验证。
- [提醒不进历史，缓存命中点在上一轮 user 原文处截断] → 与既有每回合 note 同款取舍；提醒在尾部不影响系统前缀。
- [时区写死 Asia/Shanghai] → 产品面向中文用户、展示时区既定；后续多时区再抽配置。

## Migration Plan

- 纯外发窗口增量，无数据/API 迁移；回滚去掉 reminder 透传即可。

## Open Questions

（无）
