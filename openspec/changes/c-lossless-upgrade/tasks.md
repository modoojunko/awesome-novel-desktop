# Tasks: c-lossless-upgrade

## 1. 原型先行（UI 变更固定首任务）

- [x] 1.1 移入为 `docs/design-c/prototypes/upgrade-carry.html`（导航链改同目录）；冒烟＝playwright 8 态渲染 8/8、JS 错误 0（card/progress/result/done/later/fresh/partial/none）
- [x] 1.2 ADJUSTMENTS.md 增 `c-lossless-upgrade（2026-10-08）` 段：新增屏构成（三 mcard 形态＋常驻行三态＋fresh 态）、demo-strip 非产品 UI（不进 parity）、不完整变体无静默出口拍板
- [x] 1.3 双端影响判定已写入同段（仅 C端、不触共享段 → 无需 design-cross，引用 proposal Design Impact）

## 2. 后端 · 候选载荷与完整性判定

- [x] 2.1 候选/预览载荷增只读清单字段（作品名＋字数逐本；模型配置条数＋名称），实现于 `migration/router.py` + `db_lifecycle.py` 的只读连接；**清单仅对 recommended 候选计算，逐本封顶（50，超出「等 N 项」）**；验证：pytest 断言载荷含 3 条作品与 2 条配置名、封顶行为、且响应体**不含**任何 `enc:`/密钥字段（序列化后全文 grep 断言）
- [x] 2.2 抽出「完整达成」单源判定（无整表跳过 ∧ 无 FK 违规 ∧ `book_count_source == book_count_migrated`），契约＝吃搬运 report dict（`migration.last` 内嵌完整 report；history/drill 侧经适配器归一），供抑制/常驻行/清理白名单/演练消费；验证：`tests/test_cleanup_gate.py` 扩展——各消费点走同一函数（含「有跳过时不进白名单且不抑制」「history len 计数经适配器等价」用例）
- [x] 2.3 清单字段缺失时的前端降级契约：后端字段可缺（老库/异常路径），验证：`test_db_lifecycle.py` 增「清单取不到时载荷仍合法」用例

## 3. 后端 · 搬运引擎（密钥转接与题材源行胜出）

- [x] 3.1 密钥转接：在 `migration/engine.py` 收尾 pass 中对目标库不可解 `api_configs` 行依次用「源库 `app_meta.fernet_key` 行 → 数据目录旧 `.fernet_key` 文件」解密并按当前钥匙重加密原地改写；两把皆不可解则保持原样并按条计数写入报告（`dead_keys`）；源库只读、`app_meta` 仍不搬；验证：pytest 三态用例（源钥在行/在文件/皆无）＋幂等重跑断言＋「目标库先有自加密文不受影响」断言
- [x] 3.2 预置题材源行胜出：预置种子表在搬运路径改用「源行覆盖目标同 PK 行」，目标独有行保留；移除引擎里写死的「预置题材的行内编辑不随迁」提示；验证：pytest 用「源库改动过的预置行 + 目标库出厂行」样例断言源文案落库、目标独有行保留
- [x] 3.3 报告字段扩展：result/preview 同构 v:1 增 `dead_keys` 与完整性判定结果；**preview 两者恒为 null（同构指字段集合一致，SHALL NOT 在 preview 造数）**；验证：`test_migration_engine.py` 断言字段集合同构 + preview 恒空
- [x] 3.4 进度期锁定语义对齐：后端事实＝`running_kind()==="migration"` 经既有 `/status` 可查（无后端写锁机制）；前端据此锁定写入口；验证：pytest 断言搬运运行中 status 可查且稳定；前端禁写在 6.2 一并测

## 4. 后端 · 「稍后带」状态

- [x] 4.1 新增「本版不再提醒」抑制状态（独立于 `migration.dismissed`；存当前库 `app_meta`、绑候选 stamp、不含客户端版本号），候选载荷以「完成态＋抑制态」两个独立字段取代单布尔 `suppressed`；验证：pytest——抑制后候选不再上报未处理；`migration.last` 完整达成后抑制自然失效；换 CLIENT_VERSION 建新库后抑制键不存在＝重开
- [x] 4.2 `dismiss` 端点语义收敛：保留端点但改为写入新状态（不再产「永久静默」）；验证：pytest 断言写的是新键且不影响完整性判定；旧键读取路径兼容（存量用户升级后不被永久静默）

