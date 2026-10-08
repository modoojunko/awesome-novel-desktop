# c-llm-call-log 任务清单

## 1. 基建

- [x] 1.1 `logging_setup.py`：llm.log 专项 handler（同参 TRFH：midnight/backupCount=5/UTF-8/delay；`_ainovel_llm` 标记；独立 FoldRepeatFilter 实例）挂具名 logger `ai_client`/`llm_probe`/`zhuque.client`，propagate 保持双写 app.log；幂等与 LOG_OFF 单源继承。验证：2.1。
- [x] 1.2 `api_configs/connection.py`：探针留痕——`_log_probe`（host/path 取 urlparse 丢 query；status 机械映射 result；成功 INFO 失败 WARNING）＋三埋点（models_list GET 后、`_probe_generation` 出口、httpx 异常路径 status=0）；`_probe_generation` 判定级联逐字抽 `_probe_verdict`（行为不变）；新增 vendor/api_format 参数由调用点传入。验证：2.2。
- [x] 1.3 `zhuque/client.py`：classify 恰一行留痕（chars 记字符数不记正文；判定级联抽 `_parse_classify`；200 非 JSON 体收进受控 ZhuqueUpstreamError，原裸抛 JSONDecodeError）。验证：2.2。
- [x] 1.4 `ai_client.py`：构造器 `vendor=""`；三处 ApiConfig 工厂传入；`_log_call` 行追加 `vendor=%s`（getattr 兜底 `-`）。验证：2.3。

## 2. 测试

- [x] 2.1 `test_logging_setup.py`：llm handler 挂载与轮转参数；幂等不重复挂；llm 行双写 app.log＋llm.log；非 llm logger 不进 llm.log；LOG_OFF 不挂；conftest `daily_file_log` 夹具 teardown 摘 llm handler；`test_missing_dirs_created` finally 补摘（直调 setup 的泄漏判例，design D8）。验证：`pytest tests/test_logging_setup.py -q` 全绿。
- [x] 2.2 新 `test_llm_probe_logging.py`：fetch_models 401 行（Gemini 401 案判据：host＋path＋status=401＋result=auth_error＋WARNING＋Key 不落）；test_connection 401；超时 status=0 result=timeout；全通双行（models_list＋generation_probe 均 INFO）；空回复 result=unknown WARNING；anthropic 404 降级两行（not_found＋auth_error）；URL query 永不落；朱雀四条（ok 行 chars-only／401 auth_error／超时／非 JSON 200 受控 bad_response）。验证：`pytest tests/test_llm_probe_logging.py -q` 全绿。
- [x] 2.3 `test_ai_client_logging.py`：vendor 断言（有 vendor 记实名；`__new__` 裸实例记 `-` 不炸）；存量 app.log 双断言守护双写。验证：`pytest tests/test_ai_client_logging.py -q` 全绿。

## 3. 打包文案

- [x] 3.1 `verify_pack_hardening.ps1` 回报口径、`install_portable.bat` 提示文案补 `logs\llm.log`（AI 问题求诊附专项档）。验证：grep 两文件含 llm.log。

## 4. 回归与收尾

- [x] 4.1 后端全量回归：`cd client/backend && .venv/bin/python -m pytest -q` 零新增红（存量红逐条归因）。产出：结果摘要贴任务下。
  - 4.1 实测（worktree @c-llm-call-log，主检出 .venv 解释器，最终态复跑）：**2055 passed / 1 skipped / 0 failed**（约 72s）。
- [x] 4.2 ruff 门禁：ruff==0.16.3 复核改动文件零新增告警。产出：结论贴任务下。
  - 4.2 实测：改动 8 文件 `ruff check` All checks passed（初跑 3 条：conftest I001 import 排序＋测试桩 RUF012 ×2，已按 test_api_format 的 ClassVar 惯例同款修复）。
- [x] 4.3 `openspec validate c-llm-call-log --strict` 通过。产出：输出贴任务下。
  - 4.3 实测：`Change 'c-llm-call-log' is valid`。
- [ ] 4.4 真机冒烟（随下次发版）：真机点一次「测试连接」（含一次失败配置），`logs/llm.log` 出现对应探针行且 app.log 双写可见；朱雀检测一次留痕 chars 行。产出：现场记录（可后补）。

## 5. 评审修复（PR #736 review 三条，design D9）

- [x] 5.1 P2：`_probe_target`／`_log_classify` 对畸形 URL（未闭合 `[`——httpx 0.28.1 接受并真实连接，urlparse 抛 ValueError）兜底 `("-", "-")`——探针不再从 except 处理器二次抛 500 化。钉子 `test_malformed_base_url_never_breaks_probe`。
- [x] 5.2 P3：ollama 探针行 `format=-`（原生 /api/tags 非按格式探测）；`_log_probe` 内集中处理。钉子 `test_ollama_probe_logs_native_format`。
- [x] 5.3 P3：删除死常量 `_LLM_MARK`（handler 标记字面量唯一设置点在 logging_setup，测试按字面量钉）。
- [x] 5.4 二轮评审 P3：200 体判废提前到留痕之前（`_non_api_response` 一次计算两处复用），「网站首页 200 HTML」场景留痕行与函数裁定一致记 `endpoint_mismatch`（WARNING）——不误导定诊。钉子 `test_html_200_logs_endpoint_mismatch`（test_connection／fetch_models 双口径）。
