# 代码体检报告 2026-09-22（前端工程师 / 后端工程师 / 架构师三视角）

只读静态分析，基于 CodeGraph 索引 + 逐点实勘。三路代理独立工作，交叉确认项已合并标注。
对照基线：09-19 架构体检（docs 内 qa-night 报告同期）。

## 总评

- 安全类遗留（check-auth 回传 token、CORS `*`）与规则单源（brand 编译期单源、entitlement 契约对拍、CI 跑 C端 vitest）**已修复，进步明显**。
- C端 ALTER 链 except:pass **已根治**（声明式 `apply_additive_columns`，异常上抛）。
- **数据层三根柱子仍是结构性风险**：S端生产无迁移链、alembic 双头断裂被 fail-open 掩盖、前端无查询/缓存层。
- 本轮新增 3 条值得优先处理的 P1：主线卡空数据覆盖路径、`.docker-data-qa-night` 密钥入库、C端时区红线违例。

**P1 共 6 条，P2 共 13 条，P3 共 9 条。**

---

## 一、P1（6 条）

### 1. S端 alembic 双 head 未修 + 启动迁移 fail-open（后端＋架构师双确认；09-19 遗留，未修）
- 位置：`server/alembic/versions/`（8 个迁移）；`server/app/main.py:171-178`
- 证据：`c3a51e09d7e2` 后分叉两条链——`a001_users_surrogate → a002_payments_tables → d7e9f1a3b5c7 → e8f2a4b6c8d0` 与 `a1b2c3d4e5f6 → c4d5e6f7a8b9`，两头无合并。启动时 `command.upgrade(cfg, "head")` 遇多 head 必抛 MultipleHeads，`except Exception` 仅 warning 后落到 `create_all` 兜底。
- 影响：sqlite/dev 路径迁移链**从未成功执行**，`alembic_version` 永不落标；a001 的 users 重建/`codes.bound_username→user_id` 回填在 dev/测试库永不生效；任何真 DDL 在 dev 不被验证。
- 修复方向：补 merge revision 收敛双头；启动迁移失败 fail-closed（至少非空库时阻断）；CI 加 `alembic heads` 单头断言。

### 2. S端生产数据库没有迁移链——schema 靠带外 DDL，探针只告警（架构师，新发现）
- 位置：`server/app/main.py:142-153`
- 证据：`DB_BACKEND == "pg_http"` 分支注释自述「表结构由管理端 MCP applyMigration 预建，应用启动不迁移」，仅 `run_schema_check()` 探测，缺失/异常均 warning 后照常启动。仓库里的 alembic 对生产是死代码。
- 影响：「代码上线、DDL 漏执行」只能靠请求期 500 暴露（9-04 全量 401 事故即此类）。
- 修复方向：给 pg_http 建可执行单源 DDL 流水线（alembic 生成 SQL → CI/部署期 apply），探测从告警升级为门禁。

### 3. C端主线卡加载失败静默落空卡，保存即整卡覆盖——真实数据丢失路径（前端，新发现）
- 位置：`client/frontend/src/components/novel/settings/useStoryArc.ts:67`；覆盖写出口 `client/frontend/src/lib/api.ts:222`
- 证据：`.catch(() => !cancelled && snapshotLoaded(EMPTY_ARC))`——hook 无 error 态；失败时表单显示为空且被记为干净基线；`save()` 走 `updateStoryArc` whole-card PUT。
- 影响：瞬时网络失败后用户补两句点保存，已有 fullstory/ending 被近空值整卡覆盖。消费方 `StoryArcForm.tsx:58`、`SettingsView.tsx:460`。
- 修复方向：失败时保留错误态并禁写；或 save 前若本会话未成功加载过则拒绝提交。