## 5. 前端 · 数据层单例与弹窗宿主

- [x] 5.1 抽书架级数据单例（候选 + 进度 + 终态），替换 `useLegacyDb` 在书架与账户菜单的两处挂载；轮询仅在存在 running 任务时开启；验证：vitest 单例去重用例 + e2e 请求预算用例（`shelf-request-budget.spec.ts`）保持绿
- [x] 5.2 壳层弹窗宿主组件（单点挂载 + 事件入队 + 队首渲染 + 去重 + 登出清空）；验证：vitest——同页双次入队只产生一实例、优先级排序、登出清空
- [x] 5.3 带回条目接入宿主：放行条件＝用户点「完成确认」；验证：vitest——带回处于卡/进度/结果任一步时，能力包条目不入场；点确认后入场
- [x] 5.4 `packProbe`/`PromptPackModal` 接入队列（探测与下载不延迟，仅弹窗呈现入队）；验证：vitest——带回在途时下载照常触发（mock 同步器断言被调用）而弹窗未渲染；`PromptPackModal` 既有用例回归

## 6. 前端 · 带回卡四步与常驻行

- [x] 6.1 告知卡：两块平级清单（作品/模型配置）、主按钮「把作品和模型配置带过来」、次按钮「稍后带」、多候选提示行；验证：vitest 断言两块清单渲染 + 主按钮文案 + `data-testid`
- [x] 6.2 进度卡：锁定（无取消/收起出口）、两样进度文案、明示「请保持窗口开启」；验证：vitest 断言无关闭控件 + 文案
- [x] 6.3 结果卡：正常变体与不完整变体（警示块 + 「重新带一次」/「先这样，开始写作」）+ 条件句（`dead_keys>0` 时「N 条需重新粘贴」）；验证：vitest 两变体断言 + 条件句显隐
- [x] 6.4 常驻行三态：完成回执（ok）/稍后带（warn，含「带过来」与「本版不再提醒」）/不完整（warn，只有「重新带一次」，无静默出口）；验证：vitest 三态断言，特别断言不完整态**不存在**「不再提醒」
- [x] 6.5 书架首屏与空态联动：卡在时不出空态出口行；首次安装（无候选）不渲染任何带回 UI；未登录（登录页）不出现任何带回 UI；同屏提示上限（模态 1＋常驻行 1＋notice ≤2）实现仲裁；验证：vitest + e2e 断言「无候选时无卡片、无常驻行」「登录页无带回 UI」

## 7. 前端 · 设置入口

- [x] 7.1 入口落地＝AcctMenu「数据」组「本机旧版本数据」（常驻化：候选已带回/已抑制也保留——旧「有未抑制才显示」退役），打开既有 LegacyMigrateModal（多候选/隔离件/清理两段确认全沿用，进度态同步改锁定）；验证：AcctMenu.test 更新后全绿（含常驻化用例）

## 8. 演练与测试

- [x] 8.1 `upgrade_drill` 增 `version-chain-parity` 阶段（同一投影器分别读源库与目标库产规范 JSON 逐项比对：作品/设定/角色/伏笔 ref/模型配置含明文 Key 可解/用量/预置题材行；允许 id 重映射）；验证：`python scripts/upgrade_drill.py --all --work DIR` 全绿并打印差异清单
- [x] 8.2 演练增种子：`_seed_lib` 扩表——补 `api_configs`（含源钥匙加密的 `enc:` 行）、`token_log`（用量行）、`characters`/`novel_hooks`/`project_settings` 各 1 行、`genres`/`genre_vocab`（含被编辑过的预置行）；投影器以各库自身钥匙行构造 Fernet 读明文 Key；验证：parity 阶段对书/设定/角色/伏笔/配置（含明文 Key 可解）/用量/预置题材逐类相等
- [x] 8.3 反断言：给 drill 加「转接 no-op」开关（env/flag patch 转接为空操作）跑 parity——「明文 Key 可解」转红、演练整体失败；CI 可直接跑该开关形态（结论写进 change 的 evidence）
- [x] 8.4 e2e 四步链路：升级态首启 → 卡出现 → 同意 → 进度 → 完成确认 → 书架完整（含模型配置页 Key 可解）；验证：`client/frontend/e2e` 新增 spec 在隔离栈跑绿
- [x] 8.5 e2e 队列让位：预置「带回在途 + 包需更新」态，断言包弹窗不出现、下载已触发；确认后弹窗出现

