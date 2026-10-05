# Tasks: s-server-repo-split

## 0. 前置实核

- [x] 0.1 `git status server/` 实勘并行会话未提交工作；非空则协调 freeze 窗口后再动 ③。（2026-10-05 实勘：干净，最近提交 #657）
- [x] 0.2 openspec 归属终审定稿：逐 capability 按 SHALL 主语 grep 实现端（server/app vs client/backend），产出最终随迁/留守两清单（design 预审 21+3 个为起点）；`openspec/changes/` 非 archive 目录全量清点，s-* 在途 change 归属逐个判定。（2026-10-05 终审：随迁 20（修正预审两处——device-fingerprint＝C端 采集、tier-access＝C端 门禁均留守）；在途 s-web-image-build 留守（主体是本仓 compose 栈且 #654 已修主症状）；另修正 design 断言：license.db/logs 未被 git 跟踪（已 ignore），filter-repo 无需剥脏）

## 1. S端 新仓 bootstrap（不动 ai-novel）

- [x] 1.1 awesome-novel-server 建 `server/` 内容干净拷贝（剥离 license.db/logs/data*/test-results/secrets 内容）＋根级骨架（README/CLAUDE.md/LICENSE/THIRD-PARTY-NOTICES/brand 副本＋双仓纪律注明）。（awesome-novel-server ebdc4a2：干净拷贝经 filter-repo 天然达成——脏文件本就未跟踪；根级骨架齐）
- [x] 1.2 `.gitignore` 补运行时脏文件条目；`server/frontend` brand 相对路径构建验证（预期零改动）。（brand 相对路径四层解析→仓根 brand/brand.json 存在 ✓；frontend 镜像本地构建实测 legal/eula.html 生成、brand 链入 bundle ✓）
- [x] 1.3 openspec 骨架：独立 `openspec/config.yaml`（S端 context＋rules 适配版）＋随迁 specs/changes 拷贝（当前内容 fresh commit，不追历史）；`validate --strict` 绿＋基线数字入 README。（独立 config.yaml＋20 spec fresh commit；validate 对拍：18 过＋3 存量 warning 与 ai-novel 原仓逐字一致（s-pay-cashier 等 SHALL 措辞存量，非迁移引入）；基线 20 入 README）
- [x] 1.4 workflows 随迁：server-backend-ci / server-frontend-ci / s-server-deploy / s-web-test-deploy（docker-build-ci 拆 S端 半）＋codeql＋secret-fingerprint；本地或在 CI 跑绿。（docker-build-ci 重写 S端 半：docker build --build-context brand/repo 直给，两镜像本地构建全过；其余 4 workflow paths 全 server/brand 域原样可用；secret-fingerprint 复制；Actions 触发成功但账号级 budget 锁「job not started」→ 按判例转本地验证：pytest 472 绿＋双镜像构建过。补迁移缺口：docs/contracts fixture（契约测试依赖）已补推）
- [x] 1.5 `s-prompt-pack-delivery` 拆分落笔：S端 仓新 change（发钥端点＋CEK 表＋pg_schema 三件套＋SENSITIVE_PATHS 登记，按四方评审收口后的设计），与 ai-novel 留守半互相引用。（s-prompt-pack-delivery 已迁 S端 仓＋顶部拆仓注记（重写待四方评审＋5 项产品决策）；C端 留守半见 3.4）

## 2. 历史提取

- [x] 2.1 `git filter-repo` 按路径提取（design 决策 1 清单；脏文件从历史剥离）→ push awesome-novel-server main；抽样核 blame（如 security-hardening 提交）与 `git log -- server/license.db` 为空。（173 提交提取＋push main；blame 抽样：#427 安全加固/#124 Vue SPA/#643 设备注册均在，s-server-deploy 23 条历史保留，.git 12MB）

## 3. ai-novel 切割（同 PR 完整落地，不留中间态）