### 4. C端 `/api/v1` 手写 fetch 族 19 处绕过中心栈（前端，新发现）
- 位置：`client/frontend/src/hooks/useApiConfigs.ts:5-33`、`useModelStatus.ts:30-106`、`useChangeHistory.ts`、`useUsageStats.ts:33`、`pages/ApiKeyConfigPage.tsx:52-59`、`hooks/useDeviceActivation.ts:28-32`（7 文件 19 个 fetch 点）
- 证据：各自复制 `authHeaders()`（5 份）、`throw new Error("HTTP " + status)`；中心栈的 401 清凭据踢出（`lib/api.ts:99-114`）、503 结构化提示（:116-146）、403 member_required 广播（:152-163）全部不存在；`ApiKeyConfigPage.tsx` 连 `r.ok` 都不查。
- 影响：token 过期后设置页只显示 "HTTP 401" 不回登录页；`fetchModel` 失败完全静默，AI 就绪态停留旧值误导用户。
- 修复方向：`lib/api.ts` 加可选 `API_BASE` 前缀，该族迁回 `request()`。

### 5. C端时区红线违例 ×5（后端，新发现；CLAUDE.md 口径：违例即 P1）
- 位置：`client/backend/db_lifecycle.py:188`（.corrupt 隔离件命名）、`client/backend/backup/export.py:46,67,323`（导出目录与 manifest `exported_at`）、`client/backend/migration/engine.py:190`（staging 目录戳）
- 证据：裸 `datetime.now()`（本地时间）。
- 影响：备份归档/隔离件命名与 manifest 时间戳随机器时区漂移，跨时区/夏令时排序错位；数据本身无损。
- 修复方向：统一替换 `datetime.now(UTC).replace(tzinfo=None)`。

