## Why

2026-09-24 实锤事故：演示栈数据目录的 `.fernet_key` 文件被重置后，库里的 API Key 密文全部解不开，门控判据（只查字段非空）放行 → 深层 `decrypt_api_key` 返回空 → `get_ai_client_for_novel` 抛 `ValueError` 无人接 → 用户看到裸 500，且设置页显示一切正常，无从知道要重填 Key。两个根因：①判定层「Key 可用」与实际调用「Key 可解密」判据不一致，失配态穿透成 500；②Fernet 钥匙独立存放在数据目录文件里，与库的生命周期没有任何绑定保障——搬库、清理数据目录、选择性删文件都会让全部 Key 静默变死文。

## What Changes

- **判定层纳入可解密性**：`config_key_usable` 增加「`decrypt_api_key` 解出非空明文」维度；密文解不开归入 `no_key` → 既有 503 + `detail.reason` 引导链路（前端零改动），消灭裸 500。
- **`no_key` 文案三分支**：字段空（「先去模型配置添加」）/ 连接测试失败（「请检查或重测」）/ **密文无法解密（新增：「加密钥匙已更换，请重新粘贴保存」）**。
- **`user_has_ai_key` 对齐**：现状为 `limit(1)` 单发查询（非遍历），改为取候选 `.all()` 逐个按可解密口径判定（**行为变更**：修复「最新一条死文、第二条活」时判定层放行、兜底层找不到 Key 的错位）；`ai_client.get_ai_client_for_user`（400/438）同口径。
- **门控覆盖审计**：实勘确认唯一缺口是 **story 推演路由**（7 端点只挂 `require_ai_access`，路径参数无 `project_id`，`require_novel_model` 无法 drop-in）——抽取判定核心 `ensure_novel_model_ready` 供 story 变体 dependency 从会话引擎取 `project_id` 调用。勘误：story 死文现状不是 500 而是**静默空回合**（ValueError 被 `gather(return_exceptions=True)` 吞掉）；其余全部调用面双门控已齐（write/auxiliary 上游、plot_sim、ai_check、ai_draft、characters_ai、ai_router、style_shadow、prompt、reconcile、volumes/ai_plan），archive 两处为 try/except 降级非门控对象。
- **Fernet 钥匙迁入数据库**（**BREAKING**：`.fernet_key` 文件退役）：钥匙作为一行数据存入 `app_meta` KV 表，库成为自包含单元；启动期 `init_crypto()` 负责加载/迁移/生成——旧文件存在则**原样抄入库存钥匙**（密文零重加密，存量 Key 无感保命），不存在则生成新钥匙；迁移成功后旧文件**保留为只读遗留**（同机新旧版本混跑/回滚时旧版读文件、新版读库行，内容一致，密文恒可解）。**安全取舍（显式声明）**：钥匙入库后「库文件单独流出时 Key 不可读」的保护消失（db 流出即钥匙流出）——该保护在现状下本已名存实亡（钥匙文件与库同在一个数据目录，能拿到库的攻击者通常同样能拿到钥匙文件），本 change 以此换取「库和钥匙必须一起走」从人肉纪律变成结构保证；备份包不含钥匙材料的行为不变（导出 Key 本为明文）。
- 备份链路不受影响：导出包内 Key 为明文（导出解密/导入重加密），钥匙迁移不改变备份行为，备份包**不含**钥匙材料（包内 `api_key` 本身为明文，既有行为）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `intro-genre-settings`：「AI 就绪状态的单一事实源」——`ready` 判据增加「Key 可解密出非空明文」；`no_key` 文案区分三分支（新增「密文无法解密」，固定优先级「解不开 优先于 测试失败」）；`user_has_ai_key` 对齐。原三场景全保留，新增两场景（密文解不开 → 503 no_key 引导重填不 500；全死文时用户级回退判据不放行）。另 MODIFIED「后端模型调用分层」——grep 门禁清单追加第 ④ 条（门控覆盖近似检查＋静态映射/豁免表）＋story 端点场景。
- `model-api-config`：新增「Key 静态加密与钥匙同库自包含」requirement——钥匙存 `app_meta`、稳态不依赖文件、迁移等价（文件在→零重加密；非法文件→按不存在处理）、启动顺序约束（先于任何加密调用）、并发首启消解、库间迁入死文提示、备份行为不变。

## Impact

- 后端：`ai_state.py`（判定层+文案）、`api_configs/crypto.py`（钥匙来源文件→库+启动加载+`_reset_for_tests`）、`main.py` lifespan（挂 `init_crypto`——位置在打指纹戳后、config.json→User 迁移前）、`ai_client.py`（`get_ai_client_for_user` 跳过解不开的配置）、`auth_local/deps.py`（抽取 `ensure_novel_model_ready` 判定核心供复用；`require_ai_access` 维持现有宽口径——其 503 无 reason，拦截交给 `require_novel_model`）、`story/router.py`（变体 dependency）、`migration/engine.py`（迁入报告死文提示）、场外 `docs/volume-plan-prompt-experiment/run.py`（直读 `.fernet_key` 的实验脚本，改从 `app_meta` 读或注明仅适用旧数据目录）。
- 前端：**仅文案透传小改**——`no_key` 枚举与文案单源在后端，但已核实 6 处组件按 `reason` 本地映射文案会盖掉 `detail.message`（`AiWriterAssistant`/`HooksSettingForm`/`WorldSettingPanel`/`SettingsView`/`StoryArcForm`/`GenreSettingForm`），死文态须透传「重新粘贴保存」；`useModelStatus` 直取 message 无需动。
- 测试：`ai_state`/`crypto` 单测、pytest conftest 增加钥匙初始化夹具；e2e 存量断言不受影响（判定层修好后错误码从 500 变 503 的端点无存量断言依赖 500）。
- 运维/用户：升级后首次启动自动完成钥匙迁移（文件在）或新钥匙生成（文件不在；旧死文配置由引导重填）。当前演示栈的死文 Key 需重填一次（本次事故已不可逆，与是否合入本 change 无关）。
