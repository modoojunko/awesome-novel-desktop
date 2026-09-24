> 实现顺序：先 1（钥匙入库，含测试基座）后 2（判定层）——2 的死文态用例依赖 1.3 的钥匙轮转/重置钩子。

## 1. 钥匙入库：`app_meta` 行 + 启动初始化（`.fernet_key` 文件退役）

- [x] 1.1 `api_configs/crypto.py`：`_get_fernet()` 改读模块级缓存；新增 `async init_crypto(session)`——读 `app_meta.fernet_key` 行：有→装载；无→旧文件**先 `Fernet(content)` 试构造**（合法→原样抄库零重加密；非法（空/截断/非 Fernet）→按不存在处理：生成新钥匙＋warning＋坏文件保留）；写库撞 PK（并发首启）→ rollback 重读装载先到者；迁移成功后旧文件**保留为只读遗留**（不删，支持同机新旧版本混跑/回滚）。未初始化调用 → `RuntimeError` 快速失败；`_fallback_plaintext` 仅 init 失败路径可达（正常恒 False）。
- [x] 1.2 `main.py` lifespan：`init_crypto` 挂在**打指纹戳之后、`config.json`→User 迁移与 `migrate_user_configs` 之前**（`main.py:130-197` 内含 `encrypt_api_key`，排在 init 后会启动崩或静默明文）；启动日志记 migrated/generated；「文件在＋行在＋内容不等」→ warning（只报事实）；顺手统计死文配置数进启动日志。
- [x] 1.3 `crypto._reset_for_tests()`：清 `_fernet`/`_fallback_plaintext`（死文态/迁移态用例的钥匙轮转依赖）。
- [x] 1.4 pytest conftest：全局 `init_crypto` 夹具（仿 `_session_test_db` 模式，依赖其保证表已建）；存量直调 encrypt/decrypt 的 4 文件约 8 处（test_api_format/test_ai_member_gate/test_backup_export/test_backup_import）回归。
- [x] 1.5 单测：迁移态（文件合法在→钥匙行=文件内容→旧密文可解→文件保留不变）；非法文件态（空/截断→新钥匙＋warning→既有密文按死文引导，加解密不抛未处理异常）；新生成态（文件不在→新钥匙入库）；并发首启撞 PK→重读装载；备份导出仍明文/导入仍重加密（既有断言不回归）。
- [x] 1.6 `migration/engine.py`：迁入报告（`report["notes"]`）对「按当前钥匙不可解」的 `api_configs` 密文配置提示需重填（`EXCLUDED_TABLES` 只排除 `app_meta`，密文会随迁入计划进新库）。
- [x] 1.7 场外消费者：`docs/volume-plan-prompt-experiment/run.py` 直读 `.fernet_key`——改从 `app_meta` 读或注明仅适用旧数据目录。

## 2. 判定层：可解密性入判据（消灭裸 500/静默空转）

- [x] 2.1 `ai_state.config_key_usable` 增加「`decrypt_api_key` 解出非空明文」维度；三态（字段空/测试失败/死文）可区分，**判别固定优先级「解不开 优先于 测试失败」**（不引 lru_cache——钥匙换回旧钥匙场景吐陈旧结果）。
- [x] 2.2 `ai_state.no_key_message` 三分支文案：空→「先去模型配置添加」；测试失败→「请检查或重测」；死文→「API Key 无法解密（加密钥匙已更换）— 请重新粘贴保存」。
- [x] 2.3 `ai_state.user_has_ai_key`：现状 `limit(1)` 单发改为 `.all()` 逐个按可解密口径判定（行为变更：修复「最新一条死文、第二条活」错位）。
- [x] 2.4 `ai_client.get_ai_client_for_user`（400/438，现状同为 limit(1)）：同口径取候选逐个判可解密，跳过死文配置。
- [x] 2.5 单测：三态判定矩阵（均 `no_key`；可解→ready 前提满足）；死文＋测试失败并存→文案指向重新粘贴保存；死文态走 `/volumes/ai/options` 门控断言 **503 非 500**（金丝雀）；`user_has_ai_key` 全死文不回退放行；`get_ai_client_for_user` 跳过死文。
- [x] 2.6 前端文案透传：6 处本地映射改直取后端 `message`（`AiWriterAssistant.tsx:54`、`HooksSettingForm.tsx:587`、`WorldSettingPanel.tsx:257`、`SettingsView.tsx:1259`、`StoryArcForm.tsx:202`、`GenreSettingForm.tsx:776`；`useModelStatus.ts:37` 已合规）；vitest 补透传断言。

## 3. 门控覆盖：story 变体 dependency ＋ grep 门禁 ④

- [x] 3.1 `auth_local/deps.py`：抽取判定核心 `ensure_novel_model_ready(db, user_id, project_id)`（`require_novel_model` 复用之，签名行为不变）。
- [x] 3.2 `story/router.py`：新增变体 dependency 从 `_active[deduction_id].project_id` 取值调用判定核心，挂到 `/round` 等全部 AI 端点（保持「门控只在 dependency」合规）；修后死文态＝503 显式信号（现状＝静默空回合）。
- [x] 3.3 分层 grep 门禁追加第 ④ 条（门控覆盖近似检查），静态映射/豁免表落地（豁免：`ai_client.py`、`tests/`、`ai_prefill.py`、`novels/router.py` suggest-meta、`archive/service.py`/`archive/reconcile.py` 降级路径），写入门禁注释与 CI 既有检查位；同步进 `intro-genre-settings` 分层 requirement 的归档 sync。

## 4. 演练与门禁

- [x] 4.1 隔离栈演练态 A（文件合法在）：启动→连接测试通过→AI 调用正常→旧文件保留且内容不变（存量 Key 无感）。
- [x] 4.2 隔离栈演练态 B（文件不在/非法＋库有死文）：AI 调用→503 `no_key` +「重新粘贴保存」文案→设置页重填 Key→调用恢复（demo 栈 5274 现场样本）。
- [x] 4.3 库间迁入演练：新库迁入旧库数据→报告含死文提示→相关配置 503 引导非 500。
- [x] 4.4 全量门禁：pytest（backend）、vitest（前端透传断言）、e2e 全量（存量 e2e 无 500 断言依赖，U5 断言 `[401,503]` 同向）；`openspec validate --strict`。