### 6. QA 运行时数据 24MB 入库，含真实 Fernet 密钥（架构师，新发现）
- 位置：`.docker-data-qa-night/`（git 跟踪 249 个文件）
- 证据：`.docker-data-qa-night/client/.fernet_key` 为合法 Fernet key；含 `novel.db-wal/shm`、qa-evidence/*.png、compose.yml（`JWT_SECRET`/`ADMIN_TOKEN` 明文）。`.gitignore` 只挡 `.docker-data/` 未挡 `-qa-night` 变体。
- 影响：仓内死重；QA 栈密钥进 git 历史（非生产泄漏，但违反自身「密钥不入库」纪律）。
- 修复方向：`git rm -r --cached` + gitignore 补 `.docker-data-*/` + 密钥轮换；无真实用户期清理历史最便宜。

---

## 二、前端工程师视角（client/frontend + server/frontend）

概览：C端 145 个 TS/TSX 源文件，中心化 `lib/api.ts`（51 文件引用），模块级单例 ChapterStore 质量高；S端 Vue 侧单 axios 实例 + 503 自愈拦截器健康。`as any` 全仓 1 处、`@ts-ignore` 0 处，类型卫生短板集中在 `request(): Promise<any>` 一个出口。

（P1 #3、#4 见上；其余：）

### [P2] 空书 CTA「新增一章/新增一卷」无双发闸——UNIQUE 双发同族残留
- `NovelWorkspace.tsx:530-542,553-561`；底层 `useWorkbench.ts:345-401` 无 in-flight 保护，双击两次 POST `/volumes` 撞 `UNIQUE(novel_id, volume_no)`，与 dfceb17d 修的 bug 同签名。
- 对照已修好的三处：`VolumeWorkspace.tsx:920-936`、`modals.tsx:634`、`OutlineTree.tsx:150-151`。
- 修复：createVolume/createChapter 加 in-flight 闸或 CTA 挂 busy。

### [P2] LicenseProvider 模块级 `cachedVerify` 登出不清理：换账号沿用上一账号权益
- `LicenseProvider.tsx:46,83-93,131`；`lib/auth.ts:20-25` logout 不清它。登出→换号最长约 1 分钟内 tier 徽章与 `useFeature` 判定显示上一账号权益（本地判定；服务端仍强制）。
- 修复：logout 同步清 `cachedVerify` 与节流状态，或 Provider 监听 loggedIn 下降沿重置。

### [P2] `lib/ai.ts` 手写 JSON POST 与中心栈语义漂移
- `lib/ai.ts:156-198`（doJsonPost）、`:73-150`（doStreamFetch）；401 只带 status 抛出，不踢出不提示；`lib/api.ts:271-274` importParse 的 401 踢出不写 `sessionStorage.last_auth_kick_at`，绕过登录页反弹熔断。
- 修复：非流式改调 `request()`；SSE 补 401 分支；importParse 补 kick 时间戳。

### [P2] FinishModal 伏笔加载失败静默置空，完本确认基于假「无伏笔」
- `FinishModal.tsx:62` `.catch(() => setHooks([]))`；:71 卷章树 `.catch(() => {})`。失败态渲染为「无进行中伏笔」。
- 修复：失败态禁用确认钮。

### [P2] PromptManagementPage 每章串行 N+1 + 两处全吞 catch
- `PromptManagementPage.tsx:164-200` for 循环逐章 `await request(.../prompts)`——300 章的书串行 300 个请求；:142 volumes 失败静默呈现「没有卷章」；:213-215 openViewer 失败显示空内容。
- 修复：volumes 一次带回 has_stored 或并行分片；catch 区分网络失败与 404。

### [P3] `request()` 返回 `Promise<any>`
- `lib/api.ts:72-75`。字段改名编译期不报。渐进收口 `request<T>`。

### [P3] 死代码 `lib/utils.ts` 零引用
- `cn()`（clsx+tailwind-merge）全 src 无 import；删文件并核对 package.json 依赖。

### [P3] 探测类请求静默失败三连
- `useDeviceActivation.ts:28,32`、`useModelStatus.ts:106`、`AcctMenu.tsx:169`、`lib/portal.ts:26-28`。单独可接受，叠加后「网络坏了」在 C端无统一可感知信号；随 #4 迁回中心栈自然解决大半。

### 前端复核
- 三套 fetch 栈：**仍在（部分收敛）**——主栈健康；ai.ts 系 SSE 设计使然但 doJsonPost 属重复实现；`/api/v1` 族完全绕过（P1 #4）。
- 裸 catch 默认值：**大面收敛**，残留点见上。
- check-auth：C端前端已改道本机后端代打（`useAuthHeal.ts:34`、`auth_local/router.py:26`），无直连 S端残留。
- Modal 纪律：**保持良好**——全量走 `design/Modal.tsx`（45 callers），无手写 scrim；`.rail-assist` 已命名空间化。
- localStorage：健康——业务键收敛在 `lib/auth.ts`/`lib/prefs.ts`；仅 `ever_planned` 键串两处重复（口径一致）与 `lib/api.ts` 两处直写 `"auth_token"`。

---

## 三、后端工程师视角（client/backend + server/app + 云函数）

概览：C端 ~29.5k 行，db-generation 状态机、备份导入逐书 savepoint、AI 客户端显式超时纪律扎实；S端 ~10.4k 行，支付链（CAS+幂等键+T2 补偿+金额闸门+验签背压）是两仓最健壮部分。未发现 P0。

（P1 #1、#2、#5 见上；其余：）

### [P2] S端 `datetime.utcnow()` ×5（弃用 API）
- `server/app/application/payments/refund_flow.py:80,165,209,281`、`server/app/interfaces/web_api/payments.py:383`。语义 naive UTC 合规，但 Python 3.12（两 Dockerfile 均 3.12-slim）已 DeprecationWarning 且同仓两种口径并存易混比。统一替换钦定写法。

### [P2] record_usage 吞错时回滚整个请求会话，契约脆弱
- `client/backend/api_configs/usage.py:41-44`——commit 失败 rollback 无日志，会丢弃同 session 已暂存的**主流程写入**。当前 36+ 调用点顺序安全（记账先于主写入），但「FK 静默回滚」根因仍在：未来任何调用点先 add 主数据再记账，失败即静默丢数据返 200。
- 修复：独立 session 或 `begin_nested()` savepoint，失败至少 warning。

### [P2] 免登迁入端点 `source_filename` 未收紧：路径遍历 + ATTACH 字符串拼接
- `client/backend/migration/router.py:88,117`（body 直采拼 `DATA_ROOT`）；`engine.py:250` `f"ATTACH DATABASE '{staged}' AS mig_src"`；precheck（engine.py:47-72）不查文件名模式与 `..`。文件名含 `'` 即破坏 ATTACH 语句。
- 修复：白名单对齐 `scan_migration_candidates` + ATTACH 参数化。

