# c-llm-call-log：大模型出网调用独立日志 llm.log

## Why

2026-10-08 用户反馈「Gemini 模型页面测试 401」定诊实锤：连接探针（测试连接／Key 失焦拉模型清单，`api_configs/connection.py`）与朱雀检测客户端（`zhuque/client.py`）**完全零日志**——后端访问日志只有本地请求行（test-connection 200），探测目标主机与上游状态码（401）无处可考，远程定诊全靠推断。生成类调用已有 `ai_client` 留痕行，但混在 app.log 且行内无供应商（vendor）身份。需要：零日志直连点补上留痕，并把大模型出网调用独立落 `llm.log` 专项档（与 app.log 双写），AI 问题求诊直接看专项档。

## What Changes

- `logging_setup.py`：同参第二个 `TimedRotatingFileHandler` → `logs/llm.log`（midnight、保留 5 天、UTF-8、delay，独立同型限速实例），挂载到具名 logger `ai_client`／`llm_probe`／`zhuque.client`；三者保持 propagate=True——行**双写** app.log（求诊主档不缺行）＋ llm.log（专项档）。幂等与 LOG_OFF 关闭语义与 app.log 单源继承。
- `api_configs/connection.py`（本次定诊核心缺口）：探针每出网请求一行——`models_list`（清单 GET）与 `generation_probe`（「你好」最小生成探针），行含 vendor／api_format／host／path（**丢弃 query**）／上游状态码／耗时／结果分类；失败升 WARNING；httpx 异常路径同样落行（status=0）。`_probe_generation` 判定级联逐字抽成 `_probe_verdict`（纯判定单出口，行为不变）。
- `zhuque/client.py`：classify 每次调用恰一行（正文**只记字符数** chars）；顺手加固：200 但体非 JSON 从裸抛 JSONDecodeError（→500）改受控抛 `ZhuqueUpstreamError`（复用既有「无法解析」文案，调用方落 502）。
- `ai_client.py`：`AIClient` 构造器加 `vendor=""` 参数，三处 ApiConfig 工厂（for_user 两分支＋for_novel）传入（vendor 本来在手但被丢弃）；留痕行追加 `vendor=%s`（`__new__` 直装实例 getattr 兜底 `-`）。
- 打包文案：`verify_pack_hardening.ps1`／`install_portable.bat` 的「回报附日志」清单补 `logs\llm.log`。

非目标：启动失败页求诊候选与 `installer.iss` 不动（启动诊断与 llm 无关；logs/ 卸载清理现状口径不变）；`s_api_call_error` 空 error 补异常类型（S 端链路）另立；`refresh-models` 12ms 秒回异常另查。

## Capabilities

### Modified Capabilities

- `backend-logging`: ADD 新 Requirement「大模型出网调用独立落 llm.log」——三类出网调用（生成调用／连接探针／朱雀检测）每调用恰一行；行含动作类型／供应商／主机＋路径（不含 query）／模型／上游状态码／耗时／结果分类，失败升告警级带错误摘要截断；专项档与按天日志同轮转同保留参数、独立体积护栏、幂等单源；隐私红线继承（Key／正文全文／query 永不落）；app.log 双写保留。

## Impact

- **代码**：`client/backend/logging_setup.py`、`api_configs/connection.py`、`zhuque/client.py`、`ai_client.py`；打包文案两件。零前端、零壳层逻辑（壳层预挂同一 `setup_logging()` 自动获得 llm.log）。
- **测试**：`tests/test_logging_setup.py`（专项档判据五条）、新 `tests/test_llm_probe_logging.py`（Gemini 401 判据等十二条）、`tests/test_ai_client_logging.py`（vendor 断言）、`tests/conftest.py` 夹具扩展（llm handler teardown 摘除）。
- **行为变化**：`zhuque` 200 非 JSON 体从 500 变受控 502（行为修复）；ai_client 留痕行格式追加字段（存量断言包含式，不破）。
- **风险**：llm handler 挂具名 logger，测试清理块漏摘会跨用例泄漏（conftest 与 `test_missing_dirs_created` 同批修，判例入 design）。
