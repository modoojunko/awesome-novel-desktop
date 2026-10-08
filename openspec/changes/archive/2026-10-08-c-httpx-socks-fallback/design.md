# c-httpx-socks-fallback 设计

## Context

- 现状：`client/backend/requirements.txt` 仅 `httpx>=0.27.0`。httpx 的
  `trust_env=True` 会读 Windows/macOS 系统代理与环境变量；SOCKS 形态代理触发
  `import socksio`，产物未带该包 → `AsyncClient` 构造期 `ImportError`。
- 既有错误处理只接 `httpx.TimeoutException`/`httpx.RequestError`（调用期），
  构造期异常直接穿透成端点 500。实锤现场：app.log 2026-10-08，
  `/api/auth/check-auth`、`/api/update-check` 连续 500。
- 出网构造点共 9 处（grep 实锤）：`AsyncClient`×7——`auth_local/service.py`
  `call_server_api`、`auth_local/router.py` `devices/current`×2、
  `update_check.py`、`zhuque/client.py`、`api_configs/connection.py`×2；
  **同步 `httpx.Client`×2**——`prompt_pack/sync.py`（probe_latest/sync_once）。
  同步链路若无兜底：`/api/pack/probe` 经 `asyncio.to_thread` 无接异常 → 500；
  `sync_once` 构造失败会被 trigger_sync 线程兜住但误记 `failed reason=unexpected`。
  另 openai/anthropic SDK 内部自建 httpx（9 处之外，代码层包不住，只有依赖刀能覆盖）。
- 各构造点参数不同：timeout 3s/5s/60s 不等，另有 `follow_redirects=`、
  测试侧 `transport=` 注入——工厂必须全量透传。

## Goals / Non-Goals

**Goals:**
- SOCKS 系统代理用户的出网全链恢复（主刀：依赖；防线：降级工厂）。
- 「代理配置问题绝不把业务端点打成 500」钉成行为契约（spec outbound-http-client）。
- 无代理与 HTTP 代理路径行为守恒（用户问询焦点，见 Risks 首条）。

**Non-Goals:**
- 不改登录页文案分流（「S 端不可达提示语」另行小 change）。
- 不做代理设置 UI / 用户侧代理配置项。
- 不动 `call_server_api` 的主/兜底基址切换与既有结构化错误形态（code=-1）。
- openai SDK 内部 httpx 的构造兜底（代码不可达，由依赖刀覆盖）。

## Decisions

**D1 双刀分工：依赖是主刀，工厂是防线，缺一不可。**
socksio 装上后 httpx 才能真正走 SOCKS 代理，且 openai SDK 内部 httpx 一并修活；
工厂兜底防「依赖没进包 / 未来被裁剪」类回归，把最坏结果从「端点 500」压到
「降级直连」。只做依赖不加工厂 → 产物漏收 socksio 时 VPN 用户退回 500；
只加工厂不加依赖 → SOCKS 用户全靠直连（全局模式下直连不通），SDK 内部调用照炸。

**D2 兜底形态：构造期 try/except + `trust_env=False` 重建，不做全局关闭代理感知。**
- 否决「所有 client 直接 `trust_env=False`」：那会让 Clash HTTP 系统代理用户也
  退化直连——把 A 用户的修复变成 B 用户的回归。
- 否决「预探测 socksio 再决定」：要维护「哪些异常算代理问题」清单，且探测与
  实际构造之间存在双判定漂移；构造期异常直接接住最贴本质，正常路径零开销。
- 捕获范围：工厂内构造调用本身的 `Exception`（ImportError、畸形代理 URL 的
  ValueError 等），重建 `trust_env=False` 并留痕（降级原因 + 代理形态）。
  构造成功后的使用期异常不接——那是各调用点既有错误路径（Timeout/RequestError
  → code=-1），语义不变。
- **留痕脱敏**：代理 URL 可能内嵌凭据（`socks5://user:pass@host:port`），且 app.log
  是给用户回传的求诊文件——日志只记 scheme＋host:port，剔除 userinfo
  （`ai_client._host_of` 判例：完整 URL 不进日志）。
- 落点：backend 根新模块（如 `http_client.py`），避免塞进 auth_local 造成
  zhuque/prompt_pack/update_check 反向依赖业务模块。

