# design — c-api-config-save-gate

## Context

动机见 proposal.md（Why 两层失守）。现状约束：

- 连接探测实现与判据单源在 `client/backend/api_configs/connection.py` 的 `test_connection`（「测试连接」端点 `POST /api-configs/test-connection`、`POST /api-configs/{id}/test` 同用）；判据收紧在 `c-ai-availability-fixes`，口径＝200 必须 API JSON＋「你好」禁思考最小生成收到格式正确回复才算通（2026-10-05 拍板，取代「400/422 不拦」）。
- 创建链路现状：前端 `ApiKeyConfigPage.handleFormSubmit` 先 `addConfig`（`POST /api-configs` 直落库）→ 再 `testConfig(id)`（non-blocking，失败只改 toast 尾巴）→ 关弹窗。后端 `create_config`/`update_config` 落库零探测。探测结果的**唯一**持久化点是 `test_api_config`（写 `last_test_status/models/last_tested_at`），前端编辑提交恒发全量负载（含未改的 `base_url`/`api_format`）。
- 编辑态「留空则保留当前密钥」：前端省略 `api_key` 字段，后端 `body.api_key` 空串=未提供（两侧各一道，2026-09-18 覆盖率专项）。
- 产品无真实存量用户（2026-09-18 拍板）；但 v0.27 内测用户会原地升级进新行为。

## Goals / Non-Goals

**Goals:**

- 坏 URL 在保存动作当场被拦、原位暴露；落库数据保证「探测通过」（限保存入口）。
- 探测判据与「测试连接」严格同一份；探测结果的持久化与卡片状态链路自洽（含刷新后）。
- 一次保存只打一次上游探测；纯改名等非连接编辑不触网。

**Non-Goals:**

- 不改探测判据本身（在 `c-ai-availability-fixes`）。
- 不做 URL 自动改写/预填（由 `c-api-config-vendor-defaults` 承接）。
- 不对存量配置批量重验；不给导入/迁移/朱雀路径加门禁。
- 不给「探测失败仍要保存」的逃生口（见 Decisions 2）。
- 不改写探测文案的状态码裸露问题（沿用现状，另案处理）。

## Decisions

1. **门禁落点＝后端 service 层 create/update（单源）**，不在前端先测后存。落库前调 `test_connection`（编辑 Key 留空时用已存密钥），判败抛结构化 422，**detail 形状＝`{code: "probe_failed", status: <探测status>, message: <探测原文案>}`**——`message` 键刻意对齐前端 `lib/api.ts` 既有提取路径（`detail` 为对象时取 `detail.message`），零解析层改动即让探测文案直达用户；判别码走既有 `detail.code` 透传。备选「前端先测后存」（可绕过、双往返、响应无从带结果）否；备选「detail 用 `error` 键＋改 api.ts」（多动一层、多一颗钉）否。
2. **判败即拦全集，无逃生口**：按「非 ok 即拦」实现（含 `unknown`——models 端点 400/402 等异常响应形态，勿按五项白名单枚举）。备选「只拦 endpoint_mismatch」留下同族洞；弱网/Ollama 未启动存不进是接受的代价（内测反馈再议逃生口）。
3. **门禁触发＝创建恒测；编辑按「值变化」测**：后端比对 `base_url`/`api_format` 与已存值、`api_key` 以非空为变更，任一不同才探测。前端编辑恒发全量负载也安全，**不需要前端 diff 改造**。备选「按负载字段有无触发」——真实 UI 编辑恒携带全量字段，纯改名也会被探测误伤（弱网连改名都拦），否。
4. **判过即持久化＋响应嵌套 `probe`**：探测结果按 `test_api_config` 同款写库（`last_test_status/last_test_error/last_tested_at/models`），响应附 `probe: {ok, status, models, note}`（嵌套防与配置对象顶层 `status`〔生命周期〕/`models` 撞名）；前端取 `probe` 置卡片，`refreshStatus` 回读库列不回退。删除创建后二次 `testConfig`（其探测、写库、置状态三个职责分别由门禁探测、判过持久化、响应 `probe` 承接）。
5. **错误分流与清除**：`probe_failed`→弹窗 `tresult bad` 位（与「测试连接」失败同形）；409 撞名、保存请求自身网络失败、503→`.ferr`。用户改动任一连接字段即清过期错误/测试结果（修正窗口不展示指向旧值的结论）。成功 toast 固定「已添加「X」· 连接正常」；`note`（无模型列表解释）只进卡片/表单结果位，不进 toast（§13 补救句须带点击出口，toast 单行装不下）。
6. **保存按钮 busy 态**：「保存中…」＋spinner（沿 ZhuquePanel 范式），`Modal locked` 已有；探测最坏多跳（models＋生成＋thinking 去参重试）叠加单跳 10s 超时，全程须有进行中反馈。

## Risks / Trade-offs

- [保存动作变长（最坏 3~4 跳×10s，约 30s 量级）] → 保存中 busy＋Modal locked；失败即时可改可重试；无总预算上限（接受）。
- [弱网/离线/Ollama 未启动时无法保存配置] → 接受（Decision 2）；错误文案沿用探测文案，用户可稍后重试；内测若反馈集中再议逃生口。
- [存量测试集体触网/翻红] → conftest autouse 统一桩，**打桩点钉死 `api_configs.service._test_connection`**（service 按值导入别名，patch `api_configs.connection.test_connection` 不生效——已知陷阱）；`test_api_key_config.py` 等存量 CRUD 用例免触网；e2e 成功臂用本地假上游桩（`page.route` 拦不到后端出网 httpx，参照 ai-assist `STUB_BASE` 桩服务器先例）。
- [存量 e2e ②③（「127.0.0.1:1 网络错误照常入库」）与门禁语义直接相反，门禁后必红] → tasks 4.2 列明改造（造数换桩上游/后端种子，Undo 链路另找铺垫）。
- [探针模型 id 是猜的（创建时未选模型），严格判据下 id 被拒会连保存一起拦] → id 取用顺序含配置已选模型；判败错误点名所试 id 与请求地址，可行动；`c-api-config-vendor-defaults` 预填模型名＋候选册补齐大幅收窄该面；内测若现「地址对但保存被拦」个案按此归因。
- [与 `c-ai-availability-fixes` 的顺序依赖] → **硬前置**：其组 5（「你好」探针）实现完成是本 change 探测门禁的开工条件；归档 sync 判据 delta 先行或同批，落完 `openspec validate --strict` 双 change 同验。不再用「以在途工作区版本为准」的软表述（会把旧判据带进门禁）。
- [探测文案含裸状态码（如「认证失败 (HTTP 401)」）与主 spec「不裸露状态码」存在存量张力] → 本 change 不改写文案（同一文案优先）；裸码问题沿用现状、另案处理。

## Migration Plan

无数据迁移。API 契约变化（create/update 新增探测失败 422 分支、响应新增嵌套 `probe`、判过写测试结果字段）按 BREAKING 记录；无真实存量用户不做兼容回落，v0.27 内测库原地升级直接进新行为（弱网/弱上游下保存被拦属预期变化）。回滚＝还原提交，无状态残留（写库的是既有测试结果字段）。

## Open Questions

（无）