### [P2] chat_stream OpenAI 分支 `chunk.choices[0]` 越界 + 流式用量缺 tokens_in
- `client/backend/ai_client.py:338`（OpenAI 兼容供应商流末 usage chunk `choices=[]` → IndexError，且 IndexError 不在 `_NETWORK_ERRORS`，成功生成被记成 `*_fail`）；:341-346、:361-370 流式只带 total/output tokens，用量低估。
- 修复：choices 判空跳过；done 事件补 prompt/completion 拆分。

### [P3] 死目录仍存：`client/backend/novel|projects|threads/` 仅剩 `__pycache__`，全仓无 import
### [P3] main.py 迁移装配重复/死代码
- `main.py:93-101` `apply_additive_columns(engine)` 连调两次（import+注释整块复制）；`:205-208` `ADDITIVE_COLUMNS` 死声明（真身在 db_lifecycle.py:253）。
### [P3] HTTP 客户端零复用
- `auth_local/router.py:62,72`、`service.py:405`、`update_check.py:150`、`connection.py:73` 每请求新建 AsyncClient；`ai_client.py` 每次构造新 AsyncAnthropic/AsyncOpenAI 无 `aclose()`。本地单用户影响小。

### 后端复核
- C端 ALTER except:pass：**已根治**——声明式 `apply_additive_columns`（db_lifecycle.py:258-272），非 duplicate-column 异常上抛；现存 except:pass 均为窄类型解析或无害路径。
- check-auth：**已修**——S端 `authorize.py:94-99` 硬切不回传令牌，令牌只经 `POST /api/pair/exchange` 发给持本机配对密钥者。
- run_thread 兜 BaseException：**已转为有意设计**（job_runner.py:89-93，防 CancelledError 卡死单飞槽，落 status=error）。
- 正面确认：支付回调幂等、备份导入 savepoint、限流 env 化+XFF 右起跳数、两端 CORS 白名单默认空、日志无 token/key 明文、update_check 出站校验完备。

---

## 四、架构师视角（跨端结构）

架构快照：单仓三端，C端 React SPA → 本机 FastAPI 单体 + SQLite（routers 多数直接 SQL，仅 chapters/volumes 走 repositories/）；S端 Vue SPA → CloudBase FastAPI（interfaces → application → domain，infrastructure 按 DB_BACKEND 双实现，生产唯一路径 pg_http）；brand/brand.json 与 openspec specs（60 能力）为跨端契约源。

（P1 #1、#2、#6 见上；其余：）

### [P2] S端前端 e2e 全自动挂 mock——S web↔S 后端之间回归无活体检查
- `server/frontend/e2e/fixtures.ts:4-12` 所有用例自动挂 MockApi；`test_pg_http_repos.py` 也用 MockTransport。后端删路由/改 DTO 双双全绿；nightly C端 e2e 不覆盖 S web 页面。
- 修复：留一条真后端冒烟档，或对消费端点做 schema 快照对拍。

### [P2] C端前端 fetch 栈三分 + 无缓存层手工失效（与前端视角 P1#4 同源，另见缓存面）
- 无 react-query；失效 = window 自定义事件 + 模块级缓存 + `registerRefetch` 注册表（`NovelWorkspace.tsx:952-967`）、手写去重缓存（`lib/version.ts:26`、`lib/portal.ts:12`）。跨视图一致性依赖每个开发者记得广播/注册，漏一处即旧数据。
- 修复：一次性还债引 React Query 或等价 query 层，以 key 失效替代事件广播。

