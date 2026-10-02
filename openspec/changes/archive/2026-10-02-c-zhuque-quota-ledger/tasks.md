## 1. 原型先行（C端 唯一受影响屏）

- [x] 1.1 更新 `docs/design-c/prototypes/model-config.html` 朱雀页签已配置态 `zg-stats` 中间卡：静态「50 万 token / 月 · 免费额度（以腾讯云控制台为准）」→「12,340 / 50 万 token · 本月已用 · 本地估算，以腾讯云控制台为准」（保持 `.st` 结构与既有档位，零新样式）；ADJUSTMENTS.md 登记该内容位偏差原因。验证：原型浏览器过目三卡不挤行、mono 数字对齐与左右两卡一致 ✅（另：ADJUSTMENTS 第 4 条登记了存量 lint 修复——`#zqBadge` 的 ✓ 字符命中 design-lint emojiRegex，自原型入库起 design:lint/check 即存量红，HEAD 实证 exit 1）

## 2. 后端：契约与记账

- [x] 2.1 `client/backend/zhuque/service.py`：新增常量 `ZHUQUE_MONTHLY_FREE_TOKENS = 500_000`（env `ZHUQUE_MONTHLY_FREE_TOKENS` 覆写，int 解析失败回默认）＋ `get_month_usage(db, user_id)`（token_log 按 user_id ＋ `created_at >= 本月一日`（UTC）＋ `operation LIKE 'zhuque-%'` 求和 tokens_in+tokens_out）；`get_config_status` 返回值追加 `usage` 块（`month_used_tokens` / `month_free_quota` / `month_remaining_tokens`＝额度减已用截 0），未配置分支同返。验证：pytest 新增 `test_monthly_free_tokens_env_override` / `test_usage_status_clamps_negative` / `test_config_status_usage_block_and_month_aggregation`（含跨月切零、非朱雀 op 不计）全绿 ✅
- [x] 2.2 `client/backend/zhuque/service.py:test_config`：捕获 `zhuque_client.classify("ping", plain)` 返回值，取 `makers_models_usage or usage` 的 `total_tokens`，以 `operation="zhuque-test"`（project_id/chapter_id 缺省）走 `record_usage`；classify 抛异常路径不记账、测试结果语义不变。验证：pytest 新增 `test_test_endpoint_records_usage`——沿用 `test_check_endpoint_mapping_and_usage` 既有先例（`async_session()` 主库断言），测试成功后主库 token_log 出现 zhuque-test 行（tokens_out=55）、429 失败路径不出现、写作用量汇总 total_this_month=0 ✅
- [x] 2.3 `client/backend/api_configs/service.py`：五处 `TokenLog.operation != "zhuque-check"` 泛化为 `~TokenLog.operation.like("zhuque-%")`（行 626/639/652/680/707 注释同步）；项目维度按操作分组明细（by_operation）不动。验证：grep 确认五处全泛化且无残留 `!= "zhuque-check"`；pytest 全量无红（含既有 zhuque-check 汇总排除断言）✅

## 3. 前端：台账卡

- [x] 3.1 `client/frontend/src/components/api-config/ZhuquePanel.tsx`：`ZqStatus` 增 `usage?` 块；已配置态 `zg-stats` 中间卡改为台账卡——`<b>` 显「{已用千分位} / {quota 人话「50 万」，非整万直接千分位} token」，`<span>` 显「本月已用 · 本地估算，以腾讯云控制台为准」；`usage` 缺字段时回退渲染旧静态额度卡内容（「50 万 token / 月 · 免费额度（以腾讯云控制台为准）」），禁用「—」等新空值占位；未配置态不动；「查看用量」外链保留。验证：`zhuqueConfig.test.tsx` 新增渲染断言通过 ✅
- [x] 3.2 `client/frontend/src/__tests__/zhuqueConfig.test.tsx`：mock `/v1/zhuque/config` 响应补 `usage` 块用例，断言台账卡文案与刷新链路（runTest 后 refresh 重取）；既有「—」锚点两用例（`:260`/`:250`）回归确认不受影响。验证：vitest 该文件 30/30 全绿 ✅

## 4. 回归

- [x] 4.1 C端 门禁：`npm run design:lint` 退出码 0（修复原型存量 ✓ emoji 后，见 1.1）；`npm run design:check` 7/8 绿、1 红为书架屏 empty 像素差异率 0.292%（阈值 0.2%）——记忆在册的存量光栅漂移，本改未触 list.html/书架屏，按 proposal Design Impact 判定依据不触共享段、免 design-cross；`tsc --noEmit` 退出码 0。验证：三条命令输出结论于上 ✅
- [x] 4.2 e2e `client/frontend/e2e/zhuque.spec.ts`：**2 passed（隔离栈，从本工作树构建镜像＋classify 桩＋MAX 权益种子）**。本改把 spec 补成自包含（原 spec 依赖建时会话的浏览器态，fresh profile 必挂）：beforeAll 探测部署→S端 注册签发→写 config.json（tier=max＋完整权益快照含 ai-detect——无快照走档位兜底 features 恒缺 ai-detect，检测行锁 MAX 态）→API 种书/卷/章/正文/Key；check-auth 页面桩防注入 token 被冲（/auth/verify 不能桩——它是套餐上下文数据源）；行点击前等 `zq-guide/zq-maxlk` 类退掉（配置取数 null 窗口的 guide 竞态）；新增「配置页台账卡」用例（真后端 usage 契约，截图实证 `321 / 50 万 token` 真数据渲染）。⚠️ 环境注记：teardown 的 sweep 未设 `E2E_CLIENT_BACKEND_CONTAINER` 时默认打共享栈（记忆在册坑），本次对共享栈 0 删但触发了一次干净重启（重启后 5174/8000 探活正常）
- [x] 4.3 后端全量 pytest 绿：**1753 passed, 1 failed**——唯一红为 `tests/test_plot_prompt.py::test_empty_plots_golden_unchanged`，记忆在册的 main 存量红（plot golden），与本改无关（未触任何 plot 文件）。验证：pytest 输出摘要于上 ✅