**D3 九处构造点全部换用工厂（sync/async 双入口）。** 异步 7 处走 async 入口，
`prompt_pack/sync.py` 两处同步 `httpx.Client` 走同步入口（同一降级语义）。
两条实现硬约束：
- **晚绑定**：工厂内部以 `httpx.AsyncClient(...)`/`httpx.Client(...)` 模块属性形态
  调用（`import httpx` 后属性访问），不得 `from httpx import AsyncClient` 导入期
  绑定——既有 7 处测试夹具（test_server_api_fallback/test_api_format/
  test_llm_probe_logging/test_ai_layers）全部 `monkeypatch.setattr(<模块>.httpx,
  "AsyncClient", fake)`，晚绑定才可被拦截，否则夹具静默失效、测试开始打真网。
- **kwargs 全量透传**：timeout/follow_redirects/transport 等原样传给真 client
  （test_api_format 夹具依赖 transport= 注入到达真构造）。
逐点迁移时核对各自原参数不丢失。openai/anthropic SDK 路径不动。

**D4 产物自证双保险。** httpx 对 socksio 是函数级运行时 import，静态分析有漏收
风险：socksio 钉入 `bundle_manifest.py` 的 `HIDDEN_IMPORTS` **单源**——该清单是
PyInstaller/Nuitka 双引擎共同消费、由 tests/test_bundle_manifest.py 钉 parity 的
现成机制（现含 httpx 无 socksio）；**不得**只在 build.spec 本地私加——Nuitka 对
缺条目不 FATAL，会静默漏收，事故在 Nuitka 包原样复发。加上发布产物解包抓特征串
自证（c-prompt-pack-hardening 判例：抓产物特征串，别只看构建命令成功）。
打包链改动按判例走 dispatch 演练。

**D5 测试形态：pytest 单测三分支，不新增 e2e spec。**
- 走代理分支：测试环境设 `ALL_PROXY=socks5://127.0.0.1:<port>` 让 httpx 走
  SOCKS 构造路径（socksio 装上后构造成功）。**断言必须可辨别**：检查所建 client
  的 mounts/transport 确为 SOCKS 代理传输（或起本地最小 SOCKS5 listener 断言
  连接真的抵达）——「端点非 500」不可作断言：三条出网链路的既有错误路径都把
  代理连接失败收敛为非 500 形态，与降级直连不可区分，改坏成永远直连测试照样绿。
- 降级分支：monkeypatch 使工厂首笔构造抛 ImportError，断言降级 client 生效、
  留痕日志（且不含 userinfo）、业务端点返回业务形态。
- 守恒分支：干净 env 下既有用例全绿即证明（无新分支介入）。
- Windows 注册表系统代理路径 CI（Linux）不可复现，归 task 4.3 用户实机验收口径；
  spec 中该场景标注为人工验收。

## Risks / Trade-offs

- [无代理用户回归] → 两刀均为惰性路径：构造成功即返回（零分支、零开销），
  HTTP 代理用户构造成功行为同旧；无代理路径由既有全量 pytest 回归钉住。
  仅 SOCKS 场景行为变化（崩溃 → 走代理）。
- [PyInstaller 漏收 socksio] → hiddenimports 显式钉 + 产物特征串自证任务双保险。
- [VPN 用户 LLM 调用经境外出口变慢] → 与浏览器同路径的一致行为，优于崩溃；
  DeepSeek 等国内端点在全局模式下确会绕行，属用户 VPN 拓扑决策，记 trade-off
  不做分流。
- [ALL_PROXY 指向的本地代理端口未开] → 走既有 RequestError 路径（结构化
  网络错误），与现状同语义，不新增处理。
- [各构造点 kwargs 差异漏迁] → 工厂纯透传，迁移 PR 里逐点核对参数清单。

## Migration Plan

随下个发版带走（依赖进包须发版，无热修通道）。用户侧立即解法（发布前）：
关 VPN 后点「重新检测」，或把 VPN 客户端系统代理从 SOCKS 切 HTTP 模式。
回滚：revert 依赖行即可，socksio 无状态无迁移。

## Open Questions

（无）