### [P2] config.json 路径「三处解析、两种写法」，cwd 依赖结构仍在
- `auth_local/middleware.py:11`（字符串拼接不 resolve）、`auth_local/service.py:94-95`（resolve）、`main.py:135`（os.path.join）——三个模块各自定义 CONFIG_FILE，默认值相对 cwd。不同 cwd 启动登录态可能落到两个文件（历史 CONFIG_PATH 坑的现形）。
- 修复：收敛单一 `paths.py` 叶子模块，import 期 resolve 一次。

### [P2] C端仓储抽象只覆盖 2/15 域；S端 interfaces 也有绕过 application 直取仓储
- `client/backend/repositories/` 仅 chapter/volume；`novels/router.py` 15 处直接 execute/select；S端 `web_api/payments.py:78-86` 直接 SkuRepo/TierRepo/config_repo 绕开 application（同文件其余 35 处走 application）。业务规则（三态开关、折扣展示）长在接口层。
- 修复：不强求全量仓储化，payments 这类有业务规则的域补 application service；C端默认 router→service 收口。

### [P3] C↔S 契约靠散文规格 + 少量对拍测试，无机器可查单源
- C端调 S端 ≈7 端点，手写 DTO 两份；entitlement 有 `docs/contracts/entitlement-defaults.json` 对拍（好范例），其余端点没有等价物；openspec specs 无 CI 校验。
- 修复：entitlement 对拍模式推广到 check-auth/devices；或导出 openapi 供 C端生成类型。

### [P3] 发布门槛起伏：合 main 不部署 + S前端云上二次构建
- `.github/workflows/s-server-deploy.yml:4-6`（仅 tag/dispatch）；`yml:193-200` 自证 `tcb app deploy` 云端会重新 `npm run build` 覆盖 CI 产物（靠 `.env.production.local` 变通）。main 与生产可无限期错位；线上 bundle 实为「云端另一次构建」。C端 version 链干净无此问题。
- 修复：main→staging 自动部署（tag 上生产），构建产物指纹校验。

### [P3] 剩余手工双实现均有测试护栏，风险可控
- cnNum 双实现（nodeTitle.ts:14 注释 + client-backend-ci.yml path 触发 + parity 测试）、entitlement 对拍、brand 编译期单源。保持即可，新 twins 套用「契约文件+双端对拍」模式。

### 架构复核（09-19 P1 清单逐项）
| 09-19 结论 | 现状 |
|---|---|
| alembic 双 head + fail-open | **仍在，且加重**（生产路径根本不跑 alembic） |
| check-auth 回传 token + CORS * | **已修** |
| 前端裸 catch | **规模未变**（236 处 catch），但中心栈已硬化，残留点已具体化 |
| 三套 fetch 栈 | **仍在**（本轮量化：11 文件 28 处裸 fetch + `/api/v1` 族 19 处） |
| 无缓存层多副本手工失效 | **仍在** |
| CI 不跑 C端 vitest | **已修**（client-frontend-ci.yml:41） |

---

## 五、建议收口顺序（供拍板）

1. **半日批**：P1 #5 时区违例 ×5、P1 #6 QA 数据出库+gitignore、P3 死目录/死代码/重复装配——机械、低风险。
2. **结构批（数据层三柱）**：P1 #1 双头 merge + fail-closed、P1 #2 生产 DDL 流水线——两者一起做，S端 schema 演进一次理顺。
3. **前端一致性批**：P1 #4 `/api/v1` 族迁回中心栈（顺带消 P3 探测静默）、P1 #3 主线卡空卡覆盖、P2 双发闸/cachedVerify/FinishModal。
4. **中期**：React Query 还债、S端 e2e 真后端冒烟档、契约 fixture 推广、迁移端点收紧。

---

## 六、Change 拆分计划（09-22，拍板用）

原则：一个 change 一个主题、可独立过门禁独立归档；机械替换/死代码清理不开 change，走直修 PR（先例：死代码清理 #148/#171、bug 修复直 PR）。

