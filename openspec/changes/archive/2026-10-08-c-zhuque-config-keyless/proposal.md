# c-zhuque-config-keyless — 朱雀配置域只挂登录、使用口键自持门（撤大模型 Key 判据）

## Why

用户真机吐槽（2026-10-08）：「单独配置了朱雀，保存测试还报错大模型 ApiKey 没配置」——朱雀检测不依赖大模型才对。

定诊（代码＋隔离 TestClient 实证）：`tier-plan-four-tiers`（#679，2026-10-05）的「41 声明点挂 key」把朱雀配置域三个端点（`PUT/DELETE /api/v1/zhuque/config`、`POST /api/v1/zhuque/test`）挂上 `require_ai_access`——该门是三段判据：非会员 403 → 档位不够 403 → **「会员需已配写作大模型 Key」503**（判据链 ApiConfig active 行 → 旧 `User.api_key` → config.json 兜底）。首配因此死锁：作者（PRO/试用）只有朱雀 Key、还没配写作大模型 → 保存被 503 拦下 → Key 从未落库 →「保存并测试」「测试连接」永远失败。实测原文与用户报障逐字一致：`PUT /api/v1/zhuque/config` → 503 `AI 服务未配置 — 请先在设置中填写 API Key`（`POST /test` 同）。

该 change 的 tasks 3.2 自述「zhuque config 增删/test 3 处为新增门（现状只挂登录，**拦截范围=免费/标准**）」——意图只是档位门，判据复用越界；同批 e2e 还以「先种一条模型配置」绕行（`zhuque.spec.ts` 注释原文即「无写作 Key 时 503」，本机产品侧无绕行路径）。

**2026-10-08 用户拍板两条口径**：①**配置不区分套餐权益，操作入口区分**（回到「配置全档可配、门禁落使用口」）；②使用口（检测）同换键自持门——「任何 Key 都没有」不再被通用 503 盖过。

## What Changes

- **配置域收回登录门**：`PUT/DELETE /api/v1/zhuque/config`、`POST /api/v1/zhuque/test` 撤掉 `ai_feature("ai-detect")` 标注与门依赖——登录即可保存/更换/删除/连接测试，不分套餐档位、不要求已配写作大模型（拍板①）。
- **使用口换键自持门**：检测端点 `zhuque-check` 由 `require_ai_access` 改为 `require_tier_access`（`ai_feature("ai-detect")` 保留）——会员＋档位两级照拦（免费 403 `member_required`、标准 403 `feature_required`＋`tier_required=pro`），但**不再含写作模型 Key 判据**：未配朱雀 Key 一律返回精确的 503 `zhuque_not_configured`（拍板②）。
- **Key 判据单源＋引导口径**（2026-10-08 三条口径的收口）：门控的「已配写作大模型 Key」判据改为复用判定层 `user_has_ai_key`（可解密口径 ＋ **排除 `vendor="zhuque"`**）——此前它自建一条不看 vendor 的查询，朱雀行会被当成「已配大模型 Key」放过门、用户随后在深处吃不明错误；同时 503 文案改为指向配置口（`尚未配置写作大模型 API Key — 去「模型配置 → 写作大模型」添加`，替换旧的「AI 服务未配置 — 请先在设置中填写 API Key」）。
- **门控层拆两门**（`auth_local/deps.py`）：会员＋档位两段抽成 `_require_member_and_tier`、Key 判据抽成 `_check_writing_model_configured`；`require_ai_access` 签名与文案逐字不变（写作链路 40+ 端点零影响），新增 `require_tier_access`＝会员＋档位（键自持端点用；当前消费者＝`zhuque-check`）。
- **端点 key 标注守卫扩展**：`test_ai_feature_registry` 的「挂 key 必有门」断言认识两种门。
- **回归钉（走真实门依赖，禁整段 override）**：`test_zhuque.py` 三用例——配置域全档可配（free/standard/pro/trial 保存/测试/删除 200）、使用口档位门不松（free/standard 403、PRO 只配朱雀 200）、未配朱雀 Key 不吃通用 503（reason=`zhuque_not_configured`）；`test_ai_feature_matrix.py` 增键自持门两用例；既有 `_client` 补齐门覆盖位（旧版只绕过 `require_ai_access`）。
- **在途 spec 修正**：`tier-plan-four-tiers`（未归档）zhuque-config delta 里「Key 保存与连接测试端点 SHALL 挂 feature key ai-detect 门／非会员保存返回 403」一段与本次拍板相反，已就地改为「配置不分套餐权益、门禁落使用口」；其 zhuque-detection delta 的「通用 503 在 ai-detect 门之后判定」注亦改为「任何 Key 都没有同样返回 zhuque_not_configured」。
- **提示词面板：看/改不依赖写作大模型（口径④，2026-10-08 追加拍板）**：`prompt-panel` 五个端点（书目总览／章级列表／内容读取／内容保存／生成弹窗的提示词预览 `GET .../write/prompt`）由 `require_ai_access` 换 `require_tier_access`（`ai_feature("prompt-panel")` 保留，仍是 PRO 专属）——买了 PRO 却没配模型 Key 的作者可照常查看/编辑/存稿，「未配 Key」的引导改落在**点生成**时（正文生成端点按 Key 判据 503 提示去「模型配置 → 写作大模型」添加）。e2e `workbench-features.spec.ts` ④b 按新行为重写（原断言「弹窗即报错、生成键置灰」作废）。
- **测试基建顺带修**：`test_zhuque.py` 逐用例认领 `CONFIG_FILE`（该模块级全局按首个 import 者定型、又会被别的模块运行期改指——「只配朱雀」用例在未改动的 main 上按文件顺序就会假红，本次一并消除）；旧用例 `test_check_endpoint_free_tier_403` 的覆盖对象随门切换更新。
- **e2e 侧（带栈复跑通过）**：`zhuque.spec.ts` 删掉历史绕行的「先种一条写作模型配置」种子（该 spec 现即「零大模型配置＋朱雀 Key」的回归网，2 passed）；`workbench-features.spec.ts` ④b 按口径④重写（弹窗可看/可改 → 点生成才提示，1 passed）。均在本会话自建隔离栈（`zqgate-e2e`，跑本分支构建）实测。

