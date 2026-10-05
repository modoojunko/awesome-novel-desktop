# Design: s-server-repo-split

## 决策 1：历史用 git filter-repo 提取，不用全新 init

- `git filter-repo --path server/ --path .github/workflows/server-backend-ci.yml --path .github/workflows/server-frontend-ci.yml --path .github/workflows/s-server-deploy.yml --path .github/workflows/s-web-test-deploy.yml --path scripts/code_issue.py --invert-paths --path server/license.db --path server/logs --path server/data --path server/data.legacy --path server/test-results`（路径清单执行时按最终随迁表定稿）。
- 保 660+ 提交的 blame 史（安全加固/支付/设备体系排查价值高）；脏文件从历史一并剥离。
- openspec 的 spec/change **不进历史提取**——以当前内容在 S端 仓 fresh commit（spec 历史留在 ai-novel，blame 价值低于代码，且避免 spec 历史迁移的路径纠缠）。
- 前提核对：filter-repo 需 pip 安装（执行时确认本机可用；不可用则 brew 装或临时 venv）。

## 决策 2：openspec 归属规则与清单

规则：**requirement 的 SHALL 主语实现在哪端，spec 归哪仓**。跨端 spec（provider/consumer）归 provider 侧。

**随迁清单（预审，执行时逐个 grep SHALL 主语实核定稿）**：
- `s-*` 10 个：s-api-ratelimit、s-client-outdated-signal、s-contract-live-check、s-landing-pricing、s-pay-account-views、s-pay-cashier、s-payments、s-query-filter-safety、s-schema-migration、s-security-baseline
- 无前缀 11 个：code-issuance、entitlement-sync、wechat-pay-gateway、device-registration、device-fingerprint、device-auth-page、devices、account-control-center、account-deletion、account-security、pg-schema-self-check、tier-access
- **留在 ai-novel**（易错点已核）：db-generation（=C端 每版独立库，c-db-per-version）、tier-gating（C端 门禁组件）、installer-release（C端 打包）、e2e-assertion-polish 及其余全部。

**在途 change 处置**：实勘 `openspec/changes/` 非 archive 目录——c-* 全部留守；`s-prompt-pack-delivery`（两端混合，且设计待按四方评审重写）**拆两半**：S端 仓新 change（发钥端点＋CEK 表）＋ai-novel 留 C端 半（拉包安装），两边 proposal 互相引用；其余若有 s-* 在途 change 随迁。

**两仓基线**：迁移后各自跑 `openspec validate --strict`＋全量 specs 计数入档（原 74 拆成两份，数字写进两仓 README）。sync 脚本（sync_specs）如有跨仓假设，执行时一并改。

## 决策 3：brand/ 双仓复制

- S端 仓放仓根 `brand/`（从 ai-novel 复制当前内容）；`server/frontend/src/constants/brand.ts:8` 的 `import brandJson from '../../../../brand/brand.json'` 在新仓根布局下相对深度不变（server/frontend/src/constants → 仓根同样四层），**预期零改动**，构建时验证。
- C端 侧消费点（`client/packaging/build/build.spec`、`client/frontend/vite.config.ts`、`client/frontend/src/lib/brand.ts`）不动——ai-novel 保留 brand/。
- 两仓 brand/README 注明「双仓副本，以 ai-novel 为首发源，改动两端同批」。

## 决策 4：跨端管线切割

1. **compose/e2e**：ai-novel 的 compose 全家桶 `build: ./server` 失效。约定：**sibling checkout**——`docker-compose.yml` 的 server 构建上下文改变量 `${S_SERVER_DIR:-../awesome-novel-server/server}`；本地栈配方与 CLAUDE.md 更新；C端 e2e 已参数化（`E2E_S_API`），隔离栈配方改为从 sibling 起服务端。
2. **nightly e2e（e2e-scheduled.yml）**：CI 双 checkout——`actions/checkout` 加 `repository: modoojunko/awesome-novel-server`（token 走 secrets），ref 缺省 main；版本兼容靠现成 check-auth code=3 信号，不新增机制。
3. **design-cross.mjs**：单进程读两端 frontend——移到**本地脚本/S端 仓 CI** 跑（需要双 checkout；公开的 C端 仓 CI 不持私有仓 token）。ai-novel 的 config.yaml 门禁条目同步改写为「design-cross 在 S端 仓 CI 执行，本地跑法见其 README」。
4. **docker-build-ci.yml**：两端混编——拆成两半，S端 半随迁、C端 半留守，paths 触发各自修正。
5. **secret-fingerprint.yml**：两仓都要（复制）。

## 决策 5：新仓骨架内容

- 根：README（含 validate 基线数字与本地开发配方）、CLAUDE.md（AI 会话入口，注明「每个对话独立环境」纪律延续）、LICENSE 与 THIRD-PARTY-NOTICES（复制）、brand/ 副本、openspec/（config.yaml 独立 context＋迁移来的 specs/changes）、`.github/workflows/`（4.5 个随迁＋codeql/secret-fingerprint）。
- `.gitignore`：补 `server/license.db*`、`server/logs/`、`server/data*/`、`server/test-results/`、`server/secrets/*`（留 .gitkeep 机制）。
- 部署冒烟：Actions 额度若仍锁，按既有「本地 tcb CLI 直发配方」执行 `s-server-deploy` 等效冒烟，探活 `/api/user/me`。

## 迁移次序（tasks 骨架依据）

① S端 仓 bootstrap＋CI 绿（不依赖 ai-novel）→ ② filter-repo 提取＋push → ③ ai-novel 同 PR：删 server/＋改 compose/workflows/跨端引用＋config/CLAUDE → ④ 双向验证（部署冒烟＋C端 e2e 连 sibling）→ ⑤ secrets/收尾。③ 之前两仓并存双真源，③ 之后 ai-novel 的 server/ 引用全部失效——**③ 的 PR 必须一次完整落地，不留中间态**。

## 风险与回滚

- **并行会话**：主检出可能有其他会话在 server/ 上有未提交工作——③ 执行前实勘 `git status server/`，非空则协调 freeze 窗口（对齐「每对话独立环境」纪律）。
- **回滚**：③ 的 PR revert 即恢复 monorepo；S端 仓删除重来（filter-repo 可重复执行，幂等成本低）。
- **历史秘密**：S端 仓私有＋历史来自同源私有仓，无新增暴露；`license.db` 剥离见决策 1。ai-novel 历史仍含 S端 痕迹——公开前消毒属 C端 公开 change（非目标已列）。

## 测试口径

- 新仓：`pytest server/tests`（含契约测试）全绿、`server/frontend` build＋单测、ruff、`pg_schema` 自检、`openspec validate --strict`、workflows 触发路径 dry-run 核对。
- ai-novel：`client/backend` pytest＋vitest＋e2e（连 sibling S端）全绿、`openspec validate --strict`、design:check（不触样式，防误伤）。
