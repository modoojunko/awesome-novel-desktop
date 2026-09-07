# Tasks: c-s-entitlement-sync

## 1. 共享契约基准

- [x] 1.1 落 `docs/contracts/entitlement-defaults.json`（档位→features/limits，内容=PRD §6.2 表），验证：JSON 可解析且含 none/free/trial/pro/max 五键
- [x] 1.2 PRD §6.6 映射矩阵与 JSON 交叉核对（12 个 FeatureKey 全覆盖、免费基线/会员差异一致），验证：逐行比对记录在 change 目录

## 2. PR-1 S端

- [x] 2.1 `models/payments.py` TierORM 加 `entitlement TEXT NOT NULL DEFAULT '{}'`（server_default 落 ORM），验证：sqlite create_all 后新库含列
- [x] 2.2 `infrastructure/pg_schema.py` 登记 tiers.entitlement 不变量（EXPECTED_DEFAULTS/REQUIRED 两处），验证：pg_gate 本地跑 success
- [x] 2.3 `config.py` 加 `ENTITLEMENT_DEFAULTS`（语义同 1.1 JSON 内联成 dict），验证：单测断言与 docs/contracts JSON 一致
- [x] 2.4 `payments_repo.py` TierRepo 加带 60s 进程内 TTL 缓存的按 key 查询（现状仅 find_all，缓存自建；坏 JSON/缺行返回 None），验证：单测覆盖命中/过期/坏 JSON 三路
- [x] 2.5 `authorize.py` check-auth 组装并下发 `data.entitlement`（免费基线含 max_projects=1；组定点=data dict 追加可选字段），验证：扩展 `test_check_auth_extension.py`——pro 下发非空 features、无配置回退 DEFAULTS、免费基线、坏 JSON 回退
- [x] 2.6 契约测试 `contract/test_c端_contracts.py` 补 entitlement 形状断言（v=1、features 是 list、limits.max_projects 为 int|None），验证：全量 pytest 绿
- [x] 2.7 生产 DDL/种子 SQL 脚本落 `docs/`（ALTER TABLE + UPDATE pro 行），验证：脚本评审通过（执行留发版口）

## 3. PR-2 C端 后端

- [x] 3.1 `auth_local/service.py`：browser_auth(silent) code 0 保存 `entitlement`+`entitlement_fetched_at`；code 1 清除之；`load_or_create_config` 默认 `"entitlement": None`，验证：单测三路
- [x] 3.2 `MEMBER_TIERS` → `FALLBACK_MEMBER_TIERS`（+pro/max），主判定路径白名单摘除，验证：grep 无残留引用
- [x] 3.3 `check_permission()` 优先级链重写（deletion_pending→过期（trial 无到期生产收紧=与过期同口径 allowed=False，env `ENTITLEMENT_LEGACY_TRIAL=1` 宽限）→完整快照自证（is_member=features 非空或 max_projects 不限，不再 or 白名单）→无快照 FALLBACK），保持同步纯读 config，验证：单测覆盖 PRD §9 场景 1/5/10/16/17 全分支
- [x] 3.4 三段式重同步挂在 **async 边界**（deps 门禁函数与 check-auth 端点内 await 一次重同步；check_permission 保持同步）：快照缺字段→重同步→成功采用新快照；不可得→STANDARD_FALLBACK（镜像 docs/contracts JSON）+ `entitlement_degraded`，验证：单测 mock 重同步成败两路 + check_permission 零网络 IO 断言
- [x] 3.5 `verify_session()` 响应透传 `entitlement` 原文（无快照省略）+ `entitlement_degraded`（缺省 false），验证：单测断言形状（含 degraded true/false 两态）
- [x] 3.6 共享 JSON 对拍测试（C端侧读 docs/contracts/entitlement-defaults.json 与代码内 STANDARD_FALLBACK 比对），验证：pytest 绿
- [x] 3.7 `docker-compose.yml` client-backend environment 注入 `ENTITLEMENT_LEGACY_TRIAL=1`（本地 dev 宽限；生产安装包不注入），验证：本地容器内 env 生效、client/packaging 构建产物不含该 env
- [x] 3.8 后端全量 pytest + ruff 全绿（venv python 跑），验证：本地命令输出