明确不做：不改 `require_ai_access` 对外行为、不动前端（页签本就无门禁代码、工作台检测行的档位锁定已在）、不给免费/标准档做「检测可用」放行、不给 `prompt-panel` 之外的 LLM 端点开键自持门（守卫白名单固化，见 design 决策 7）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `zhuque-config`: 新增「配置域不分套餐权益（门禁落使用口）」要求——配置域端点只挂登录、SHALL NOT 挂档位门或写作模型 Key 判据；两门分流单源在门控层；含两条场景（任意档位可配含免费；只配朱雀、未配写作大模型可保存并测试）。
- `model-api-config`: 新增「Key 判据与引导（两个 Key 世界互不顶替）」要求——写作大模型 Key 判据单源在 `user_has_ai_key`（可解密口径＋排除朱雀行）、未配时 503 文案指向「模型配置 → 写作大模型」、朱雀配置状态不影响大模型功能判定（反向亦然）。
- `prompt-crafting`: 新增「提示词取数与编辑不依赖写作大模型配置」要求——面板五个端点＝登录＋`prompt-panel` 档位门（PRO/试用可看可改可存），未配模型 Key 不再是 503；「去配大模型」的引导落在生成动作；无档位权益仍 403。
- `tier-access`: 「端点门禁对拍守卫」补双门措辞（`require_ai_access` 或键自持端点的 `require_tier_access`）——与守卫测试实现同步。
- `zhuque-detection`: 「检测门禁与额度口径」改为**会员＋档位两级键自持门**（`require_tier_access`，SHALL NOT 用 `require_ai_access`），并明确未配朱雀 Key 一律 503 `zhuque_not_configured`、SHALL NOT 被通用 503 盖过；「会员但未配朱雀 Key 直调端点」场景按此重写。

## Impact

- 代码：`client/backend/auth_local/deps.py`（抽两函数＋新增 `require_tier_access`＋Key 判据收归 `user_has_ai_key`＋503 文案指向写作大模型）、`client/backend/zhuque/router.py`（配置域撤门＋执行域换门＋头注）。
- e2e 实测：`client/frontend/e2e/zhuque.spec.ts`（2 passed，零大模型配置）、`workbench-features.spec.ts` ④b（1 passed）。
- 测试：`client/backend/tests/test_ai_feature_http.py`（提示词面板真实 HTTP 门序钉：free/standard 403、pro/trial 过门；生成端点未配 Key 仍 503 引导含「大模型」）、`test_prompt_store_db.py`／`test_prompt_summary_batch.py`／`test_export_db_zip.py`（门覆盖随换门更新）、`client/backend/tests/test_zhuque.py`（新增 3 用例＋`local_tier` fixture＋`_client` 门覆盖补位）、`test_ai_feature_matrix.py`（键自持门 2 用例＋「只配朱雀不算已配大模型」1 用例）、`test_ai_feature_registry.py`（守卫认双门）；`client/frontend/e2e/zhuque.spec.ts` 注释同步。
- 规格：`openspec/changes/c-zhuque-config-keyless/specs/{zhuque-config,zhuque-detection}/spec.md` 新增/修改；`openspec/changes/tier-plan-four-tiers/specs/{zhuque-config,zhuque-detection}/spec.md` 就地修正（该 change 未归档，避免归档时把相反契约写回主 spec）。
- 行为影响：全档位作者都可完成朱雀 Key 配置/测试/删除（原免费/标准 403、PRO 未配模型 503）；检测端点在「未配朱雀 Key」时的 503 文案变精确；只配朱雀的用户打大模型功能时改为明确提示「去配写作大模型」（原先放过门、深处报错）；未配大模型的 503 文案由含糊的「AI 服务未配置」改为指名写作大模型；写作链路判据与文案语义优化、门禁强度不变。
- 无 UI 改动、无 schema/依赖/迁移变更（免原型与设计门禁）；纯 C端 后端修复。
