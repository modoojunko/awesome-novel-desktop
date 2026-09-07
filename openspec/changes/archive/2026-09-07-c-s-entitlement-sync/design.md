# Design: c-s-entitlement-sync

## Context

完整设计事实源 = `docs/prd/c-s-entitlement-sync.md`（同分支，含命名裁定 §2.1、Grill 五拍板、八跳数据流 §5.1、映射矩阵 §6.6、叶子级定案）。本文件只记实施必需的技术决策，不重复 PRD。

现状约束：
- S端 check-auth 已被优化为 pg_http 单往返（#288），新增档位配置查询不得退化；
- 生产 PG schema 手工维护（pg_gate 门禁 + EXPECTED_DEFAULTS 不变量），alembic 不跑 pg_http；
- C端 桌面壳 pywebview 无 focus 事件桥；e2e 跑浏览器（5174）；
- C端 `features.ts` 已有 12 个 FeatureKey（7 免费 + 5 会员 AI），是词汇表事实源。

## Goals / Non-Goals

**Goals:**
- S端 单一事实源下发权益快照；C端 快照驱动判定；新老版本互滚不炸
- 用户的 PRO 身份在本地即刻被正确识别（本 change 的直接验收：建第 2 本书成功）

**Non-Goals:**
- 存量表改名（codes→entitlements、device_grants→authorizations）——独立迁移立项
- 补差价升级订单——独立立项
- S端 管理后台编辑 UI、升级页功能矩阵接口——二期
- DRM 级防篡改；定时轮询；前端"入口隐藏"式门禁

## Decisions

1. **档位配置存 tiers 单列 JSON（`entitlement TEXT NOT NULL DEFAULT '{}'`）**——未来加权益维度零 DDL（生产 schema 手工维护痛点的最小化）；配置在档位级不在 sku 级（pro 月/季/年同内容；时长/设备数本就在 skus）。
2. **TierRepo 进程内 TTL 缓存 60s**——避免每次刷新多一跳 pg_http 退化 #288 单往返优化；配置变更频率极低（改配置=运维事件），60s 传播延迟可接受。备选（每次查询/启动加载）被否：前者加延迟、后者要求重启才生效。
3. **契约字段 `data.entitlement = {v:1, features, limits}`，tier/expires_at 保持平铺不动**——老 C端 在消费平铺字段，兼容优先；快照只装增量信息。
4. **C端 判定优先级链**：deletion_pending → 本地过期 → 完整快照自证（`is_member = bool(features) or max_projects 不限`，**不再 or 档位白名单**——防矛盾输入被白名单翻案）→ 快照不全三段式 → 无快照 FALLBACK 名单（trial/pro/max/monthly/quarterly/yearly/lifetime）。
5. **三段式异常**（Q3 拍板）：本地缺字段→重同步一次；不可得→STANDARD_FALLBACK（档位标准镜像）+ `entitlement_degraded` 标志；前端提示条含可复制详情与客服出口。**重同步挂在 async 边界**（deps 门禁函数与 check-auth/verify 端点均为 async，可 await 一次重同步）；`check_permission` 保持同步纯读 config——不给它引入网络 IO，避免把 sync 的 `tier_bypass()`/`tier_or_gate` 链条异步化涟漪。
5b. **Provider 上移**：LicenseProvider 从 NovelLayout 上移到认证后路由根部（project-shell delta）——书列表需要 degraded 提示条与刷新触发点，现挂载点够不着；NovelLayout 只留 ProjectShell→Outlet。
5c. **两跳刷新链**：路由切换 → `/auth/check-auth`（S端 静默往返+写快照）→ 前端 verify refetch。只调 verify 不联网，是检视揪出的断链，spec 已写死两跳为验收口径。
6. **STANDARD_FALLBACK 单一事实源**：仓库级 `docs/contracts/entitlement-defaults.json`，两端测试各自读文件与代码内表对拍；S端 `ENTITLEMENT_DEFAULTS` 是运行时兜底，JSON 是对拍基准。
7. **刷新触发**：路由切换（进工作台/书列表）为唯一保证信号（pywebview 无 focus 桥，已查证），window focus 尽力而为；60s 去抖；无定时轮询（Q1，兼顾 CloudBase 点耗）。
8. **trial 收紧环境判据**：env `ENTITLEMENT_LEGACY_TRIAL=1` 仅本地 compose/pytest 注入；生产安装包不带。
9. **设备数不下发**：激活链路已 own，C端 无消费点，不造无主字段；将来需要时加 `limits.device_limit`（来源=sku 列）。
10. **前端渐进**：8 个 is_member 消费组件本期零改动（后端判定变对即自动修正）；`useFeature` 先落钩子供新门禁点使用，逐 key 迁移等 MAX 差异化时再做。
11. **词汇表治理**：加 FeatureKey 先登记 specs 再两端实现（PRD §6.5 登记制），共享 JSON（决策 6）是配置侧的同源对拍件。
12. **已知不对称（记录防踩雷）**：老 S端 场景下 `useTier().isMember=true`（FALLBACK 名单）而 `useFeature(会员 key)=false`（静态兜底取反）——本期无消费组件故无害；MAX 期迁移消费组件时必须先消掉这个不对称（如 FALLBACK 时 useFeature 也读名单）。
13. **跨 spec 张力留痕**：`s-payments` spec 有"MUST NOT 使用域外借词（grant/entitlement）"条款（scope=激活端点，与本 change 无直接冲突）；遗留改名立项时须同时 delta s-payments 相关 requirement。`frontend-auth-heal` 的"清理本地登录态"被本 change 扩展（连快照一并清），行为已被 entitlement-sync 覆盖、不矛盾。

## Risks / Trade-offs

- [快照明文可篡改] → 接受：UX 级门禁立场，真账在 S端 订单/对账链（PRD §10）
- [退款收回有分钟级窗口] → 接受（Q5）：刷新节奏传播，不建推送
- [S端 配置错误放大] → 三段式 + DEFAULTS 双兜底 + 客服提示，且 fail-open 方向经 Q3 拍板
- [pg_gate 漏登新列] → EXPECTED_DEFAULTS/REQUIRED 同步登记 + 契约测试 + pg_gate 生产实测
- [镜像表漂移] → 共享 JSON + 两端对拍测试（决策 6）
- [路由切换不触发（用户长驻单屏）] → 窗口期=会话时长，与现状相同不劣化；focus 事件尽力补

## Migration Plan

1. PR-1（S端）：ORM 加列 + 不变量 + DEFAULTS + 共享 JSON + check-auth 下发 + 测试——可独立合，对老 C端 无感
2. PR-2（C端 后端）：快照读写/清理 + 判定链 + verify 透传 + 环境判据 + 测试
3. PR-3（C端 前端）：Provider 透传 + useFeature + 提示条 + ADJUSTMENTS 登记 + vitest
4. 本地验收：docker 重建两端容器，PRO 账号建第 2 本书成功、断网不降级、中途购买回前台生效
5. 生产（发版口，用户拍板后）：PG 手工 DDL + pro 种子 SQL → pg_gate 验证 → S端 部署 → C端 随下个版本
- 回滚：字段纯新增，代码回退即恢复现状；列保留无害

## Open Questions

无（Grill 五拍板 + 叶子级六定案已闭合）。
