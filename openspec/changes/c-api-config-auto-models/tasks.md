# Tasks — c-api-config-auto-models

## 1. 后端

- [x] 1.1 `connection.py`：新增 `fetch_models()` 轻探针（复用 `_build_probe`；GET-only；anthropic 404 → 空清单＋candidates＋note；Key 空非 ollama → auth_error；200 非 API JSON → endpoint_mismatch）
- [x] 1.2 `schemas.py`：新增 `FetchModelsBody`（vendor_id/base_url/api_key/api_format）
- [x] 1.3 `router.py`：新增 `POST /api-configs/fetch-models`（登录鉴权，透传 `fetch_models` 结果）
- [x] 1.4 `service.py`：`_normalize_models` 加 `truncate` 参数（超 100 截断）；`test_api_config` 自动落库走归一化
- [x] 1.5 `connection.py`：`VENDOR_MODEL_CANDIDATES.deepseek` → `["deepseek-flash", "deepseek-v4-pro"]`（官方文档 2026-10-07 实勘）
- [x] 1.6 pytest：fetch_models 成功/404 降级/网页判废/Key 空/ollama tags；端点契约；落库归一化截断；候选表断言更新

## 2. 前端

- [x] 2.1 `types/api-config.ts`：`FetchModelsResult` 类型（含 candidates/note）
- [x] 2.2 `useApiConfigs.ts`：`fetchRawModels(body)` 调新端点
- [x] 2.3 `ApiConfigForm.tsx`：模型字段改选择器（组合框＋`.mp-*` 搜索弹层＋候选 chips；键盘导航）
- [x] 2.4 自动拉取接线：Key 失焦非空触发；Ollama 免 Key 触发；vendor/URL/格式变更重拉；在途去重（序号丢弃过期响应）；失败 warn＋「重新拉取」
- [x] 2.5 默认选中规则（2026-10-07 二次拍板定案）：**清单首项**（「默认选第一个就好，不评估价值」——登记默认不优先，预填值只作初值）；手选不覆盖；`handleTest` 结果同步刷新清单
- [x] 2.6 vitest：apiConfigForm（触发/默认选中/弹层搜索选择/手填兜底/测试刷新/失败重试）、apiKeyConfigPage（fetch-models 接线＋POST body）、apiVendorDefaults 对齐
- [x] 2.7 字段顺序＝Base URL → API Key → 模型（2026-10-07 用户拍板：模型垫底，Key 失焦拉到的清单喂给紧随其下的选择器）；原型同批对调

## 3. 原型与规格

- [x] 3.1 `docs/design-c/prototypes/model-config.html`：添加弹窗补模型选择器形态（组合框＋弹层），design:check 过线
- [x] 3.2 openspec validate --strict 过线

## 4. 端到端与收尾

- [x] 4.1 e2e `config-page.spec.ts` ④ 改造：DeepSeek 流程补 Key 失焦自动拉取（stub 清单）＋选择器默认选中＋POST body 断言保持
- [x] 4.2 隔离栈跑 config-page 全 spec＋design parity；全量 vitest／pytest 绿
- [x] 4.3 PR #711（含变更说明与本 change 归档待办）

## 5. 评审整改（2026-10-07 三方评审：前端 Request changes／后端方向批准带 P1／产品批准带 P1）

- [x] 5.1 【P0·前端】applyAutoSelect 守卫读闭包过期 state → 模型值 ref 镜像（setModel 单一写口）；用例「在途拉取期间手填不被迟到响应覆盖」
- [x] 5.2 【P1·前端】Esc 只收弹层（stopPropagation，防 Modal window-Esc 关整窗）＋用例钉 onCancel 不被调
- [x] 5.3 【P1·前端】弹层 portal 到 body＋fixed 锚定（Modal .mcard overflow 裁剪卡内浮层，长清单必现）；滚动/resize 重锚＋近视口底缘向上翻转
- [x] 5.4 【P1·前端】弹层 mousedown 整体 preventDefault（滚动条拖点不误关）；外点关闭改 document pointerdown（点非聚焦区域旧 blur 方案关不掉）
- [x] 5.5 【P1·前端】invalidateModelList 作废在途请求（序号＋fetching 复位）；用例「清 Key 切供应商旧响应不落地」
- [x] 5.6 【P1·后端】`test_api_config` 响应体与落库同一份归一化清单（不再 150/100 两口径）
- [x] 5.7 【P1·后端】保头：配置默认模型（models 首项）在清单内时置落库结果首位——不限是否触发截断（首项＝已选模型语义，下次探针优先用）；用例「my-pick 排 121 位仍保留」＋「未超限重测同样保头」（review-agent 终审 P3 定案：放宽规格而非收紧代码）
- [x] 5.8 【P1·后端+产品】fetch_models 404 特判限 anthropic 格式（openai/ollama 404＝异常响应提示核对，不误诊「无清单端点」）；用例
- [x] 5.9 【P1·产品/后端】对话探针失败信封携带已提取清单（手填错 id 自恢复闭环）；用例
- [x] 5.10 【P2·前端】空态文案按 fetchErr/modelNote 分岔（不再指向不存在的「重新拉取」）；IME 组合期 Enter 放行；Ollama placeholder 专文案；handleTest 同步清 fetchErr/candidates＋写同参指纹；aria-activedescendant＋option id＋tabIndex=-1；点输入框重开弹层
- [x] 5.11 【P2·后端】ollama 自定义端口的 base 一律照打（旧实现见 "localhost" 硬替 11434）；fetch 429/5xx 用例
- [x] 5.12 文档与规格对齐实况：design.md D5 改组合框实况＋风险栏闭环；spec delta 补 openai-404／在途作废／手填常驻／探针失败带清单／截断保头／响应体对齐

## 6. 跟进挂号（评审产出，另立任务不在本 PR）

- [ ] 6.1 死模型 id 清偿：`ai_client.py`/`models/user.py`/`auth_local/service.py` 五处 `deepseek-v4-flash` legacy 兜底（全新安装默认落到死 id）
- [ ] 6.2 raw 探针端点（fetch-models/test-connection）按用户限速（失焦自动触发调用量上台阶）
- [ ] 6.3 截断 keep-set 扩展：已绑定该配置的 `Novel.ai_model` 一并入保留集（需产品拍板语义）
- [ ] 6.4 错误映射抽公共 helper（connection.py 三份近似拷贝）
- [ ] 6.5 书内 ModelSettingForm 长清单搜索（本 change 非目标）
- [ ] 6.6 组合框「搜索残词被当 id 提交」与「跨供应商残留手选 id」的轻提示（产品口径待拍板）
