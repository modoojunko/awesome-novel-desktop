## Context

- 判定层 `ai_state.py:config_key_usable` 判「Key 可用」＝`api_key` 字段非空 + `last_test_status` 非失败（O-9）；实际调用 `ai_client.get_ai_client_for_novel` 才真正 `decrypt_api_key`，解不出非空明文即抛 `ValueError`。门控 `require_novel_model`（`auth_local/deps.py:92`）复用判定层，判据缝隙导致失配态穿透成裸 500（`volumes/ai_plan._generate` 把 `get_ai_client_for_novel` 放在 try 外，且全仓 30+ 端点同模式）。
- `api_configs/crypto.py`：钥匙存 `{DATA_ROOT}/.fernet_key` 文件，`_get_fernet()` 同步首次读/生成，`DATA_ROOT` 不可写时 `_fallback_plaintext` 明文降级；`decrypt_api_key` 吞 `InvalidToken`/钥匙缺失返回空串。同步函数被 async 调用方直调。
- `decrypt_api_key` 调用面：`ai_client.py`（400/438 `get_ai_client_for_user` 遍历、502 `get_ai_client_for_novel`）、`api_configs/service.py`（114 连接测试、296 掩码、751 User→ApiConfig 迁移加密；788 为掩码序列化不涉及）、`backup/export.py`（339/380 导出明文）、`backup/importer.py`（782 导入重加密）。另：`main.py:130-186` 的 `config.json`→User 迁移**不加密**（明文进 legacy `User.api_key`），真正的加密在随后的 `migrate_user_configs`（`main.py:188-197` → `service.py:751`）。
- `app_meta` 是应用级 KV 表（`key String(64) PK` + `value Text`），现有键 `schema_id`（库结构指纹）、`drift_accepted`（审计）；启动期由 lifespan 在建表/补列/打戳之后写入。**库间迁移引擎**（`migration/engine.py`）的 `EXCLUDED_TABLES = {"app_meta"}` 是唯一排除——`api_configs`（含 `api_key` 密文列）**会**随迁入计划搬进新库，而源库钥匙行不随行。
- 前端只消费 `detail.reason`/`ai_state` 枚举与后端下发的 `message`（`intro-genre-settings` spec 钉死），文案单源在 `ai_state.no_key_message`。

## Goals / Non-Goals

**Goals**

- 失配态（字段非空但解不开）在门控层归 `no_key` → 503 引导，前端零改动消灭裸 500。
- 钥匙入库：库自包含，迁移/备份/恢复天然带钥匙；旧文件在则零重加密迁移，用户存量 Key 无感。
- 门控覆盖审计：`get_ai_client_for_novel` 可达的 HTTP 入口全部挂 `require_novel_model`。

**Non-Goals**

- 不改加密算法/密文格式（`enc:` Fernet 原样）；不引入 OS 钥匙链（DPAPI/Keychain）——绑机器会让「库+钥匙整体搬家」场景再次死文，与本次目标相反。
- 不做跨设备同步、不把钥匙放进备份包。
- 不改备份导出/导入行为（明文导出/重加密导入维持现状）。
- 不改前端（枚举/文案均后端单源）。

## Decisions

1. **钥匙入库位置＝`app_meta` KV 表新行（键 `fernet_key`），不建新表。**
   `app_meta` 语义即「应用级元数据」，现有键只有 `schema_id`/`drift_accepted`，启动期已在该表写入；整库留档/搬移时随库走。备选「独立单行表」「User 表加列」均无增益：单行表多一个模型文件，User 表是用户域不是应用域。
   注意：**库间迁移引擎会搬 `api_configs`**——`migration/engine.py` 的 `EXCLUDED_TABLES` 只有 `app_meta`，旧库配置密文随迁入计划进新库而钥匙行不随行，新库钥匙若非源库钥匙即成死文。有 503 引导兜底非灾难，但迁入报告（`report["notes"]` 机制）SHALL 对此给出显式提示（见 model-api-config delta）；legacy 手工救援链路（列交集搬运）同样适用。