**总量：9 个 change ＋ 2 个直修 PR。P1 全清只需 3 个 change ＋ 2 个直修 PR；P1+P2 清零＝7 个 change ＋ 2 个直修 PR。**

### 第一批：P1 清零（3 change ＋ 2 直修）

| # | Change | 覆盖发现 | 体量 |
|---|---|---|---|
| C1 | `s-db-migrate-pipeline`——S端 schema 演进理顺：merge revision 收敛双头、启动迁移 fail-closed、pg_http 单源 DDL 流水线（alembic 生成 SQL→部署期 apply）、schema 探针告警→门禁、CI 加 `alembic heads` 单头断言 | P1 #1 #2 | 2–3 天，DDL 流水线是大头 |
| C2 | `c-silent-data-guards`——C端静默失败→数据丢失防护：主线卡失败禁写不再落 EMPTY_ARC 基线、FinishModal 失败态禁确认、createVolume/createChapter/空书 CTA in-flight 闸、LicenseProvider cachedVerify 登出清、PromptManagementPage 批量取数＋catch 分型 | P1 #3 ＋ 前端 P2×4 | 1–2 天 |
| C3 | `c-fetch-unify`——fetch 栈收敛中心栈：`lib/api.ts` 加 API_BASE 前缀、/api/v1 族 7 文件 19 处迁回、ai.ts doJsonPost 改 request()＋SSE 补 401、importParse 补 kick 时间戳、探测三连随迁消解、（可选）request\<T\> 泛型 | P1 #4 ＋ P2 ai.ts ＋ P3×2 | ~2 天，19 处迁移＋e2e 回归 |
| PR-A | 时间口径清零直修：C端裸 `datetime.now()` ×5 ＋ S端 `utcnow()` ×5 → `datetime.now(UTC).replace(tzinfo=None)`，跑现成 TZ 抗性测试兜底 | P1 #5 ＋ P2 utcnow | 半天 |
| PR-B | 仓库与死代码卫生直修：`.docker-data-qa-night` 出库＋gitignore 补 `.docker-data-*/`＋Fernet key 轮换；删 novel/projects/threads 死目录、main.py 重复装配与 ADDITIVE_COLUMNS 死声明、lib/utils.ts | P1 #6 ＋ P3×4 | 半天 |

### 第二批：P2 清零（4 change）

| # | Change | 覆盖发现 | 体量 |
|---|---|---|---|
| C4 | `c-ai-usage-correctness`——chat_stream choices 判空＋IndexError 不再记 fail＋done 事件补 tokens_in 拆分；record_usage 改独立 savepoint＋失败告警 | 后端 P2×2 | ~1 天 |
| C5 | `c-backend-infra-hygiene`——迁移端点收紧（source_filename 白名单＋ATTACH 参数化）、config.json 三处解析收敛 paths.py 单源、HTTP 客户端模块级复用 | 后端 P2×1 ＋ 架构 P2×1 ＋ P3×1 | 1–2 天 |
| C6 | `s-contract-live-check`——S web e2e 加真后端冒烟档（或消费端点 schema 快照对拍）、entitlement 对拍模式推广到 check-auth/devices（JSON fixture 单源） | 架构 P2×1 ＋ P3×1 | 1–2 天 |
| C7 | `c-query-cache-layer`——React Query（或等价 query 层）还债，key 失效替代 window 事件＋registerRefetch | 架构 P2×1 | 3–5 天，大件放最后 |

### 第三批：可选/中期（2 change，可裁）

| # | Change | 覆盖发现 | 体量 |
|---|---|---|---|
| C8 | `s-payments-application`——payments 业务规则（三态开关/折扣展示）沉到 application service，C端立 router→service 收口范式（不强求全量仓储化） | 架构 P2×1 | 2–3 天 |
| C9 | `s-deploy-on-merge`——main 合入即部署 staging（tag 上生产）＋前端构建产物指纹校验 | 架构 P3×1 | ~1 天 |

