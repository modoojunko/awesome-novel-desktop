# tasks — c-api-config-vendor-defaults

## 1. 原型先行（C端）

- [x] 1.1 `docs/design-c/prototypes/model-config.html` 创建弹层补形态：新增「模型名称」一级字段＋选 DeepSeek 预填 Base URL/模型名称（只填 Key）＋「OpenAI 兼容」不预填对照＋手改字段不被切换覆盖态；验证＝原型可点过各形态且无布局漂移
  - 证据：e2e ④ DOM 断言全绿（预填值/手改保护/不预填对照逐项 `toHaveValue`）＋对照截图 `prefill-deepseek.png`（随 e2e 报告落 test-results，归档副本在本目录）
- [x] 1.2 `docs/design-c/prototypes/ADJUSTMENTS.md` 登记偏差（模型名称字段＋预填为新增形态，偏差原因＝2026-10-05 拍板反转旧「URL 不预填」）；验证＝登记条目在册
  - 证据：`ADJUSTMENTS.md`「c-api-config-vendor-defaults（2026-10-05）」条目

## 2. 供应商默认值登记表

- [x] 2.1 前端登记表（vendor×api_format → base_url＋默认模型＋备选候选）：DeepSeek 全量入册（`https://api.deepseek.com`＋默认 `deepseek-v4-pro`，备选 flash/vision-exp；DeepSeek×anthropic 无实测端点留空）；OpenAI/Anthropic/GLM/Kimi/Qwen 按官方文档核对后登记（禁编造模型 id，无据留空）；覆盖规则（空或仍为预填值才覆盖）实现为纯函数；验证＝单测：键覆盖、无据留空、手改不覆盖
  - 证据：`vendorDefaults.ts`＋`apiVendorDefaults.test.ts` 8 绿、该文件覆盖 100%；URL 依据＝Kimi 官方文档（platform.kimi.com）＋GLM 国际站文档（docs.z.ai 路径同构）＋五端点可达性实测（401/200 JSON＝真实 API 形态）＋仓内既有记载（DeepSeek/Qwen 地址见原型种子与主 spec 场景）；模型 id 仅 DeepSeek 有实测在案
- [x] 2.2 后端 `VENDOR_MODEL_CANDIDATES` 补齐实测候选并与登记表对齐（探针兜底职责不变，注释注明与前端登记表的关系）；验证＝pytest 候选路径用例绿
  - 证据：`connection.py` 候选块注释对齐；`tests/test_api_format.py` 40 绿（候选路径含 `test_openai_probe_uses_vendor_candidate_when_no_models`）

## 3. 表单预填与落库

- [x] 3.1 `ApiConfigForm` 预填逻辑＋「模型名称」输入框（一级字段，落 `models` 首项）；切供应商/切格式按覆盖规则填值；「OpenAI 兼容」不预填；编辑态不施加预填；验证＝vitest：预填、覆盖、手改保护、不预填对照四组用例
  - 证据：`apiConfigForm.test.tsx` 14 绿（预填三组＋编辑态不渲染模型字段断言）；`ApiConfigForm.tsx` 覆盖 100/100/100/100
- [x] 3.2 create 负载与落库支持 `models`（`schemas.py` `CreateApiConfigBody`＋`service.create_api_config`，归一化抽 `_normalize_models` 与更新共用）；验证＝pytest：创建后 `config.models` 含预填模型
  - 证据：`tests/test_api_key_config.py` 新 6 例绿（预填落库含归一化/无 models 空数组/超限 422/`_first_model` 全形状）
- [x] 3.3 保存门禁探针 id 优先吃表单模型名（与 `c-ai-availability-fixes` 探针 id 序列、`c-api-config-save-gate` 门禁协同）；验证＝pytest：带 `models` 创建时探针以该模型发「你好」
  - 证据：`test_connection(preferred_model=…)` 管道＋`_probe_model` 优先级（preferred→列表→候选）＋raw test `model` 透传＋`test_api_config` 用已存模型；断言＝探针请求携带该模型 id（`test_api_format.py` 2 例＋`test_api_key_config.py` 2 例绿）。注：验证语中「发『你好』」的 payload 升级属 `c-ai-availability-fixes` 组 5（判据 change，另案实施）；本任务落地的是「探针 id 优先吃表单/配置模型」管道本身

## 4. e2e

- [x] 4.1 `config-page.spec.ts` 新增：选 DeepSeek 只填 Key 保存成功（URL/模型预填断言）＋「OpenAI 兼容」路径不预填断言；验证＝e2e 通过
  - 证据：隔离栈实跑（compose project `novel-vd-e2e`，独立容器名 vd-e2e-*、端口 19021/8021/5192、数据目录 /tmp/an-vd-e2e/.docker-data；bundle 抓 `deepseek-v4-pro` 特征串自证）config-page spec **4/4 绿**——④ 新用例＋①②③ 存量；③ 两处「URL 不预填」旧断言随拍板改写为「预填随格式换/手改不覆盖」；对照截图 `prefill-deepseek.png`（归档副本在本目录）
  - 存量怪癖记录：新建弹窗常挂载不重置（create 态跨开合保留），④ 的不预填对照在全新表单段落做；该怪癖非本改引入

## 5. 回归（实际输出结论记录在 PR/归档总结）

- [x] 5.1 后端全量 pytest（用 `client/backend/.venv` 解释器）：全绿，零新增红
  - 证据：`1838 passed`（58.99s）
- [x] 5.2 `npm run design:lint` 全绿；`npm run design:check` 全绿（像素差 <0.2%，书架屏存量光栅漂移按先例除外）
  - 证据：design:lint exit 0；parity 8 场景 **6 过、2 存量红**——empty 0.291%（在册先例「书架屏光栅漂移」）与 quota 2.693%（本次 A/B 实证存量：干净 HEAD worktree 同值 0.291%/2.693%，与本改零关系，建议另案跟进）；本改零新增红
- [x] 5.3 双端类型检查：C端 `tsc --noEmit` 全绿（本 change 纯 C端，S端零改动）
  - 证据：exit 0
- [x] 5.4 前端 vitest 全量＋C端 e2e config-page 相关 spec 全绿
  - 证据：vitest **1188 绿**＋覆盖率全仓 **100/100/100/100**（perFile 契约含新入册 `vendorDefaults.ts`）；config-page e2e 4/4（隔离栈）
- [x] 5.5 共享段判定核对：不触碰 base.css 令牌/基础组件类与 pill/notice/sk/panel/f-err 家族（依据 proposal Design Impact），`scripts/design-cross.mjs` 不适用；验证＝判定依据引用在回归结论中
  - 证据：本改文件清单（vendorDefaults.ts/ApiConfigForm/ApiKeyConfigPage/useApiConfigs/schemas/service/connection/router/coverage-contract/原型+ADJUSTMENTS）无共享段
- [x] 5.6 `openspec validate c-api-config-vendor-defaults --strict` 通过
  - 证据：`Change 'c-api-config-vendor-defaults' is valid`
