## Context

见 proposal.md。落地相关现状（实勘）：

- auto mock：`server/frontend/e2e/fixtures.ts` 的 `mockApi` auto fixture 拦截全部 API（否则 check-auth 预热穿透 vite proxy 空转）。
- vite 已带 proxy：`/api → http://127.0.0.1:19000`（vite.config.ts:37-39）——活体档的网络路径现成。
- CI：`server-frontend-ci.yml` 明注「e2e 全 mock，无需后端」；nightly（e2e-scheduled.yml）起的是 C端四服务栈，含 server-backend:19300（chb 栈口径下同理）。
- 契约 fixture 先例：`docs/contracts/entitlement-defaults.json`＋两侧对拍测试（`server/tests/contract/`、C端 `test_entitlement_sync.py`）。

## Goals / Non-Goals

**Goals:**

- 活体冒烟档进 nightly 真跑：落地页/登录进控制台/备案页三条关键路径。
- check-auth 契约 fixture 单源＋两端对拍。

**Non-Goals:**

- 不把全部 mock 用例迁成活体（mock 层继续承载功能覆盖；活体只守契约面）。
- 不做 devices/current 的 fixture（该端点消费方单一、响应稳定，登记为后续候选）。

## Decisions

**D1：活体档独立目录 `e2e/live/`，直接 import `@playwright/test` base，绕开 auto mock。**
不改造既有 fixtures（auto mock 对其余用例仍是正确默认）；`S_LIVE_BASE_URL` 未设即整组 skip（照 UP11_DATA_DIR 先例）。

**D2：活体后端用 uvicorn＋sqlite 本地库（nightly 内 pip install 即起），不经 docker compose。**
冒烟只验 HTTP 契约面（页面渲染＋登录流），不需要 PG/云资源；compose 栈留给 C端 e2e，避免互抢。

**D3：check-auth fixture 放 `docs/contracts/check-auth.example.json`，两侧测试只 assert 键集与类型族（不 assert 具体值）。**
值随会话/用户变化，fixture 锚定的是「有哪些字段、什么形状」；与 entitlement-defaults（值语义单源）分工不同，故不合并。

## Risks / Trade-offs

- [nightly 多起一个后端的维护成本] → sqlite 零依赖，启动秒级；失败即红可定位。
- [活体冒烟对登录流的真实依赖（验证码/限流）] → 冒烟用专用测试账号＋后端 sqlite 全新库，无旧态干扰；限流阈值 env 已可放。
- [fixture 与真实响应漂移] → S端契约测试用 fixture 断言真实 handler 输出，漂移即红。

## Migration Plan

1. 活体 spec＋本地起后端验证 → nightly 接线 → 观察一轮。
2. 回滚 = revert 提交（无数据/部署面变更）。