2. **同步/异步边界＝模块级缓存 + 启动期异步初始化。**
   `encrypt_api_key`/`decrypt_api_key` 保持同步签名（调用面 12 处不动）：`_get_fernet()` 改读模块级 `_fernet` 缓存；新增 `async init_crypto(session)` 在 lifespan **打指纹戳之后、`config.json`→User 迁移与 `migrate_user_configs` 之前**调用（`main.py:130-197` 两步内含 `encrypt_api_key`，`service.py:751`——若 init 排在其后，fail-fast 语义下 RuntimeError 启动崩）——读 `app_meta.fernet_key` 行（有→装载；无→旧文件抄库或新生成），写缓存；并发首启 INSERT 撞 PK → rollback → 重读装载先到者。**未初始化即调用 → `RuntimeError` 快速失败**（生产 lifespan 必初始化；pytest conftest 全局夹具初始化；crypto 提供 `_reset_for_tests()` 供钥匙轮转/迁移态用例重置模块缓存）。**双源一致性观测**：「文件在＋行在＋内容不等」（破约唯一可观测时刻）→ `uvicorn.error` warning（只报事实，不碰钥匙内容）；init 顺手统计死文配置数打进启动日志（判定层之外的补偿面，设置页徽标不入本次 scope）。备选「每次调用现开 session 异步读库」要改 12 处调用点为 await 且引入每请求 IO——弃。
   明文降级机制（旧 `_fallback_plaintext`）**随重写退役**：init 失败一律 RuntimeError 快速失败，不存在任何明文存储降级路径——目录不可写时 SQLite 本就无法建库/写行，应用先于 crypto 不可用，该通道在钥匙入库后已无意义（spec 钉的是 fail-fast，实现从之）。
   并发首启（多栈共享 DATA_DIR，09-24 事故土壤）：INSERT 钥匙行捕获 `IntegrityError` → rollback → 重读该行装载先到者（迁移来源相同则内容一致，零分叉）。

3. **迁移＝文件内容原样抄库，零重加密；旧文件保留不删。**
   钥匙只是字节串，抄入库后 Fernet 实例照旧解旧密文——主检出等存量栈的用户 Key 无感保命，不需要任何「重加密 sweep」。迁移成功后旧文件**保留为只读遗留**：同机新旧版本混跑/回滚是日常（主检出跑旧版、worktree 跑新版共用一族数据目录），旧版读文件、新版读库行，内容一致则密文恒可解；若迁移后删除文件，旧版会重新生成新文件＋新钥匙，与库内密文全对不上——再次制造死文。44 字节死重，买回滚安全。备选「解出全部明文用新钥匙重加密」复杂且有中途崩溃窗口——弃。

4. **判定层改法＝`config_key_usable` 内联解密，`no_key` 细分文案以参数下发。**
   `config_key_usable` 增加 `decrypt_api_key(config.api_key)` 非空维度（Fernet 解密微秒级，判定层每次调用一次解密可接受；**否决** `functools.lru_cache` 按密文串缓存——「钥匙换回旧钥匙」场景会吐陈旧结果，且开销不值得）。`no_key_message(config)` 增加第三分支：字段空→「暂无可用 API Key…」；测试失败→「连接测试失败…」；**非空但解不开→「API Key 无法解密（加密钥匙已更换）— 请重新粘贴保存」**；三分支判别取固定优先级「解不开 优先于 测试失败」（已进 spec）。`compute_ai_state` 结构不动（`no_key` 枚举不增，前端枚举/分派零改动）。
   `user_has_ai_key` 的 ApiConfig 查询从 `api_key != ""` 改为「取 active 配置后逐个按可解密口径判」——数量个位数，无需优化。
   `ai_client.get_ai_client_for_user`（遍历找可用 Key 的兜底路径）同步跳过解不开的配置，与判定层同口径。

