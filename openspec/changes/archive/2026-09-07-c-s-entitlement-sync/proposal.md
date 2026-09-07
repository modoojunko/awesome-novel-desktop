# Proposal: c-s-entitlement-sync

## Why

S端 支付改版把档位归一化为 pro/max，C端 的会员判定白名单（`MEMBER_TIERS`）停留在旧档位名——PRO 用户被按免费处理：1 本书限额、AI 全关、升级提示错乱（2026-09-06 实锤事故）。根因是"哪个套餐开什么功能"两端各存一份硬编码，双事实源，S端 每改一次档位 C端 必断。治本：S端 单一事实源配置套餐内容，C端 登录拉取权益快照，按快照开功能。

## What Changes

- **S端**：`tiers` 表新增 `entitlement` JSON 列（档位→features/limits 目录配置）+ `ENTITLEMENT_DEFAULTS` 代码兜底 + check-auth 响应新增可选 `entitlement` 字段（契约 v1：features 数组 + limits.max_projects，null=不限）
- **C端 后端**：`check_permission()` 判定源重写——快照优先；快照异常走三段式（重同步→档位标准兜底 STANDARD_FALLBACK+降级标志）；`FALLBACK_MEMBER_TIERS`（含 pro/max）只活在"无快照"分支，主路径白名单摘除；trial 无到期数据生产收紧为免费基线（Q4，dev/test 环境变量保留旧宽限）
- **C端 刷新**：新增触发点——路由切换（进工作台/书列表，保证信号）+ window focus（尽力而为）；启动/登录维持现状；不做定时轮询（Q1）
- **C端 前端**：权益上下文上移至认证后路由根部（书列表获得上下文与刷新触发）；`LicenseProvider` 透传 entitlement，新增 `useFeature(key)` 钩子；新增权益异常客服提示条（问题详情可复制）；`features.ts` 注册表降级为"词汇表+快照缺失兜底"；客服链接从 Navbar 抽取共享模块单源
- **命名裁定落地**：权益正名 entitlement 全链路启用；`License` 保留为聚合类名
- **明确不做（登记遗留）**：存量表改名（codes→entitlements、device_grants→authorizations）、补差价升级订单（Q2 拍板方向）、S端 管理后台编辑 UI、升级页功能矩阵接口

## Capabilities

### New Capabilities

- `entitlement-sync`: 端到端权益同步契约——S端 从权益记录×档位配置计算并下发用户权益快照（features/limits）；C端 缓存快照、按三处触发点刷新、快照驱动判定、异常三段式自愈与客服升级路径

### Modified Capabilities

- `tier-access`: `check_permission()` 判定源从"档位白名单"改为"权益快照优先"——完整快照下 is_member 由快照自证、project_limit 取 limits.max_projects；FALLBACK 档位名单（含 pro/max）仅用于无快照分支；trial 无到期数据生产环境收紧（与过期同口径 allowed=False）
- `tier-gating`: `LicenseProvider` 增加 entitlement 透传与 `useFeature()` 钩子（快照 features 包含判定，快照缺失回退静态 memberOnly）；`features.ts` 语义从判定依据改为词汇表+兜底；`isFree/isPro` 口径与代码对齐（免费待遇=非有效会员）
- `project-shell`: 权益上下文从 NovelLayout 上移至认证后路由根部（AuthGuard → LicenseProvider → routes），书列表获得上下文与刷新触发点

## Impact

- **server/**：`models/payments.py`（TierORM 加列）、`infrastructure/pg_schema.py`（不变量登记）、`config.py`（ENTITLEMENT_DEFAULTS）、`interfaces/client_api/authorize.py`（check-auth 下发）、`repositories/payments_repo.py`（TierRepo 缓存读）、tests（`test_check_auth_extension.py`、`contract/test_c端_contracts.py`）
- **client/backend/**：`auth_local/service.py`（browser_auth 保存快照、check_permission 重写、verify_session 透传）、tests
- **client/frontend/**：`lib/features.ts`（注释语义）、`components/novel/license/LicenseProvider.tsx`、`hooks/useTier.ts` 同源新增 `useFeature`、新增权益异常提示条组件；8 个 is_member 消费组件**零改动**（判定变对后自动修正）
- **schema**：生产 PG 手工 DDL（`ALTER TABLE tiers ADD COLUMN entitlement TEXT NOT NULL DEFAULT '{}'` + pro 行种子 SQL）+ pg_gate 不变量；本地 docker S端 sqlite 补列
- **兼容**：字段纯新增，老 C端 无感；发新 C端 后闭环
- **发布顺序**：PR-1 S端 可独立上线 → PR-2/3 C端 随下个版本；生产 DDL 在发版口执行（用户拍板）；**C端 发版（打包/更新通道）是闭环必要条件，列入交付清单**

## Design Impact

- 受影响端：**C端**（S端 纯 API 变化，无界面）
- 屏/弹层清单：书列表升级横幅与建书弹窗文案（is_member 判定变对后**自动修正**，零布局变化）、工作台 Rail 升级卡（同）、**新增**权益异常提示条（书列表顶部，notice 家族 warn 语气，出现条件=verify 响应 `entitlement_degraded`）
- 对象状态：复用既有 notice 组件与 info/warn 语气词，无新增形态、无第四种胶囊
- 共享段：不触碰两端共享 CSS 段
- 原型：提示条为既有 notice 形态复用，在 `prototypes/ADJUSTMENTS.md` 登记新增条目；既有屏零布局变化，parity 基线不受影响
- 设计工件：实现侧自查（无独立设计侧会话）
- 文案：提示条主文案动词口径、补救语句带"联系客服"可点击出口（复用 constants/support.ts 单源），不出现内部术语
