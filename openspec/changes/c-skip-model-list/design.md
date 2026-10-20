## Context

连接测试与清单拉取都在 `client/backend/api_configs/connection.py`：`test_connection` 先 GET `{base}/models`，仅对 **404／200 网页体** 降级发最小生成探针（`_fallback_probe` 组件已存在），其余状态码硬判负；`fetch_models` 是零生成调用的轻探针。2026-10-16 CloudBase 网关实锤（见 proposal Why）：`GET /models` 回 400/403（403 附误导文案），chat/completions 完全正常——探测语义与端点现实错位，`last_test_status` 失败态再被 `ai_state.config_key_usable` 采信，生成被健康闸挡死。

约束：探测/生成/清单三链共用 `normalize_openai_base` 同源归一与 llm.log「每个出网请求恰一行」不变量（c-llm-call-log 评审 P2）；前端表单已有「清单拉取失败 → 手填」的完整出口（组合框手填、候选 chips、note 呈现）。

## Goals / Non-Goals

**Goals**
- 连接测试的健康判据恒为对话探针：清单请求凡未带回可用清单即降级，判定以探针为准。
- 用户可用高级选项显式声明「端点无清单接口」，跳过后连清单请求都不发。
- CloudBase 型网关的配置测试转绿 → `last_test_status` 转好 → 健康闸自然开。
- 轻探针文案如实（403/400 不再标「认证失败」）。

**Non-Goals**
- 不动生成链路（`ai_client.py`）与健康闸谓词（`config_key_usable`）。
- 不做厂商特判（不新增 CloudBase vendor 按钮／白名单——协议行为修，另立 change 才谈预设）。
- 不改 openai 格式 404 的「异常响应」语义（404 更可能是地址填错，维持提示核对）。
- 不做「网关无清单」的跨请求缓存/记忆（每次测试按当次行为判定，无状态）。

## Decisions

### D1. 降级判据＝「未带回可用清单」全集，不按状态码白名单
models GET 的失败分支统一改道 `_fallback_probe`（404/200网页体 既有路径不变，新增 400/401/403/405/429/5xx）。理由：网关对清单路由的失败形态不可枚举（已实锤 400 与 403 两种），白名单每遇到新形态就要再修一轮；而「探针同址同鉴权」保证了判定不失真——坏 Key 的探针照样回 auth_error，用户看到的仍是「认证失败」，只是死因来自真实对话端点。**代价**：真坏 Key 多一次探针调用、慢约 1–2 秒（接受）。**替代方案**（否决）：只降级 400/403——下次遇到 405/429 型网关还得再改。
无 id 守卫保持：401/403 无 id 维持「认证失败」（鉴权语义明确，与清单无关）；其余无清单形态无 id 按「提示填写模型名」判负；不编造 id。

### D2. skip_model_list 用布尔列，跳过在 test_connection 入口分流
新列 `skip_model_list`（Boolean，`server_default="0"`）。**入库机制按本仓架构**：版本库文件制（novel-v{版本}.db）＋首启 `create_all`，**没有代内补列路径**（main.py 库治理明令不再对既有库 DDL）——新列由新库 create_all 自然具备；旧版库走指纹 mismatch 重命名＋带回，带回引擎按列交集制定计划（`migration/engine.build_plan`），目标缺失列带 server_default 时由 DDL 默认值兜底，**引擎零改动**。**入口分流**而非失败分支再判：`skip=1` 时直接跳过 models GET 进对话探针——跳过的语义是「这个端点没有清单接口」，发了请求再忽略属于无谓出网。布尔够用：只有一种跳过语义，无需 mode 枚举。表单（未保存态）的 raw 测试（`TestRawBody`）同样加可选字段——创建弹窗勾选后点「测试连接」必须直探。

### D3. fetch_models 对 400/403/405 返回 ok=True＋空清单＋说明，401 维持判死
403 无法区分「路由权限」与「清单缺失」，而两者对用户的下一步动作相同（手填模型 id → 测试连接），故按无清单口径返回 ok＋note，让选择器进「暂无清单——可手填」态而非红色失败态；401 是明确的 Key 层错误，维持「认证失败」。404 维持「异常响应」（地址语义）。返回形态复用 anthropic-404 的既有信封（models=[] + candidates + note），前端零新逻辑。

### D4. 文案与留痕
上游状态码可出现在探测文案（既有 spec 口径「认证失败 (HTTP 401)」），新文案沿用；面向用户的名词是「模型清单」，不出现端点路径。llm.log 不新增 result 枚举：skip 时不发请求故无 models_list 行；降级时 models_list 行按状态码机械映射照旧落，后续 generation_probe 行自然呈现「清单失败但探针通过」的链路。

### D5. 配置包加键兼容
导出每条 api_config 加 `skip_model_list` 键（不升 format_version），导入缺键默认 0——照抄 `api_format` 的 R11 先例。

## Risks / Trade-offs

- **真坏 Key 多一次探针调用**（D1 代价）：探针是一次性用户动作，判稳优先。
- **网关对 chat 也 403**：探针 auth_error 透传——语义正确（这配置确实不可用）。
- **skip 勾选但端点其实有清单**：用户自选的代价，随时可关；说明行写明。
- **前端联动点多**（Key blur／vendor 变更／fetch 按钮三处自动拉取入口都要以 skip 为闸）：收敛为单一 `canAutoFetch` 派生条件，vitest 钉死三入口。

## Migration Plan

无显式迁移代码：模型列带 `server_default`，新库由 create_all 自然具备；旧版库经指纹 mismatch 重命名＋带回链路迁入时，带回引擎列交集计划对缺失列以 DDL 默认值兜底（存量行默认关）。配置包导出/导入按 D5。存量配置行为零变化（默认关）。

## Open Questions

（无——401/403 降级、fetch_models 口径、跳过控件形态均已在 2026-10-16/17 对话拍板。）