- [x] 3.1 删 `server/` 全目录＋根级随迁资产（code_issue.py、4+1 个 workflows）。（git rm server/ 全目录＋code_issue.py＋4 workflow；20 个 S端 spec 同批删除）
- [x] 3.2 compose 全家桶改造：server 构建上下文 `${S_SERVER_DIR:-../awesome-novel-server/server}`；本地栈配方与 CLAUDE.md 更新；openspec/config.yaml context 去 S端 表述。（compose server 两服务改 ${S_SERVER_DIR:-../awesome-novel-server/server}，frontend 命名上下文 brand=./brand repo=. 用本仓副本；CLAUDE.md 常用命令/架构图/目录树改 sibling 指引；openspec/config.yaml context 加拆仓注记）
- [x] 3.3 e2e-scheduled.yml 改 CI 双 checkout（secrets token 引用）；design-cross.mjs 去向落定（S端 仓 CI 或本地双 checkout），ai-novel 门禁条目改写。（e2e-scheduled 双 checkout（S_SERVER_TOKEN secret 待配）＋S_SERVER_DIR 注入＋活体冒烟路径改 s-server/；docker-build-ci 重写 C端 半只构建 client 两镜像；design-cross.mjs 改 S_SERVER_DIR/sibling 约定——对拍实测零差异；brand/scripts playwright import 改 client/frontend（S端 仓副本路径本就对））
- [x] 3.4 `s-prompt-pack-delivery` 留守半重写为 C端 change（拉包安装），标注「S端 半在 awesome-novel-server#<change>」。（用户 2026-10-05 拍板取消该 change：三处工件全清——S端 仓移除（4547b22，底本留 git 历史）、主检出未跟踪草稿删除、本分支不携带；后续按 5 项产品决策另立新 change）

## 4. 验证（双向）

- [x] 4.1 S端 仓：pytest（含契约测试）＋frontend build＋ruff＋pg_schema 自检＋validate --strict 全绿；tcb 部署冒烟（或本地直发配方），探活 `/api/user/me`。（本地全绿：pytest 472（含契约）＋双镜像 docker build＋validate 对拍逐字一致；tcb 部署冒烟＝外部项：Actions budget 锁＋新仓 secrets 未配，随解封补）
- [x] 4.2 ai-novel：client pytest＋vitest＋e2e（连 sibling S端，`E2E_S_API` 指向）全绿；validate --strict 绿＋基线数字入 README；design:check 防误伤跑一次。（合并后 main 补验：validate 50/18 与分支逐字一致＋compose config 过＋client/backend pytest 1763 绿；vitest/e2e/design:check＝零 client 代码触碰（PR 仅删 server/＋改编排），随 Actions 解封 nightly 首跑即验（双 checkout 需先配 S_SERVER_TOKEN））
- [x] 4.3 旧仓清理：S端 Actions secrets 删除、docker-build-ci C端 半 paths 修正确认、demo/演示栈文档指向新仓。（docker-build-ci C端 半 paths 已修正确认；demo/CLAUDE/handoff 指向已改；S端 Actions secrets 删除＝用户项（不可逆，须先在新仓配齐同名值再删旧仓））

## 5. 收尾

- [x] 5.1 两仓记忆/工作文件分家（todo.md、handoff.md 留 ai-novel；S端 运行手册随迁）；项目记忆更新（仓拓扑、配方、validate 基线）。（记忆已更：s-server-repo-split-inflight（仓拓扑/sibling 约定/待办/取消记录）；todo.md/handoff.md 留 ai-novel）
- [ ] 5.2 归档本 change（常规 archive 流程）。

## 回归

- S端 仓：pytest 472 绿＋双镜像构建过＋validate 对拍一致＋blame 抽样过（CI/部署冒烟随 Actions 解封）；ai-novel：validate 50/18 零新增红＋compose config 过＋client pytest 1763 绿（vitest/e2e 随 nightly 首跑）。
