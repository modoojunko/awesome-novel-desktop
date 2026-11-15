## Context

C端 后端对 CDN/更新类出站有一道 SSRF 防线：目标须 https＋烘焙可信域，且 DNS 解析结果
全部为公网 IP（`ipaddress.is_global`）。该防线在四个模块各有一份拷贝，行为微差（kb 两份
带 `127.0.0.1/localhost` 宿主逃生口；update_check 有 async/同步两版）：

- `client/backend/update_check.py`（`_validate_outbound_url` async ＋ `_validate_outbound_url_sync`）
- `client/backend/prompt_pack/sync.py`（`_validate_outbound`，daemon 线程）
- `client/backend/kb/baseline.py`、`client/backend/kb/tree_sync.py`（`_validate_outbound`，经 `asyncio.to_thread`）

clash verge 等 TUN 代理默认 fake-ip DNS：所有域名解析成 `198.18.0.0/15` 假 IP（RFC2544
保留段，Python 判 `is_global=False`）→ 守卫在连接发出前拒绝 → 检查更新/提示词包/知识
同步全灭，而登录链（无守卫、走 httpx 透明经代理）正常——用户实测与此完全吻合。
见 proposal.md「Why」。

## Goals / Non-Goals

**Goals:**
- fake-ip 全命中＋可信域＋https 的出站放行，四条链路（更新/提示词包/知识基线/知识树）行为一致。
- 四份守卫拷贝收敛为单一共享实现（策略单源），既有语义（含 kb 环回逃生口）逐字保持。
- fake-ip 环境下的失败可辨：失败原因细分 `proxy_fake_ip`，前端三处指路文案。
- 干净环境（无代理/系统代理非 TUN）行为逐字节不变。

**Non-Goals:**
- 不做「系统代理注册表读取＋代理重试」（AI 供应商链路，另一 change）。
- 不动登录/授权链路（本就无守卫，TUN 下可用）。
- 不动更新链路的静默降级设计（失败不向用户呈现，仅日志留痕）。
- 不引入 DoH/自管解析器等复杂方案。

## Decisions

1. **共享 util 落 `client/backend/outbound_guard.py`，两层 API**：
   - `classify_infos(infos) -> str`：纯策略判定，verdict ∈ `ok`（全公网）／`fakeip`（全部落在
     198.18.0.0/15）／`blocked`（其余，含混合）。
   - `validate_outbound(url, trusted_hosts, *, allow_loopback_host=False) -> tuple[bool, str]`：
     sync 全流程（https＋可信域＋getaddrinfo＋classify），返回 (放行, verdict)。
   - 选两层而非单函数：update_check async 版的 DNS 解析须离开共享事件循环（同步解析会
     冻结应用），实现取 `asyncio.to_thread(validate_outbound, …)`——与旧 `loop.getaddrinfo`
     同一默认执行器，语义等价且四调用方共用一条代码路径。纯策略层 `classify_infos` 是
     测试主靶（无需 stub DNS）。
   - 备选「单函数＋resolve 注入」被否：async 可调性别扭，且拆两层后测试更直白。
2. **放行条件取全命中**：`all(ip in FAKEIP_NET for ip in resolved)` 才判 `fakeip`；任何混合
   （fake-ip 混真实内网/环回）判 `blocked`。理由：混合是 DNS rebinding 的现实形态，全命中
   才是 TUN fake-ip 的唯一指纹；保守取交集不损失兼容性。
3. **verdict → 失败原因映射在各调用方就地做**：探测/同步主路径先显式 validate 捕 verdict
   再 fetch（fetch 内部二次校验保留，成本一次系统解析缓存命中）；任一候选 verdict==`fakeip`
   且最终失败 → reason `proxy_fake_ip`，否则既有 reason 不变。更新链路只写日志留痕
   （`logger.warning` 带 verdict 摘要），不改任何用户可见行为。
4. **前端 reason → 文案映射沿用既有结构**：PromptPackModal `FAIL_NOTES` 表加一项；
   KnowledgeSyncModal 失败态按 reason 取文案（既有固定文案为缺省）；LoginPage
   `checkAuthorized` 异常时返回 `"network"` 哨兵（轮询中等同 false 静默），仅轮询结束/
   手动复查呈现网络指引文案。不新增组件/状态形态，warn/err 语气沿用。
5. **守卫语义对拍**：收敛后四调用方的既有单测（stub getaddrinfo 形态）必须原样通过——
   这是「行为逐字保持」的验收线；新增测试只补 fake-ip 矩阵与 reason 映射。

## Risks / Trade-offs

- **自定义 fake-ip 段的代理**：非 198.18.0.0/15 的自订 fake-ip-range 仍会被拒。接受：主流
  clash 系缺省即该段；指路文案给出关 TUN 的兜底出口。
- **放行后连接仍失败**（代理节点不通官方域）：落到既有超时路径（fetch timeout 不变），
  reason 为 `proxy_fake_ip`，文案指引用户检查代理——语义自洽。
- **198.18.0.0/15 放行的安全面**：该段为 benchmark 保留段、不可路由到内网服务，DNS
  rebinding 防护语义不受损；攻击者把可信域解析到该段只能得到不可达或经代理回到真域，
  https 证书校验端到端不变。
- **收敛引入的行为漂移**：以既有四组单测全绿为硬闸；diff 审查点＝四个旧函数删除后无
  残留分支差异（尤其 kb 逃生口的宿主白名单与 update_check async 的解析线程约束）。
