# c-api-200html-probe 任务清单

## 1. 实现

- [x] 1.1 `client/backend/api_configs/connection.py` `test_connection` 的 `not_api`
  分支改为「先降级探对话接口、探不通才判失败」：与 404 降级同路径（新增 helper
  `_fallback_probe` 承载共用探针发送），探通按「无清单端点」口径返回
  `{ok, models: [], candidates, note}`；探不通返回体判废原文案；无 id 的 openai
  不降级。404 分支改用同一 helper（行为守恒）。
  验证：`tests/test_api_format.py` 全绿（64 条，含新增 3 条）。
- [x] 1.2 `fetch_models` 零生成调用语义保持不变（`FetchModelsBody` 无 model 字段，
  轻探针无从降级；与 openai 404 不降级的既有口径同源）——体判废仍按失败报原文案。
  验证：`TestFetchModels` 既有 12 条全绿（含 `test_html_page_fails`）。
- [x] 1.3 模块 docstring 补「models 端点回 200 网页体同样降级」口径。验证：ruff 零告警。

## 2. 测试

- [x] 2.1 `tests/test_api_format.py` 新增：`test_models_200_html_degrades_to_chat_probe`
  （200-HTML + 对话正常 → ok、空清单＋openai 版说明、与生成同址、探针 id 用已选模型）；
  `test_models_200_html_degrade_failure_keeps_page_copy`（降级探针 404 → 仍判失败且
  保留「不是 API 数据…看起来像网页」原文案）；
  `test_models_200_error_envelope_degrades_to_chat_probe`（软错误信封同分支降级放行）。
  验证：三条全绿。
- [x] 2.2 `test_models_200_html_page_fails`（无 id 不降级）加固：断言零 POST
  （不发生成探针）。验证：绿。
- [x] 2.3 `tests/test_llm_probe_logging.py` 留痕口径核对：无 id 场景仍体判废短路
  （models_list 行 result=endpoint_mismatch、无 generation_probe 行）；
  有 id 降级场景 = not_found/endpoint_mismatch 行＋probe 行两行（与 404 降级同构）。
  验证：14 条全绿（既有断言无需改动）。

## 3. 回归

- [x] 3.1 `cd client/backend && pytest tests/ -q` 全量绿（worktree、共享 venv 解释器口径）。
  验证：汇总行贴 PR。
- [x] 3.2 `ruff check --extend-select F811,F821,F841 .`（0.16.3 钉版）零告警。
  验证：命令输出贴 PR。
- [x] 3.3 前端门禁不适用判定：零 UI、零共享段、零前端文件（proposal 无 Design Impact
  段即判定依据）。验证：`git diff --stat` 无 client/frontend 命中。

## 4. 用户复测口径（发版后，随发版链带走）

- [ ] 4.1 ccswitch 类网关配置：填 Key + 手填模型名 → 「测试连接」报「连接正常」
  （型号清单说明为「该端点不提供模型列表」），生成链路可用。
- [ ] 4.2 对照未修复行为：真网页站（如厂商控制台页）测试连接仍报
  「该地址返回的不是 API 数据…请检查 Base URL」。
