# c-relay-compat-probe — 中转站兼容探针：裸域名同源归一＋清单 403 降级

## Why

内测中转站配不通两类实锤（2026-10-08，案例 Fox AI `api.lunarfox.cn`，new-api 系 OpenAI 兼容站）：

1. **裸域名半通假象**：该类站 SPA 对任意非 `/v1` 路径回 200 网页（curl 实勘 `/models`、`/chat/completions` 全是 HTML），真 API 只在 `/v1/*`。代码只有 models 探测补 `/v1`，对话探针与生成调用拿裸 base 直拼 `/chat/completions` 打到网页上——「已拉到 N 个模型」绿灯亮着、测试/生成全挂，用户无从自查。
2. **清单 403 假阴性**（用户截图实锤）：照指南填 `…/v1` 仍失败——token 有效（无效 Key 是 401「Invalid token」），但中转站按分组权限拒绝清单访问（403「无权访问 gpt特定版分组」）；代码把 models 端点的 401/403 一律短路判「认证失败」，对话探针没机会跑，而该 token 的对话路径（`claude-sonnet-4-6`）很可能完全可用。

两者都是「地址形态／清单权限」问题被误判成「配置不可用」。中转站是国内用户接 Claude/Gemini 的主流路径，须类型化解决而非个案白名单。

## What Changes

- **版本段归一单源化**：openai 格式 base 归一——路径含 v+数字段（`/v1`、`/v4`、`/v1beta`…）原样保留，裸域名补 `/v1`；models 探测、对话探针（主链＋404 降级）、生成调用（ai_client→OpenAI SDK）四处共用——spec「与生成调用同源推导」的完整兑现（#741 只修了登记预填值，管不到用户手填地址）。anthropic 格式不受染（SDK 自拼 `/v1/messages` 惯例保持）。
- **连接测试清单 403 降级**：models 端点 403 并入 404 降级链（两格式同享）——拿「已选模型 > 候选首个 >（仅 anthropic）占位」发「你好」最小生成探针验证真实对话路径，通即「连接正常」＋「清单被拒（403）」说明；openai 无 id 不降级、判负提示填写模型名；401（Key 无效）保持硬判不降级（对话必同样 401，不白花请求）。
- **只拉清单轻探针 403 口径**：openai 格式 403 按零生成语义回 ok＋空清单＋候选 id＋「分组权限」说明（引导手填）；anthropic/ollama 格式 403 保持鉴权失败硬判。
- **顺带归位两处同类**：Gemini 官方兼容层 models 探测路径（端点锚 `/v\d+$` 误补 → `/v1beta/openai/models` 归位）、ollama 裸 base 生成路径（`/chat/completions` 404 → `/v1/chat/completions`）。
- 明确不做：Base URL 保存时自动改写（2026-10-05 拍板不做自动改写，归一只在请求推导层单源发生，用户所见与库内存储保持一致）；models 429/5xx 降级（无实锤，保持现判）；「测试连接」判据与「你好」探针不动。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`：「按接口格式探测连接」——403/404 同享降级、401 硬判、裸域名全链同源归一场景；「模型清单自动拉取」——openai 格式 403 回 ok＋空清单＋说明（SHALL NOT 判鉴权失败）。

## Impact

- `client/backend/api_configs/connection.py`：`normalize_openai_base` 单源（段判 v+数字）＋models/对话探针/404 降级三处接入＋403 降级分支＋`MODEL_LIST_FORBIDDEN_NOTE`。
- `client/backend/ai_client.py`：openai 分支 base 归一传 SDK，`_base_url` 同步归一形（留痕 host／禁思考记忆与实际请求同形态）。
- `client/backend/tests/test_api_format.py`：归一化表＋裸域名主链/版本段不动/Gemini 兼容层＋403 降级（通/双拒/无 id/anthropic）＋401 硬判＋fetch 403 等用例。
- 真机冒烟：lunarfox 裸域名与 `/v1` 两种填法全链；Gemini 兼容层直配（#741 遗留项，顺带修正其清单路径）。
