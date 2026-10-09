# design — c-thinking-config

## 契约依据（2026-10-09 实勘）

- GLM-5.3 文档（docs.bigmodel.cn/cn/guide/models/text/glm-5.3）：`thinking.type` 仅
  `enabled`，「仅支持开启思考，不支持禁用思考」；顶层参数 `reasoning_effort`：
  low（轻量推理）/high（增强推理）/max（深度推理，默认）。
- 迁移指引（migrate-to-glm-new）：现用 `thinking.type:"disabled"` 的应用在换 glm-5.3
  前须改 `enabled` 并设 effort。
- 用户报错原文（v0.30.2 连接测试）：「该模型始终思考，不支持关闭思考；请使用 low、
  high 或 max」——与文档一致，且证明探针的 disabled 被值级打回（非未知字段）。

## 拍板（2026-10-09，与用户对齐）

1. **形态**：放进「添加 API Key / 编辑」弹窗，每个 API 配置各带一套；弹窗内两控件
   （思考模式 开/关＋思考强度 三档），测试连接探针按同一套参数发。
2. **档位**：严格照 GLM 文档三档 low/high/max，**默认 low**——整条链一直按「省 token
   省延迟」取向（现状是干脆关思考），开了思考也先给最省的一档，要质量自己调高。
3. 端点拒参数时保留自动去参重试兜底。

## 关键决策

### D1 强度只随「开」下发；判定类恒关

- 关（默认）：`thinking:{type:disabled}`，与现状逐字节等价——存量配置零行为变化，
  非 GLM 供应商零风险。
- 开：`thinking:{type:enabled}`＋`reasoning_effort`。effort 不随「关」下发。
- **判定/短答复类调用**（`settings/ai_router._judge_chat` 单漏斗，volume-plan-ai spec
  钉住的路径）恒以显式 `thinking:{type:disabled}` 传参压过配置：思考型模型会把预算花在
  推理上、JSON 判定只回思考不回文本（`_JUDGE_MAX_TOKENS` 提到 4096 正是旧账）。配置级
  开关不改变这类调用的内部口径。显式传 thinking 时配置 effort 不搭车（关思考带 effort
  自相矛盾，部分端点会当未知参数打回）。

### D2 去参重试：探针不看文案、生成看文案

- **探针**（`connection._post_with_thinking_retry`）：带思考参数的 400 **一律**去参
  （thinking＋reasoning_effort）重试一次。理由：探针是用户点的一次性动作，多一次请求
  换判稳；文案匹配已被 GLM 纯中文拒法实锤漏判。两次都 400 时回「更贴切」的那份：原始
  400 若在说思考参数、重试 400 说了别的真因→回重试的；否则回原始（原始文案更能代表
  配置的问题）。
- **生成**（`ai_client`）：异常文案判据扩为 `thinking`/`思考`/`reasoning`/`effort`
  （GLM 报错含「思考」即命中）；不 unconditional——生成是热路径，业务 400（鉴权、
  内容政策等）不值得每发多打一次。命中后去参重试一次并记 base
  （`_THINKING_UNSUPPORTED_BASES` 语义不变：该 base 不再主动发思考参数）。
- **探针预算放大**：思考开启（或去参重试后）`max_tokens` 32→1024
  （`_PROBE_MAX_TOKENS_THINKING`）。强制思考模型会把输出预算花在推理上，32 只够思考、
  正文为空，探针会误判「回复为空」；「你好」探针即使全额 1024 也近似零成本。

### D3 anthropic 格式的 effort 透传

`reasoning_effort` 非 Anthropic 契约字段：openai 格式走 extra_body；anthropic 格式
thinking 走 SDK 形参、effort 随 extra_body 透传（GLM anthropic 兼容端点照收）。原生
Anthropic 开思考缺 `budget_tokens` 会被拒（错误文案含 thinking→去参降级），不做
budget 映射——GLM 用户走 OpenAI 格式（实锤配置即如此），原生 Anthropic 思考待真需求
再立项。

### D4 记忆的粒度代价（接受）

`_THINKING_UNSUPPORTED_BASES` 是 base 级进程记忆：同 base 下「配置 A 关思考触发记忆、
配置 B 开思考」时 B 的参数发不出（静默按厂商默认跑）。换 config 级记忆要引入「拒的
是字段还是值」的文案分类（回到文案匹配老路）。范围极窄（同 base 多配置且思考偏好不同），
接受；去参重试仍在，行为正确只是强度不生效。

### D5 迁移/备份

新列带 DDL 默认（0/low），迁入链 `build_plan` 按列交集 INSERT＋DEFAULT 兜底自动带回；
备份包加键不升 format_version（旧版导入端忽略未知键，新导入端对旧包缺键兜底关/low）——
与 api_format 加键同款兼容契约。

## 测试判据

- 回归钉：GLM 纯中文拒法 400→去参重试成功（探针＋openai 生成两路）；重试体无
  thinking/reasoning_effort 且预算放大。
- 下发钉：开＋high → `thinking:{type:enabled}`＋`reasoning_effort:"high"`；默认 →
  `disabled` 无 effort；显式 thinking 压过配置 effort。
- 判定类：`_judge_chat` 显式关思考（存量 judge 用例的 kwargs 断言面已覆盖）。
- CRUD：创建携带/缺省关 low/PUT 改值；备份导出导入带回。
- 前端：默认关 low、开→选档→提交负载、关时强度灰置值保留、编辑态回读。
