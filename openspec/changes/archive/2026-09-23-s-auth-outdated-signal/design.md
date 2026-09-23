## Context

2026-09-19 事故链中 S端 的两个结构性缺陷：①错误码不分档（challenge 缺失与密码错误同 code=1，C端 无从构建升级引导）；②无可靠信号通道（C端 登录页只能显示泛化「授权超时」）。五路评审（PM/后端/前端/架构/UX）已裁定本 change 是三件套中唯一可**独立部署、即时止血**的一路；其余两件（C端 免登导出、DB 版本化）依赖发版火车。

关键仓库事实：
- `authorize_device.py:38-44`：challenge 校验与密码校验同返 code=1。
- C端 `auth_local/service.py:498-522`：check-auth 返回 code=1 且本地有 token 时**当场清凭据**（session_invalid）——信号若挂 code=1 会把协议失配误判为会话作废，这是「独立 code=3」的硬理由（架构评审 B4）。
- S端 跑 CloudBase 云托管 MinNum=0：缩容冷启动 30-60s 常态 → 标记**必须落 PG**（架构评审 B2），内存标记在实例切换即丢。
- C端 登录轮询 60×2s=120s → TTL ≥10min（架构评审 B3）。
- `pairing.py:70-72` `_fail()` 统一形态：排除面保持，防旁路探测（架构评审 B8）。

## Goals / Non-Goals

**Goals：** 登录链路能可靠区分「客户端需更新」与「鉴权失败」；信号通道跨实例/重启存活；模糊信号（challenge 缺失）不得断言客户端版本（UX 裁定：文案误导根因）。

**Non-Goals：** C端 升级引导 UI（c-loginless-data-exit）；授权页升级出口本身（已存在，仅文案对齐）；S端 前端漏发问题的部署流程治理（另行登记 runbook）。

## Decisions

1. **独立 code=3 而非 code=1+字段**：旧 C端 兼容性由「未知 code 按未登录兜底」既有行为天然保证；新 C端 干净分支。挂 code=1 会触发清凭据（B4 陷阱），是事故级副作用，无折中空间。
2. **标记落 PG 侧表（device_outdated_marks：pc_hash 主键 + rejected_at），TTL 读时比较**：免清理任务；多实例一致；重启存活。被否备选：内存 TTL（实例切换即丢，云托管常态）；Redis（环境无此组件）。
3. **msg 文案动作导向**：「需要更新后重试」类表述替代「桌面端版本过旧」断言——challenge 缺失是模糊信号，断言版本是本次文案误导的根因（UX 裁定）。分档后 C端 才能按「确需更新/服务异常」两场景出正确文案。
4. **download_url 解析失败即省略**：不编造 URL；C端 有三级回落（S端 hint → 本地 update-check 缓存 → 官网常量），缺一不致命。

## Risks / Trade-offs

- [标记表被刷（恶意 authorize 打标记）] → authorize 需先验用户名密码正确才落标记（分档拒绝发生在密码验证之后），匿名刷标记面为零。
- [latest_version 数据源滞后] → 与 update-check 同源（latest.json 链），已有主/兜底双域；滞后仅影响文案里的版本号显示，不影响信号本身。

## Migration Plan

1. S端 pytest 全绿 → 合 main → s-server-deploy 部署（即时生效，旧 C端 零感知）。
2. C端 透传一行随 c-loginless-data-exit 或下一版本搭车。
3. 回滚：S端 服务回滚即恢复现状；标记表残留无害（TTL 自然过期）。

## Open Questions

（无——五路评审已消解全部已知矛盾；标记表命名随实现定。）
