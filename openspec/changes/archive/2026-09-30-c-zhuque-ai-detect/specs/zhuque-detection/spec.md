## ADDED Requirements

### Requirement: C端本地后端唯一执行端点（前端零直连）

- 朱雀检测 SHALL 只由 C端本地后端执行：`POST /api/novels/{project_id}/chapters/{chapter_ref}/zhuque-check`；前端 SHALL NOT 直连腾讯 EdgeOne 网关、SHALL NOT 持有 Key 明文。将来若迁移 S端统一代理，只替换该端点实现，前端契约不变。
- 落盘责任在**前端调用方**：前端 SHALL 在发起检测前触发并等待本章自动保存链 flush 完成（含防抖窗口内未落盘改动；沿用既有 flush 先例），落盘失败 SHALL 明确报错且不发起检测（SHALL NOT 按盘上旧文送检白耗额度）；后端端点只读落盘正文原样送检，SHALL NOT 触发任何章写入。
- 端点读取落盘正文后调用 EdgeOne 网关文本检测（`POST {base}/v1/providers/zhuque-text/classify`，Bearer Key），base_url 走环境变量可覆写（默认真实网关）供测试桩替换。请求体 `text` SHALL 为**规范化管道输出**（换行归一 → 非空段切分 → 各段 trim → `\n` join，含 NBSP 归一）；`prose_hash` SHALL 即对该文本的 sha256（哈希对象=请求体文本，可对请求体复算）；422 上限对同一文本计量。
- 响应 SHALL 为：`{ok, prose_hash, summary: {human_ratio, suspect_ratio, ai_ratio, softmax_confidence}, segments: [{paragraph_index, label, confidence}], usage_tokens}`；`label` 取值 0=人工、1=AI、2=疑似；`paragraph_index` 为非空段序（见切分条款）。
- 端点对章数据 SHALL 只读（仅读正文），SHALL NOT 调用任何章写接口；检测行为 SHALL NOT 触发章内容变更。

#### Scenario: 检测成功返回结构化结果

- Given 本章有 6 个非空段落、Key 有效、编辑器改动已 flush
- When 前端发起检测
- Then 返回 ok=true、prose_hash 等于请求体文本的 sha256、segments 含 6 条段落级 label+confidence、summary 三占比合计约 1（浮点容差断言）

#### Scenario: 空正文拒绝检测

- Given 本章正文为空或全部段落剔除后无有效内容（只有空行/空白行）
- When 发起检测
- Then 返回 400 与可读提示（先写正文），不调用上游网关

### Requirement: 段落切分后端收口与上游对齐

- 正文段落切分 SHALL 由 C端本地后端统一定义并执行；「段落」谓词 SHALL 为**去除首尾空白后非空**的行（换行归一 `\r\n|\r` → `\n`，NBSP `\u00A0` → 空格）；`paragraph_index` SHALL 按非空段顺序 0 起编号。前端 SHALL 只按索引渲染，映射规则为「文档中第 k 个**非空**段落节点」（跳过空白节点），SHALL NOT 自行实现第二套切分逻辑。
- `prose_hash` SHALL 为规范化文本的 sha256，规范化管道钉死为：换行归一 → NBSP 归一（`\u00A0` → 空格）→ 按非空段切分 → 各段 trim → 以 `\n` join；NBSP 归一必须进管道本体——粘贴（Word/网页）会把真实 NBSP 插进编辑器文档，若前端重算不含此步，含 NBSP 的章会在结果返回瞬间整体误判「已过期」。前端 stale 判定 SHALL 用同一管道重算（前端输入取编辑器文档按保存链同款文本提取后的内容）。
- 上游返回的分段 SHALL 按其 `order` 序与本地非空段一一对应；上游分段数与本地非空段数不一致时 SHALL 返回 502（「检测结果与段落不一致，请重试」），SHALL NOT 静默截断或 best-effort 对齐。
- 端点 SHALL 在响应携带 `prose_hash`，作为前端标注失效判定的唯一依据。

#### Scenario: 前后端段落序一致（含空行与空白行）

- Given 正文为「A、空行、全空白行、B」交替组成的 6 个有效段
- When 检测返回 segments
- Then segment 的 paragraph_index 按非空段 0 起编号，前端取文档中第 k 个非空段落节点着色，含全空白行样本不错位

#### Scenario: 上游分段数不符明确报错

- When 上游返回分段数与本地非空段数不一致
- Then 端点返回 502 与「检测结果与段落不一致，请重试」，前端失败条给「重试」出口，不产生任何标注

### Requirement: 写作模型选取路径的朱雀隔离

