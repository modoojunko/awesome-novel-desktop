# c-llm-call-log 设计

## D1 双写而非迁移（app.log 求诊主档不动）

llm.log 是**附加专项档**，不是把 AI 留痕行从 app.log 挪走。三个理由：①`test_ai_client_logging.py` 已断言留痕行落 app.log（`daily_file_log` 夹具双断言），迁移即翻存量；②backend-logging R2「求诊主档」口径＝app.log 一份看全，AI 行缺席会让求诊材料缺线索；③探针行体量小（每次测试连接 ≤3 行），双写成本可忽略。挂载实现＝llm handler 挂**具名 logger**（`ai_client`/`llm_probe`/`zhuque.client`），不设 propagate=False——record 先经具名 logger 的 llm handler 落 llm.log，再沿 root 落 app.log，两条管道互不知晓。

## D2 幂等与关闭语义单源继承

`setup_logging()` 的幂等入口（扫 `_ainovel_daily` 标记早退）不变——llm handler 与 app.log handler 在同一次初始化内创建，重入既不会重复挂 app.log 也不会重复挂 llm.log。`AINOVEL_LOG_OFF=1` 早退分支同样天然覆盖（测试零副作用依赖此语义）。llm handler 打独立 `_ainovel_llm` 标记（供测试定位与将来摘除），并挂**独立** `FoldRepeatFilter()` 实例——filter 状态挂 handler 不共享，同一条 record 在两个 handler 各自独立判定，互不干扰。

## D3 探针行记请求级事实，不掺业务判定

行分类（`result=`）按上游状态码机械映射（`_status_result`：2xx→ok、401/403→auth_error、404→not_found、429→rate_limited、≥500→server_error）。**特判不进日志**：anthropic 格式 models 404 在返回体里是「无清单端点」合法形态（降级说明给前端），日志仍如实记 not_found——请求级事实（404 就是 404）与业务裁定（ok＋note）分层，定诊时以事实为准。定诊本命字段＝上游状态码：Gemini 401 案里本地恒 200、上游 401，只有把上游状态码打进行里才能远程一眼定诊。

## D4 探针行的隐私边界

- **query 永不落**：`_probe_target` 用 urlparse 只取 netloc＋path——部分网关支持 `?key=` 传钥，整 URL 与请求头同按机密处理（ai_client `_host_of` 同款口径）。
- **headers 永不落**：Key 只在请求头（openai Bearer／anthropic x-api-key）。
- **生成探针请求体是固定「你好」**（无隐私），失败行 error 截 120 字符——上游错误文案（如 Google 的 "API key not valid"）是定诊关键，可落。

## D5 `_probe_generation` 重构形态

判定级联逐字抽成 `_probe_verdict(resp, url, model, reply_fn)`（纯判定、无副作用），`_probe_generation` 只剩计时＋出网＋单出口落行＋返回——行为与改前逐字节等价（含 thinking 去参重试：两次 POST 合并为一行，耗时含重试）。新增 `vendor`/`api_format` 两个可选参数由 `test_connection` 调用点传入，模块内 4 个调用点全量同批，无外部调用方。

## D6 zhuque 非 JSON 200 加固（顺手、有据）

原实现 `data = resp.json()` 对非 JSON 200 体裸抛 JSONDecodeError → 上层 500；而同函数对「JSON 但非 dict/非 success」已经抛 `ZhuqueUpstreamError(status, "朱雀返回了无法解析的结果")`。加固＝把 resp.json() 收进 try，ValueError 时走同一条受控上抛（文案复用既有句），调用方 service 层映射 502。动机：保证「classify 每次调用恰一行留痕」的边界闭合（裸抛路径无日志行）。`tests/test_zhuque.py` 全程 stub classify，无用例钉旧行为。

## D7 vendor 身份顺进留痕行

`ApiConfig.vendor` 在工厂层（`get_ai_client_for_user` 两分支＋`get_ai_client_for_novel`）本来在手但被丢弃——构造器加 `vendor: str = ""`（向后兼容默认），`_log_call` 行追加 `vendor=%s`。`AIClient.__new__` 直装的测试实例（含存量 `_make_openai_client`）无 `_vendor` 属性，`getattr(self, "_vendor", "") or "-"` 兜底记 `-`，不炸。字段放 model 之后 host 之前（身份组聚拢）；FoldRepeatFilter 的 key 含 args，新字段不改变折叠语义。

## D8 测试泄漏护栏（实施中实际踩到）

llm handler 挂具名 logger 而**不在 root 上**——凡直调 `setup_logging()` 的测试（非 `daily_file_log` 夹具路径），finally 只清 root/uvicorn 就会漏摘，handler 指向已删 tmp 目录并污染后续用例（首跑实锤：`test_missing_dirs_created` 泄漏致 3 个后继用例假红）。修法两处同批：conftest 夹具 teardown 对 `_LLM_LOGGERS` 逐个摘新增 handler；`test_missing_dirs_created` finally 同款补摘。判例：**给具名 logger 加 handler 时，所有直调 setup 的测试清理块都要同批点名该 logger**。

## D9 评审修复（PR #736 review 三条）

- **urlparse 比 httpx 严（P2）**：`http://[`（未闭合 IPv6）httpx 0.28.1 接受并真实发起连接，urlparse 却抛 ValueError——留痕调用点多在 except 处理器里，二次抛会把既有友好报错（network_error dict）500 化（已端到端复现）。`_probe_target`／`_log_classify` 均兜底 `("-", "-")`：留痕行 host/path 可缺，「出网即有行」与「报错不劣化」两条不变量保住。钉子 `test_malformed_base_url_never_breaks_probe`。
- **ollama format 误记（P3）**：探测走原生 `/api/tags`（`_build_probe` 特例），与 openai 格式无关——`_log_probe` 内对 ollama 记 `format=-`，不误记入参缺省 openai。钉子 `test_ollama_probe_logs_native_format`。
- **`_LLM_MARK` 死常量（P3）**：删除——handler 标记字面量只此一处设置、测试按字面量 getattr 钉住，无引用常量反成误导（对照：app.log 侧 `_MARK` 真被幂等扫描引用）。
