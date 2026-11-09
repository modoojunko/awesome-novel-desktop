# c-zhuque-ipv6-fallback Tasks

## 1. 后端回退

- [x] 1.1 `zhuque/client.py`：`_CONNECT_PHASE_ERRORS`（ConnectTimeout/ConnectError）
      触发面＋classify 内联 IPv4 回退（`AsyncHTTPTransport(local_address="0.0.0.0")`
      重试一次）；模块 docstring 补 2026-11-09 真机案
- [x] 1.2 `_log_classify` 增 `fallback` 可选参数：非空行尾 `fallback=ipv4`，未回退
      行形状不变

## 2. 测试

- [x] 2.1 `test_llm_probe_logging.py`：fake client 记录构造 kwargs（inits）
- [x] 2.2 三场景：connect 超时回退接通（2 次构造＋transport 断言＋fallback=ipv4）；
      回退再败同语义（status=0 timeout 映射＋恰一行）；读超时不回退（恰一次请求）

## 3. 验收

- [x] 3.1 ruff（改动文件）绿
- [x] 3.2 `test_llm_probe_logging.py`＋`test_zhuque.py` 全绿
- [x] 3.3 全量后端 `pytest tests/ -q -m "not perf"` 绿
- [x] 3.4 真机级验证：本机即 v6 黑洞环境，worktree 代码直调真实网关——首连挂
      10s 后 v4 接通、401（假 Key 预期）正常映射；余＝装新包后章节检测/连接
      测试实测（llm.log 应现 `fallback=ipv4` 的 ok 行），随发版走查

## 4. 归档（随实现 PR）

- [x] 4.1 delta sync 进 `openspec/specs/zhuque-detection/spec.md`＋change 移档
      archive，同 PR 带上