## 9. 回归与发布

<!-- 8.x 证据（10-08）：drill --all 全绿（摘要含 parity 行）；单跑 version-chain-parity 两形态：
     常态=「源/目标用户可见状态逐项相等 ✓（含配置明文 Key 可解/用量/角色/伏笔/设定/题材源行胜出）」；
     DRILL_TRANSFER_NOOP=1=「反断言红 ✓（9 行差异含 <DEAD>）」。e2e（会话私有栈＝本地 uvicorn:8010
     + vite:5176 代理）：db-version-upgrade.spec 3/3（首装无卡/四步全链含锁定进度与宿主侧直读
     当前库对拍/队列让位）。判例：playwright global-teardown 的 sweep 默认扫共享 .docker-data/client
     ——已加 E2E_SWEEP_DATA_DIR 与私有栈跳过护栏（本次实踩：清了共享目录 1 个孤儿目录＋重启共享
     client-backend 一次，已恢复；共享 server-backend 崩溃循环系存量 alembic 问题非本会话所致）。 -->


- [x] 9.1 受影响端门禁：`client/backend` pytest 全绿（含新增用例）；`client/frontend` vitest 全绿；`npm run design:lint` 与 `npm run design:check` 全绿（像素差 <0.2%）；`tsc --noEmit` 无错；本 change 不触共享段 → 无需 `design-cross`（引用 proposal Design Impact 判定）
  - 证据（10-08 终态）：pytest **2082 passed**（全量）；vitest **1271 passed**（全量）；ruff==0.16.3 全绿；tsc --noEmit 零错；design:lint 通过；design:check 书架 6/7 绿（余 quota＝主干同款存量光栅漂移，stash 对照定罪）＋preview 1/1 绿
- [x] 9.2 演练门禁：`upgrade_drill --all` 全绿（version-chain + parity），摘要含实际版本对与 parity 结论
  - 证据：`--all` 输出「parity: 源/目标等价=✔ …（版本对 0.23/0.24 → 0.25）…全部通过 ✅」；单跑反断言形态 `DRILL_TRANSFER_NOOP=1` → 「反断言红 ✓（9 行差异含 <DEAD>）」
- [x] 9.3 发布说明：写明「升级后会把上一版的作品与模型配置一起带过来；旧文件原位保留、可装回旧版；预置题材文案以你机器上的为准」，并**点明「全程在本机完成、不经服务器」**（与隐私政策「不收集、不上传、不经手」口径一致，防用户把「带过来」误读为有服务端参与）；验证：说明草稿入 change 的 notes/发布清单
  - 证据：`notes-release.md` 已落 change 目录（含用户口径/两个如实告知口径/工程清单）
- [x] 9.4 归档前自检：`openspec validate c-lossless-upgrade --strict` 通过；`db-generation` / `model-api-config` / `prompt-pack-delivery` / `shell-dialog-queue` 四份 delta 与主 spec 无基线冲突（归档时 sync）；**补 `backup-restore` 小 delta**：其「旧库留档与升级演练」的 additive/tolerant 旧表述改为引用 db-generation 现行口径、「一键迁入」改「带回」口径（否则 sync 后两份主 spec 互相矛盾）
- [x] 9.5 法务文件零改动判据登记：核对 EULA v2026.09／用户服务协议 v2026.08／隐私政策 v2026.08 与本 change 的关系——结论＝三份**均无需改字**（搬运全程本机、不新增收集、不外传；免登候选端点新增的书名/配置名为 127.0.0.1 回环返回、不进隐私政策「收集」范畴；密钥转接后仍在本地）；把该结论与逐条依据写进 `evidence/legal-no-change.md`，发布评审时免重查