## 4. PR-3 C端 前端

- [ ] 4.1 LicenseProvider 上移：应用认证后路由根部挂 `AuthGuard → LicenseProvider → routes`（书列表获得上下文），`NovelLayout.tsx` 只留 `ProjectShell → Outlet`，验证：书列表 useTier 可用、/novel/:id 上下文不回归（project-shell delta 落地）
- [ ] 4.2 两跳刷新：路由切换（进工作台/书列表，60s 去抖）→ 先调 `/auth/check-auth`（S端 静默往返写快照）→ 再 `refetch` 刷上下文；window focus 尽力补一刀，验证：vitest mock 两跳顺序与去抖（只调 verify 不调 check-auth 判不通过）
- [ ] 4.3 `LicenseProvider` 透传 entitlement/entitlementDegraded + `isFree/isPro` 口径对齐代码（isFree=!isMember、isPro=isMember），验证：vitest 透传/降级标志/过期会员三态
- [ ] 4.4 `useTier` 同源新增 `useFeature(key)`（快照包含判定；无快照回退 features.ts 静态 memberOnly 取反；provider 外安全默认），验证：vitest 四路（有/无 key/无快照/provider 外）
- [ ] 4.5 `features.ts` 注释语义改写（词汇表+快照缺失兜底，判定依据让位快照；`isMemberFeature` 保留为兜底口径），验证：tsc 通过
- [ ] 4.6 客服链接单源化：从 `Navbar.tsx` 抽取 `supportUrl` 到共享模块（如 `src/lib/support.ts`），Navbar 改引用；权益异常提示条（notice warn 语气；书列表，条件=entitlementDegraded；详情=缺失字段+档位+抓取时间可复制 + 联系客服链接用该模块），验证：vitest 出现/消失两路 + Navbar 链接不变
- [ ] 4.7 `prototypes/ADJUSTMENTS.md` 登记提示条新增条目（复用既有 notice 形态声明），验证：登记在案
- [ ] 4.8 前端门禁：design:lint + design:check + tsc --noEmit + 相关 vitest 全绿，验证：本地命令跑绿

## 5. 端到端验收

- [ ] 5.1 本地 docker 重建 client-backend/client-frontend/server-backend 镜像（S端 sqlite 补列），验证：容器起、/api skus 200
- [ ] 5.2 PRO 账号（modoojunko）建第 2 本书成功 + AI 入口解锁，验证：UI 操作走通（原始事故闭环）；同场景在 5.6 以打桩断言镜像固化
- [ ] 5.3 断网复测不降级（停 S端 后端容器后路由切换刷新），验证：is_member 不变、沿用旧快照
- [ ] 5.4 中途购买生效演练：**改本地 S端 sqlite 的 tiers/codes 后走真实两跳刷新链**（路由切换触发），验证：前端权益更新（不绕链、不手改 C端 config）
- [ ] 5.5 老 S端 兼容演练（S端 回退到无 entitlement 响应打桩），验证：C端 FALLBACK 判定 pro 为会员
- [ ] 5.6 C端 e2e 全量本地跑绿，验证：新增打桩用例（快照两态 + PRO 建第 2 本书断言）+ 存量不回归

## 6. 交付

- [ ] 6.1 三 PR 按切片提交（PR-1 S端 / PR-2 C端后端 / PR-3 前端含 shell 上移），CI 全绿
- [ ] 6.2 生产发版清单落 change 目录：DDL+种子 SQL 执行步骤、pg_gate 验证、S端 部署顺序、**C端 打包发版（client-update 通道，闭环必要条件）**、回滚说明；留发版口用户拍板
