## Context

- 现状不对称：models 探测对裸域名补 `/v1`（`_openai_models_url`，行尾锚 `/v\d+$` 判版本段）；对话探针主链（connection.py 裸拼 `{base}/chat/completions`）、models 404 降级链（`_build_probe` fallback 同裸拼）、SDK 生成调用（`ai_client._init_client` 直传 base）三处都不归一。
- kakou 案实测（2026-10-09）：new-api 系网页壳对任意非 `/v1` 路径回 200 `text/html`，真 API 在 `/v1` 下——裸拼地址拿到 200 网页被判 `endpoint_mismatch`。
- 2026-10-08 同方向 PR #747（含 403 降级）曾因反馈证伪整体回退，未合入；本 change 只重启归一化单项，判据草案（段锚 `/v\d+[a-z]*(/|$)`）留档于观察记录。
- spec「按接口格式探测连接」钉「与生成调用同源推导」——现状只兑现一半，本 change 是把这句话兑足。

## Goals / Non-Goals

**Goals:**
- 归一单源：一个函数、一处判据，四个消费点（models 探测／对话探针主链／404 降级链／SDK 构造）共用
- 裸域名 base 全链路可用（探测绿＝生成可用，SHALL NOT 出现探针绿生成红）
- 顺手修 Gemini 兼容层中段版本段被行尾锚误判的潜在错址
- 网页体误判文案给可执行的补救出口

**Non-Goals:**
- 不改 anthropic 格式（惯例相反，SDK 自拼 `/v1/messages`）
- 不改 ollama（已有剥 `/v1` 逻辑）
- 不在保存链路改写用户输入（落库原样；归一只发生在构造请求时）
- 不动 models 403 分组权限降级（另一观察，未拍板不卷）

## Decisions

1. **归一函数放 `api_configs/connection.py`**（`normalize_openai_base`）：探测模块持有「与生成同址」契约的措辞源头；`ai_client` 反向 import 它（`ai_client → api_configs.connection`，与既有 `ai_client → api_configs.crypto` 同向，无环）。备选：独立 root 模块——为一个纯函数立模块不值。
2. **版本段判据用段锚 `/v\d+[a-z]*(/|$)`**：段以 `v+数字` 开头即算（容忍 `v1beta` 类后缀）。行尾锚会漏判中段版本段（Gemini `…/v1beta/openai` 被误补成 `…/v1beta/openai/v1/models` 死址）；端点锚会漏判 `…/v1beta` 行尾形态。
3. **SDK 构造处同步 `self._base_url` 为归一形**：留痕行（llm_call/llm_probe 的 host/path）与禁思考记忆（`_THINKING_UNSUPPORTED_BASES`，按 base 精确串键控）必须与实际请求 base 同一形态，否则记忆永不命中、留痕指向未发出的地址。
4. **落库不改写**：用户输入原样保存；归一只在消费点发生——改写落库需要迁移存量且抹掉用户原始输入，收益为零。
5. **文案只补不改，出口按格式分流（评审 2026-10-09）**：原句「请检查 Base URL 是否填成了网站地址」在真填错网址场景仍准确，追加括号补救出口而非替换，测试钉子（`"Base URL" in error`）不破；「补 /v1」出口仅 openai 兼容格式给（anthropic 惯例 base 不带 /v1、探针侧剥掉，ollama tags 探针同剥——补了是空操作），`_v1_hint` 按格式/vendor 分流。

## Risks / Trade-offs

- **裸根端点被锁死（评审 2026-10-09 显式接受的取舍）**：仅提供裸根 `POST /chat/completions`（无任何 `/v1` 路径）的 openai 兼容端点（典型：个人 nginx 反代直透单模型后端），改动前经 404 降级链（裸拼 fallback）＋SDK 裸传是**端到端可用**的；本 change 归一化覆盖全链路（含降级链与 SDK）后，任何输入形态都无法再命中裸根路径——该类部署从「可用」变为「不可配置」。评估：无此类用户实报（kakou 类 new-api 中转有实锤且是中转反馈主流）；反向取舍（降级链保持裸拼）会造「降级探针绿、SDK 生成红」假通，恰是本 change 立项要消灭的形态；escape 出口（「地址已含完整路径」标记类 UI）涉前端与规格，按「有实锤才动手」判例留待真实反馈另行立项。
- **DeepSeek 裸域名预填值行为变化**：现 `https://api.deepseek.com`（登记值裸域名，官方同时服务裸与 `/v1`）归一后请求 `/v1/chat/completions`——官方文档明确支持，无风险。
- **存量测试断言漂移**：裸 base 的对话探针 URL 断言（405 案点名地址、fallback 构造）需同步更新，见 tasks。