无行动项：cnNum/entitlement/brand 手工双实现已有测试护栏（P3，保持现状，新 twins 套用「契约文件＋双端对拍」模式）。

### 排序约束

- **P1 清零建议排在打 v0.25 之前**：C1（发版带上迁移链断裂不合适）、C2（空卡覆盖是数据丢失路径）优先；C3 可与 v0.25 并行。
- 每批内 C1→C2→C3 互不依赖，可并行立项；PR-A/PR-B 随时可发。
- 拍板后按 `/openspec-propose` 逐个立项（propose→审批口→apply→archive），建议第一批 3＋2 起步。

---

## 七、09-23 复审（main 1b45b6f2）与 change 计划修订

### 基线变化

dfceb17d → 1b45b6f2：18 个提交 / 196 文件 / +17.6k −3.4k。大特性：`c-chapter-plan-ai` 卷下拆章（#473/474/476）、`c-db-per-version`（#464）、`c-volume-antagonist`（#458）、`c-write-home-rail-anchor`（#465-468）、`c-empty-card-hierarchy`（#469/470）、`brand-owner-line`（#459/460）、题材播种补回（#461）。

### 本轮新发现（新代码自带）

- **[P0] 拆章回改保存清空正文与子表**：`chapterPlanApi.saveEdit` 只发五段字段的局部 PUT，后端 `chapters/store.py` 对缺键按空写（`prose = data.get("prose") or ""`、子表 `clear()` 重建）——在有正文的章上「改这一章→保存」即清空正文/字数/章纲子表。入口可达：章纲树铅笔行、卷工作台派生视图行（含已归档章）。
- **[P1] 拆章读卡失败留上一章草稿且可保存**：`useChapterPlan.openEdit` 失败不清 draft、保存钮不看装载状态——保存即把上一章五段写进目标章（叠加 P0 连正文一起清）。
- **[P1] 库打戳失败全静默**：`main.py:128-143` `except SQLAlchemyError: pass`——下次启动该库判 `mismatch` 改名、按新库启动（书架空），日志零线索。
- **[P2] 清理门只在 UI**：`deletable_candidates` 按整个 `migration.history` 出待删清单，history 无 `tables_skipped`/`fk_violations`——规格要求「仅本次成功带回可删、部分失败不得出现清理入口」，实现放宽。
- **[P2] `planned_volume_no` 未进备份白名单**：导出 payload 与导入白名单都缺该键，roundtrip 测试用「键集完全相等」冻结旧契约（补字段反被判回归）。
- **[P2] 验收门是纸面的**：UP-11 活体 e2e 未设 `UP11_DATA_DIR` 即整组 skip；`upgrade_drill version-chain` 无 workflow 调用——规格写「每个版本 PR SHALL 以本演练全绿为验收门」。
- **[P2] 新规则手写 5–6 份无对拍**：阶段六档/行动 4×60/事件名 10 个/坎闭集散布前后端；同 change 内已漂移（`maxLength` 240 vs 244）。
- **[P2] 吞错回滚会话从一个助手复制成两个**：`novels/events.py` 新增同型（在调用方 session 上 commit/rollback）。
- **[P2] 建卷建章入口 3→6 且仍无闸**：后端改 MAX+1+upsert 后，双发症状由「UNIQUE 500」变「静默多建一章/一卷」。
- **[P2] 候选扫描每候选整库拷贝**：免登的登录页/设置页各付一次整库 IO。
- **[P3] 拆章契约小洞**：退役键硬拒漏 `plot_nodes`（200 但静默不落库）；校验键名（stage/acts）≠ 写入键名；非法 `vol_ref` 抛 500 而非 400。
- **[P3] 死表与换形**：`VolumeCastMember` 零读写 + `selectin` 空查；导出 `cast_members` 同名换形。
- **[P3] 搬运 409 判定靠文案子串**（实际文案不含匹配词 → 死分支）；单候选自动跳 preview 使隔离件只读清单不可达。
- **[P3] 规格自相矛盾**：`volume-outline` 构成字段仍列退役字段；`volume-plan-ai` 仍写 additive（机制已退役）。
- **[P3] S端 CI 路径过滤不含 `server/alembic/**`**（改迁移不触发 CI）。

