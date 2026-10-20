# Design — c-modelconfig-gemini-go

## Context

- 前端供应商选择区现状：`ApiConfigForm.tsx` 用 `.vgrid` 平铺 `ProviderIcon.tsx` 的 VENDORS（8 家）；登记表在 `vendorDefaults.ts`（键＝供应商×接口格式）；格式锁在 `ProviderIcon.tsx` 的 `VENDOR_FORMAT_LOCK`；后端 `api_configs/vendor.py` KNOWN_VENDORS 做 base_url 识别与展示名。
- 调用链现状：`ai_client.py` 双 SDK（AsyncOpenAI/AsyncAnthropic）按 `api_format` 分路；openai base 经 `normalize_openai_base` 段锚归一（Gemini 兼容层 `/v1beta/openai` 中段形态已有钉，`test_api_format.py`）；思考参数按「思考参数可配」契约下发（GLM 形态 `thinking`＋`reasoning_effort` 三档 low/high/max）。
- 设计稿：`docs/design-c/drafts/ai-novel-c端-模型配置-Gemini与OpenCodeGo-原型.html`（已过审，tab 方案），抓取资产 `modelconfig-captures/`。

## Goals / Non-Goals

- Goals：tab 分组两页；三条登记；锁定矩阵扩展；compat 引导收窄；opencode 会话头/UA 自动附加；Gemini 思考档位换算；真机验证三件（见 Risks）。
- Non-Goals：不实现 OpenCode Go 的 Gemini（Google 原生协议）与 GPT/Grok 系（Responses 协议）——原型「待排期」角标仅表达意图；不新增 SDK 依赖；不改探测降级链路（zen 提供模型清单，走既有 models 探测）；不动 ai-client 的超时/首字守卫/剥思考行为（对两供应商照常生效）。

## Decisions

1. **tab 用真实 `.seg` 组件类实现**（设计稿口径）：供应商字段内 `.vgrid` 上方插一段两键 seg（官方厂商｜中转 · 订阅制），不新建组件词汇、不加令牌 → 不触碰共享段、免 design-cross。备选的分组标题行方案（原分组稿）已被用户否决（要滚找）。
2. **页签切换不清已选**（spec 口径）：切页仅重渲染方块集，已选供应商与表单内容保持。过审原型在空表单上演示未覆盖此细节，实现按 spec 的「不清已选」落地，属原型未定义行为的补全，登记 ADJUSTMENTS 说明。
3. **三条登记全部「模型留空＋候选清单」**：Gemini 与两 Go 方块均无单一默认模型可钉（Go 模型清单随订阅调整），登记纪律「无据留空」；候选清单走既有 VENDOR_MODEL_CANDIDATES（后端）＋登记表候选（前端），两处同源对齐（既有纪律）。Gemini 候选取官方模型页在售型号；Go 候选取官方 docs/go 清单的对应协议族。
4. **会话标识取「base_url＋api_key 摘要」单源**：`AIClient` 不持有配置 id（`__init__` 只有 key/base/model/format，按 id 缓存需全调用链穿参），故以 `sha256(base_url|api_key)` 截断十六进制作为会话标识——同一配置进程内稳定、重启更换、零穿参。备选的「每次生成一个新 id」会让网关侧会话亲和/prompt 缓存失效，「config id 穿参」成本高无增益。头仅在主机命中 opencode.ai（含子域）时附加，与 ZCode 的 `isOpenCodeGoBaseUrl` 门同构；注入点两处同口径——`ai_client` 的 SDK default_headers 与 `connection.py` 探针的 `_build_probe` headers（探针是自建 httpx 请求）。
5. **UA 在 httpx 客户端构造处统一改**：`_init_client` 两侧 SDK 均支持 `default_headers`/UA 覆盖；仅当 base 命中 opencode 时整体替换 UA 为 `ai-novel/<版本>`（版本取现有 build_info）。非 opencode 供应商维持 SDK 默认（不惊动存量探针判例）。
6. **Gemini 思考换算收敛在 `_thinking_params` 出口**：供应商为 gemini 时档位映射 low→low、high→high、max→high；关思考改发 `reasoning_effort` 关闭语义（兼容层接受 none），不再发 GLM 形态 `thinking:{type:disabled}`（兼容层静默忽略、形同虚设）。探针 400 去参重试逻辑对 Gemini 天然不触发（兼容层对未知参数静默忽略、对 reasoning_effort 均接受），无需改动。
7. **中转页一期只上三块**（OpenAI 兼容＋Go 两方块）：待排期方块不渲染（spec SHALL NOT），避免「点了没反应」的死钮。
8. **vendor 身份链单源——前端方块 id＝KNOWN_VENDORS 键＝落库 vendor**（`gemini`／`opencode-go-chat`／`opencode-go-claude`）：后端 create/update 存的是 `resolve_vendor(base_url)` 检测值而非请求体（`service.py:116-136,285-292`），且 schema 白名单逐字校验请求体（`schemas.py:58-63`，键集即 KNOWN_VENDORS）；两个 Go 方块同主机，KNOWN_VENDORS 须用主机＋路径差异化模式区分并按「/v1 在前」登记防遮蔽。备选「存请求体 vendor_id」改存储语义风险大；备选「通用 opencode 键」会让两方块落同一 id 且前端枚举/编辑回显失配。

## Risks / Trade-offs

- [调用适配落在生成（ai_client）与探针（connection.py 自建 httpx）两处，后续改动易只改一边造成行为分叉] → 任务 4.3/4.4 显式列两文件＋单测断言「探针/生成同参同头」；评审口径把两文件当一个改动面。
- [OpenCode 服务面向编程代理流量，写作画像有封限风险] → 已在 proposal 风险记录并由作家拍板自担；实现侧不做任何流量伪装（仅按官方要求自报身份），降量使用建议写入用户文档（随 tasks 可选项）。
- [zen 网关 anthropic 链路的 `/v1/messages` 拼接形态未实测] → 真机验证单第一项：Go · Claude 系保存后探针须命中 `POST /zen/go/v1/messages`；若网关仅认 `/zen/go` 前缀的旧形态再调整登记（登记表单源可改）。
- [Gemini 兼容层对 `response_format: json_object` 是否等效映射未知（静默忽略风险）] → 真机验证单第二项：拆书/例句链路用 Gemini 配置跑一次，判据＝产出合法 JSON（不能只看无报错）；不支持则该能力对 Gemini 降级为 prompt 约定（既有 anthropic 同款兜底口径）。
- [思考档位换算后「深 max」语义静默降档] → 表单提示文案（过审原型已含「Pro 系始终思考」句）+ 换算只发生在 gemini 供应商，其他厂商不受影响；不做运行时提示（避免打扰）。
- [tab 化后编辑弹窗（`vfix` 固定供应商态）与新 tab 的关系] → 编辑态不渲染供应商选择区（现状即如此），tab 仅存在于创建态，无交互冲突。

## Migration Plan

纯增量：登记表加键、枚举加值、调用层按主机条件附加头。无数据迁移、无存量配置影响（老配置 base_url 不命中新逻辑）。回滚＝revert 提交即可，无落库格式变化。

## Open Questions

无——spec/方案级疑问已在原型评审与调研会话拍板；剩余未知全部是真机可验项（见 Risks，已排进 tasks 验证任务，不阻塞编码）。
