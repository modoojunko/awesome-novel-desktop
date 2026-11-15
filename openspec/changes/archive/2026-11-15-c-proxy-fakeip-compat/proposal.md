## Why

用户实机（clash verge TUN 模式）复现：登录可用，但「检查更新」「获取提示词包」全部失败，提示词包状态卡 `syncing`、`version` 空。根因在 C端 自己：出站校验要求 DNS 解析结果全部为公网 IP（SSRF 防线），而 TUN+fake-ip 代理把所有域名解析成 `198.18.x.x`（RFC2544 保留段，`is_global=False`）——请求未发出即被自家守卫拒绝。该守卫在 C端 后端有四份拷贝（update_check / prompt_pack/sync / kb/baseline / kb/tree_sync），行为需一致收敛。

## What Changes

- 新增共享出站守卫模块（收敛四处 `_validate_outbound` 拷贝，行为对拍保持）：在原「https＋可信域＋解析全公网」规则上新增 fake-ip 放行——解析结果**全部**落在 `198.18.0.0/15` 且主机在烘焙可信域且 https → 放行（连接仍由代理按域名转发，守卫的 DNS rebinding 防护语义不变：该段不路由到任何内网服务）。
- 混合解析（fake-ip 混真实内网 IP）、非可信域、http 仍拒绝；kb 两处既有的 `127.0.0.1/localhost` 开发逃生口语义保持。
- 守卫判定透出 verdict（ok / fakeip / blocked），失败原因细分：fake-ip 环境下的网络失败报 `proxy_fake_ip`（其余仍 `cdn_unreachable` / 既有 reason 不变）。
- 前端失败文案映射：提示词包弹窗、官方知识更新弹窗对 `proxy_fake_ip` 显示指路文案（关 TUN / 加 fake-ip 白名单，附既有重试出口）；登录页把「网络不可达」与「未检测到登录」分开提示（网络失败不再误导为「请在浏览器中完成登录」）。
- 更新检测链路保持静默降级设计不变（全部失败不向用户呈现错误），仅守卫行为修复。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `outbound-http-client`: ADDED Requirement——fake-ip 代理环境的出站校验放行策略与四模块一致性（含 verdict 诊断透出、混合内网仍拒）。
- `prompt-pack-delivery`: MODIFIED「提示词包获取与安装（C端）」（fake-ip 环境失败原因细分 `proxy_fake_ip`）＋ MODIFIED「写作能力引导弹窗（首装/更新/手动）」（失败文案映射指路）。
- `knowledge-baseline`: MODIFIED 同步失败语义（fake-ip 环境失败原因细分与官方知识更新弹窗指路文案）。
- `frontend-auth-heal`: ADDED Requirement——登录页授权等待环节区分「网络不可达」与「尚未检测到登录」的提示语义（轮询中间失败维持静默）。

## Impact

- 后端：`client/backend/` 新增共享守卫模块；`update_check.py`（async＋sync 两处校验）、`prompt_pack/sync.py`、`kb/baseline.py`、`kb/tree_sync.py` 接入；失败 reason 字段新增取值 `proxy_fake_ip`。
- 前端：`PromptPackModal.tsx`（FAIL_NOTES 映射）、`KnowledgeSyncModal.tsx`（失败文案）、`LoginPage.tsx`（网络失败与未授权分文案）；均为既有组件内文案级改动，不新增组件形态。
- 测试：后端新增守卫单测＋四调用点 reason 断言；前端文案映射测试；现有 getaddrinfo 桩测试行为保持对拍。
- 不触碰 S端、发布链（release.json 键集不变）、令牌与组件词汇。

## Design Impact

- 受影响端：C端 单端（S端 零改动）。
- 受影响屏/弹层：写作能力引导弹窗（PromptPackModal，失败态文案）、官方知识更新弹窗（KnowledgeSyncModal，失败态文案）、登录页（LoginPage，错误提示文案）。均为既有弹层内文案替换，无版式/结构变化。
- 对象状态：提示词包失败态新增 reason 取值 `proxy_fake_ip`（沿用既有 warn 形态失败卡，不新增状态对象）；知识同步失败态同理；登录页沿用既有 `err` 提示段。
- 共享段：不触碰（不涉及 base.css 令牌与基础组件类）。
- 原型先行：免——纯失败态文案与 reason 映射，无版式、组件结构、令牌变更（登记于 tasks 首任务）。
- 设计工件：实现侧自查（对照 design-language §13：补救语句带可点击出口——弹窗既有「重试」按钮、登录页既有「重新检测」按钮）。
