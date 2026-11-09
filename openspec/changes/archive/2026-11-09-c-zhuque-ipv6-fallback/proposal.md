# c-zhuque-ipv6-fallback：朱雀检测连接相位失败 IPv4 回退

## Why

真机首用实锤（2026-11-09，Mac 桌面端）：调朱雀检测必报「无法连接朱雀服务或响应超时」。
定诊链：llm.log `result=timeout duration_ms=10120`（恰 connect=10s 相位）→ 本机探测
DNS 正常（网关同时有 AAAA＋A）、默认 curl（v6 优先）20s 零 TCP、`curl -4` 强制 v4
9.7ms 接通且 classify 返回标准 401（网关完全正常）——**根因＝IPv6 黑洞**：EdgeOne
网关 AAAA 可解析但本机 v6 路由不通（SYN 无应答），系统解析 v6 优先、httpx 无
happy-eyeballs 回退，首连挂满 connect 超时。用户侧体感＝功能全废。

## What Changes

- **连接相位失败 IPv4 回退**：`zhuque/client.py::classify` 首连按系统解析（现状不
  变）；仅当首连抛**连接相位**错误（`httpx.ConnectTimeout`/`httpx.ConnectError`，
  即 connect 超时/网络不可达）时，以 `local_address="0.0.0.0"` 强制 IPv4 重试一次。
  读超时（网关推理慢）与 HTTP 状态映射不在触发面，语义零变化。
- **留痕带 fallback 标记**：动用回退时恰一行留痕行尾追加 `fallback=ipv4`（未回退＝
  行形状与既有完全一致）；「每调用恰一行」契约不变。
- 连接测试（`/api/v1/zhuque/test`→`classify("ping")`）与章节检测同走此路径，一并修好。

## Capabilities

- **zhuque-detection**：MODIFIED「C端本地后端唯一执行端点（前端零直连）」——增
  连接相位失败回退条款＋三场景（回退接通/回退再败同语义/读超时不回退）。

## 不动项

- 401/403/429/5xx/非 JSON 200 的既有映射、门禁、切分对齐、落库、额度台账零改动。
- `api_configs/connection.py` 写作模型探针不随本改（各供应商现网可达，IPv6 黑洞
  是 EdgeOne 网关特定形状；将来同类案情再泛化）。

## Risks

- 回退重试使连接相位失败的最坏等待翻倍（10s＋10s）——黑洞环境首次失败本来就是这个
  量级，且回退成功时总等待不变（10s＋<100ms）；可接受。
- v6-only 网络的用户：回退路径 v4 也会失败，行为退化为现状（报连接错误），无新增伤害。