5. **裸 500 的最后防线＝门控覆盖，不在 `ai_client` 层 catch。**
   `ai_client` 是客户端层不该认识 HTTP（既有分层边界，spec「后端模型调用分层」钉死）；`get_ai_client_for_novel` 的 `ValueError` docstring 即「正常路径不会走到这里」。因此治法是把「正常路径」补全：审计确认**唯一缺口是 story 推演**（`/api/story/{deduction_id}/round` 等 7 端点只挂 `require_ai_access`），且 story 路由路径参数只有 `deduction_id`（`project_id` 在 `/init` body 与会话引擎内部），`require_novel_model`（依赖 path 参数 `project_id` 的 DI 签名）**无法 drop-in 补挂**——修法：把判定核心抽成 `ensure_novel_model_ready(db, user_id, project_id)`（`require_novel_model` 复用它），story 侧加变体 dependency 从 `_active[deduction_id].project_id` 取值调用（保持「门控只在 dependency」的 review 清单合规）。勘误：story 死文现状**不是 500 而是静默空转**——`character_agent.py:251` 的 ValueError 被 `engine.py:306` `gather(return_exceptions=True)` 过滤吞掉，表现为空回合、无任何用户信号；修后为 503 显式信号。其余调用面（write/auxiliary 4 处上游、plot_sim、ai_check、ai_draft、characters_ai、ai_router、style_shadow、prompt、reconcile_router、ai_plan）双门控已齐；archive 两处为 try/except 降级路径非门控对象。grep 门禁清单（`intro-genre-settings` spec 分层节）增加第 ④ 条近似检查＋静态映射/豁免表（已进 delta）。

6. **e2e 演练以迁移双态各验一次。**
   态 A（文件在）：启动→钥匙行=文件内容→既有 key 配置连接测试通过、AI 调用正常。态 B（文件不在+库有死文）：启动→新钥匙→该配置触发 AI → 503 `no_key` + 「重新粘贴保存」文案 → 重填 key 后恢复。demo 栈（5274）现状恰是态 B 的真实样本。

## Risks / Trade-offs

- **「db 单独流出时 Key 不可读」的保护随钥匙入库而消失**（db 流出即钥匙流出）——现状该保护已名存实亡（钥匙文件与库同目录，整目录泄露时两者同丢），本次显式放弃以换结构自包含；若未来威胁模型升级（云同步备份、多设备同步），应引入用户口令派生钥匙或 OS 钥匙链，而非回退文件方案。
- **fail-fast 边界**：未初始化即调用加解密 → `RuntimeError`；init 失败（库读写异常）→ `RuntimeError` 启动崩——无明文降级通道（见决策 2 的退役说明）。只读 FS 下 SQLite 本就写不了、应用起不来，故 fail-fast 无新增不可用面。
- **`no_key` 文案三分支依赖判定时能区分「字段空/测试失败/解不开」**——`no_key_message` 需要在 `config_key_usable` 之外多解一次密（或返回细分原因）；实现取「解不开优先于测试失败」的判定顺序，两处解密的微小开销可接受。
- **前端文案透传：已核实 6 处本地映射会盖掉后端 message**（`AiWriterAssistant.tsx:54`、`HooksSettingForm.tsx:587`、`WorldSettingPanel.tsx:257`、`SettingsView.tsx:1259`、`StoryArcForm.tsx:202`、`GenreSettingForm.tsx:776`；`useModelStatus.ts:37` 直取 message 无问题）——死文态若不透传会显示「先去模型配置添加」而非「重新粘贴保存」，tasks 1.7 承接，proposal Impact 已按「仅文案透传小改」表述。**回滚边界声明**：「旧文件买回滚安全」只对**能开库的旧版**兑现——更老版本（无 tolerant 逻辑，`db_lifecycle.py:93-137` 是新代码）面对超集库会整库隔离，该风险先于本 change 存在，不在本次范围。
- **迁移写库失败时旧文件保留**（不删）——RuntimeError 启动崩，下次启动重试；期间应用未完成启动、无密文读取发生，无死文窗口。