- `api_configs` 通用写作模型选取路径（兜底取「任意 active 且有 Key 的配置」的逻辑）SHALL 增加 `vendor != "zhuque"` 过滤，SHALL NOT 在任何写作/生成链路把朱雀配置当作大模型使用。同类判据的隔离方向 SHALL 区分：`user_has_ai_key` 类「是否已有 Key」判据 SHALL 同加过滤（只配朱雀时应呈「未配置 Key」引导语义）；`require_ai_access` 的 Key 存在性前置检查 SHALL NOT 过滤（朱雀-only 的 MAX 作者须能通过它到达检测端点自身门禁）。
- 绑定侧 SHALL 防注入：`get_ai_client_for_novel`（按本书绑定直取配置）SHALL 对 `vendor == "zhuque"` 拒绝；「应用到全部书」类批量绑定 SHALL 校验目标配置 `vendor != "zhuque"`；备份导入的唯一 active 自动挂接 SHALL 跳过 zhuque 行。
- 通用配置读写域 SHALL 隔离朱雀行：配置列表、批量状态等面向「写作大模型页签」的查询 SHALL 过滤 `vendor == "zhuque"` 的行，SHALL NOT 让朱雀配置出现在大模型页签卡片列表、SHALL NOT 可经通用编辑/测试路径改动朱雀行（其 name/vendor/base_url 由专用端点内部固定）。
- 朱雀配置的 vendor SHALL 在专用保存端点内部写死为 `zhuque`（不依赖 base_url 推断）；vendor 解析 SHALL NOT 依 EdgeOne 域名把朱雀配置判为 openai 兼容厂商。

#### Scenario: 朱雀配置不被兜底吞用

- Given 作者只配置了朱雀 Key、未配置任何大模型 Key
- When 触发任一写作/生成动作
- Then 系统按「未配置大模型」处理（引导去模型配置），SHALL NOT 把朱雀配置当 chat 模型发起调用

#### Scenario: 朱雀卡不进大模型页签列表

- Given 作者已配置朱雀 Key 与一把 DeepSeek Key
- When 打开模型配置页大模型页签、拉取配置列表
- Then 列表只有 DeepSeek 卡，无朱雀卡；朱雀行的通用编辑/通用测试路径不可达

### Requirement: 检测门禁与额度口径

- 后端检测端点 SHALL 要求登录，并挂会员级防御校验（与 ai-check 同源机制）；MAX 精确门禁由前端 `useFeature("ai-detect")` 依 S端 entitlement 快照判定（快照只对 MAX 发放该 key，试用不含；快照缺失或权益异常时一律按未授权处理）；本地门禁 UX 级可绕过为定价文档已认账口径。
- 端点 SHALL 区分「会员但朱雀 Key 缺失/刚被删除」的分支（503，`zhuque_not_configured`，提示指向模型配置朱雀页签），SHALL NOT 把它混入 401 语义。
- 端点 SHALL 把上游每次实际扣减额度（`makers_models_usage.total_tokens`，缺失回退 `usage.total_tokens`）记入本地用量留痕（独立 operation="zhuque-check"，model 记 "zhuque"）；既有用量汇总查询（总量/按配置/按项目）SHALL 排除该 operation，SHALL NOT 混入写作模型用量统计；C端 SHALL NOT 提供朱雀月度额度统计，月度用量一律引导腾讯云控制台查看。

#### Scenario: 上游 401 映射为 Key 无效

- Given 作者配置的 Key 已在腾讯侧失效
- When 发起检测
- Then 返回 401 语义错误，前端失败条显示「API Key 无效或已失效」＋「去配置」「重试」出口

#### Scenario: 限流与额度耗尽同口径

- Given 作者 Key 有效且非本地原因
- When 上游返回 429（限流或免费额度耗尽）
- Then 端点透传可读原因，前端文案为「触发限流或本月免费额度已用完，以腾讯云控制台为准」＋「重试」出口

#### Scenario: 会员但未配朱雀 Key 直调端点

- Given 作者已配任一写作大模型 Key，但朱雀 Key 缺失或刚被删除
- When 端点被调用
- Then 返回 503（zhuque_not_configured），SHALL NOT 误报为 401 Key 无效
- 注：作者**任何 Key 都没有**时，`require_ai_access` 的通用 503（AI 服务未配置）先行——前端引导态不依赖该响应的区分

#### Scenario: 同章并发检测被拒

- Given 同一作者同一章的检测请求在途
- When 第二发请求到达
- Then 返回 409（zhuque_check_in_progress），前端映射为「检测中」既有态

### Requirement: 不落库与负载护栏

- 检测结果 SHALL NOT 写入数据库：仅前端内存存续（跨页签/视图切换存活、应用重启即弃）；归档、备份包 SHALL NOT 包含任何检测数据。
- 单次送检正文 SHALL 设字符上限（默认 30000 字），超限返回 422 与可读提示（明确报错，SHALL NOT 静默截断）。
- 同一作者同一章节的检测请求 SHALL 支持取消（前端切章/重复点击时中断在途请求）；服务端对并发的最小防护为拒绝同章在途重复执行。

#### Scenario: 重启后无残留

- Given 作者检测过第 3 章并看到结果
- When 重启应用
- Then 标题区结果条与正文标注均不出现；再次查看需重新检测（不自动重发请求）

#### Scenario: 超长章明确拒绝

- Given 正文超过 30000 字
- When 发起检测
- Then 返回 422 与「正文超出单次检测上限」提示，未调用上游、未消耗额度