### 老发现复核（要点）

- **已修**：死目录 `novel/projects/threads`、`main.py` 重复装配与 `ADDITIVE_COLUMNS` 死声明、删章静默失败；`source_filename` 部分修（dismiss/cleanup 已走白名单，start/preview 未套用）；发布门槛部分缓解（release.json 断言、installer 发布者对拍、tag 形态门禁）。
- **仍在**：alembic 双头 + fail-open、生产 pg_http 无迁移链、主线卡空卡覆盖、`/api/v1` 族（5 文件 16 处）、C端时区 ×5、`.docker-data-qa-night` 249 文件、S端 utcnow ×5、record_usage、chat_stream `choices[0]`、FinishModal、PromptManagement N+1、`request<any>`、`lib/utils.ts`、探测三连、S端 e2e 全 mock、无缓存层、config.json 三处（实为四处）解析、仓储 2/15。

### 关键新认知（改变 C1 解法）

alembic 两条分支不是简单并行：`a001_users_surrogate` **整表重建** users/codes/device_grants/device_registry（新表列清单显式写死），而 `a1b2c3d4e5f6`（注销四列）与 `c4d5e6f7a8b9`（codes.refund_requested）是加列。**merge revision 的隐式排序会先跑加列分支**（按 revision 字符串 `c4d5e6f7a8b9` < `e8f2a4b6c8d0`），重建随即把这两组列吃掉。故 C1 采用**线性化**（`a1b2c3d4e5f6.down_revision` → `e8f2a4b6c8d0`），并以「fresh sqlite upgrade head 后与 ORM 元数据逐列对拍」的测试钉住。

### 修订后的 change 计划

**第一批（已立项，5 个 change，共 96 任务）**

| # | change | 主题 | tasks |
|---|---|---|---|
| C1 | `s-db-migrate-pipeline` | 链线性化＋启动 fail-closed＋生产 DDL 单源＋CI 单头断言＋S端 utcnow | 18 |
| C2 | `c-silent-data-guards` | 主线卡失败禁写＋完本清单失败态＋建卷建章 in-flight 闸＋权益缓存登出清＋提示词总览批量 | 20 |
| C3 | `c-fetch-unify` | `/api/v1` 族迁回中心栈＋认证失效统一出口＋AI 401＋探测显式化 | 16 |
| C4 | `c-db-version-hardening` | 打戳可见＋清理门下沉＋备份白名单＋验收门进 CI＋死表＋C端时区 | 23 |
| C5 | `c-chapter-plan-guards` | 回改保存保全（P0）＋读卡守卫＋竞态守卫＋回执分流＋409 判定 | 19 |

**直修（不开 change）**：`.docker-data-qa-night` 出库＋gitignore 补 `.docker-data-*/`＋Fernet 轮换；`lib/utils.ts` 死代码删除。原「时区清零」直修单元已折入 C1（S端 utcnow）与 C4（C端裸 now）。

**第二批（待立项）**：`c-ai-usage-correctness`（chat_stream＋record_usage＋events.py 三处吞错）、`c-backend-infra-hygiene`（迁移端点收紧＋paths.py 单源＋HTTP 复用＋plot_nodes/ref 校验）、`s-contract-live-check`（S端 e2e 真后端冒烟＋契约 fixture＋规则副本对拍）、`c-query-cache-layer`（React Query 还债）、`s-payments-application`、`s-deploy-on-merge`。

**实施顺序建议**：C5（P0）→ C2（P1 数据丢失路径）→ C1（P1 S端）→ C3（P1 fetch）→ C4（P2 群）；C1 与 C4 同批协调（都动后端但不同文件）。P1 清零压在打 v0.25 之前。
