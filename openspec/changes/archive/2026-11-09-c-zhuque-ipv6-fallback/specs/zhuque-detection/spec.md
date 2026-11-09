## MODIFIED Requirements

### Requirement: C端本地后端唯一执行端点（前端零直连）

- 朱雀检测 SHALL 只由 C端本地后端执行：`POST /api/novels/{project_id}/chapters/{chapter_ref}/zhuque-check`；前端 SHALL NOT 直连腾讯 EdgeOne 网关、SHALL NOT 持有 Key 明文。将来若迁移 S端统一代理，只替换该端点实现，前端契约不变。
- 落盘责任在**前端调用方**：前端 SHALL 在发起检测前触发并等待本章自动保存链 flush 完成（含防抖窗口内未落盘改动；沿用既有 flush 先例），落盘失败 SHALL 明确报错且不发起检测（SHALL NOT 按盘上旧文送检白耗额度）；后端端点只读落盘正文原样送检，SHALL NOT 触发任何章写入。
- 端点读取落盘正文后调用 EdgeOne 网关文本检测（`POST {base}/v1/providers/zhuque-text/classify`，Bearer Key），base_url 走环境变量可覆写（默认真实网关）供测试桩替换。请求体 `text` SHALL 为**规范化管道输出**（换行归一 → 非空段切分 → 各段 trim → `\n` join，含 NBSP 归一）；`prose_hash` SHALL 即对该文本的 sha256（哈希对象=请求体文本，可对请求体复算）；422 上限对同一文本计量。
- 出网连接 SHALL 先按系统解析结果连接（现行为不变）；当且仅当首连发生**连接相位**失败（connect 超时、网络不可达）时，SHALL 以强制 IPv4 重试一次（2026-11-09 真机案：网关 AAAA 可解析但 v6 路由黑洞，v6 优先首连挂满 connect 超时）；回退请求的失败 SHALL 沿用既有错误映射对外（与单次失败同语义），SHALL NOT 产生额外错误分支；读超时与上游 HTTP 状态错误 SHALL NOT 触发回退。
- 每次 classify 调用（含连接测试）SHALL 恰产生一行 `zhuque_classify` 留痕（llm.log 专项档＋app.log 双写）：host＋path＋上游状态码＋耗时＋字符数＋结果分类；动用 IPv4 回退 SHALL 在行尾以 `fallback=ipv4` 标记（未回退＝行形状不变）；正文与 API Key 永不落行。
- 响应 SHALL 为：`{ok, prose_hash, summary: {human_ratio, suspect_ratio, ai_ratio, softmax_confidence}, segments: [{paragraph_index, label, confidence}], usage_tokens, checked_at}`；`label` 取值 0=人工、1=AI、2=疑似；`paragraph_index` 为非空段序（见切分条款）；`checked_at` 为服务端落库时间（ISO 8601）。
- 端点对章数据 SHALL 只读（仅读正文，落库写 `zhuque_results` 旁表除外），SHALL NOT 调用任何章写接口；检测行为 SHALL NOT 触发章内容变更。

#### Scenario: 检测成功返回结构化结果

- Given 本章有 6 个非空段落、Key 有效、编辑器改动已 flush
- When 前端发起检测
- Then 返回 ok=true、prose_hash 等于请求体文本的 sha256、segments 含 6 条段落级 label+confidence、summary 三占比合计约 1（浮点容差断言）、checked_at 非空

#### Scenario: 空正文拒绝检测

- Given 本章正文为空或全部段落剔除后无有效内容（只有空行/空白行）
- When 发起检测
- Then 返回 400 与可读提示（先写正文），不调用上游网关

#### Scenario: 连接相位失败回退 IPv4 接通

- Given 本机到网关的 IPv6 路由不通（AAAA 可解析、SYN 无应答）且 IPv4 可达
- When 首连（系统解析、v6 优先）connect 超时，回退请求成功返回
- Then 检测正常完成，该次调用恰两次出网请求，恰一行留痕且行尾 `fallback=ipv4`

#### Scenario: 回退请求再失败沿用既有映射

- When 首连连接相位失败、回退请求亦失败（如读超时）
- Then 对外错误与单次失败同语义（status=0 映射不变），仍恰一行留痕并带 `fallback=ipv4`

#### Scenario: 读超时不回退

- When 首连成功建立但响应读超时（网关推理慢）
- Then 不触发 IPv4 回退（恰一次出网请求），留痕行无 fallback 标记
