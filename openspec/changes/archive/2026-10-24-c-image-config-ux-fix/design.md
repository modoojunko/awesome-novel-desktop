# Design: c-image-config-ux-fix

## Context

- 配置表单（`ImageConfigPanel.tsx` ConfigForm）现有「默认模型」单行输入与「模型清单」textarea 两格，`pickProvider` 把两格预填成同一供应商预设值；后端 `image_assets/service.py` 的 create/update 原样落两字段，不校验一致性。
- 两字段的真实消费面：`default_model` 是生成链唯一兜底（`service.py:800`，本书未绑定 `image_model` 时使用）；`models` 清单在前端仅剩配置卡片 chips 展示，无任何功能消费方；书级 `image_model` 绑定有后端端点但工坊 UI 只读展示，无设置入口。
- `image_configs` 表已预留 `last_test_status / last_test_error / last_tested_at` 三列（换供应商时被清空），无任何端点写它们；`/image-configs` 路由只有 CRUD＋restore。
- 生成链（`generation.py`）已有六家适配器（volcengine/aliyun/zhipu/openai/minimax/openai-compat）、递归收敛 b64/url 的响应解析与错误分类；生成/试画/批量端点挂 `ai_feature("image-generate") + require_tier_access`，属 KEYLESS_GATE_KEYS（不要求配置写作大模型）。
- 供应商预设住在前端 `imageApi.ts` `IMAGE_PROVIDERS`（后端 `PROVIDERS` 只是合法 id 集合，无预设）；火山预设 `doubao-seedream-4-0-250828` 过时，设计说明（`docs/design-c/drafts/ai-novel-c端-封面与角色头像-设计说明.md`）登记的火山 id 清单为 `4-0-250828 / 4-5-251128 / 5-0-260128`。

## Goals / Non-Goals

**Goals:**

- 表单单模型收敛：一个「模型」格进，`default_model` ＋派生清单出；API 对显式清单保持向后兼容。
- 「测试连接」端到端可用：表单保存前后都能测，结果落预留三列并在表单即时呈现，失败原因可读。
- 火山预设刷到 Seedream 5.0 系。
- 原型先行（model-config.html）＋ADJUSTMENTS 登记，实现与其对拍。

**Non-Goals:**

- 不做「拉取模型清单」（各家 models 端点形状不一；有了试画其价值消失）。
- 不做书级 `image_model` 绑定的设置 UI（另一条线）。
- 不动 c-image-generation 的生成/批量/权益 Requirement；不改 S端；不碰共享段。

## Decisions

1. **单端点 `POST /api/image-configs/test`，body 可选 `config_id`**（而非 `{id}/test` 路由）：新建态（无 id）也要能测——body 带 `provider/base_url/default_model`＋明文 `api_key`；编辑态带 `config_id` 且 `api_key` 留空 → 取存量 Key，其余字段缺省用存量值；`config_id` 与非空 `api_key` 同时出现时以 body 为准（与 update 的显式覆盖同口径）。响应 `{ok, model?, elapsed_ms, error?}`。带 `config_id` 时持久化 last_test_* 三列；纯探测不写库。备选 `{id}/test`＋新建先保存再测——被否：迫使作家先存一份可能错的配置才能测，流失败现场。
2. **测试＝真实最小试画**（复用 generation.py 适配器链），不是 `GET /models` 探活：models 端点各家形状不一且不验证图像权限/模型名拼写；试画端到端，正好兼作六家真实响应形状（c-image-generation tasks 4.2）的验证手段。试画参数：kind 取 avatar 档——尺寸由 `_native_size` 按 provider+kind 固定（无自由档，阿里云 avatar 档为 2048*2048 全尺寸，费用预期按家写实，不止几分钱级）、固定极简 prompt、n=1；拿到可解析的 url/b64 即成功，**不落资产**（适配器对 URL 回包会下载校验后即弃，复用整链这是既有行为，不为其开旁路）。端点内 `asyncio.wait_for` 施加约 75s deadline（独立于适配器 300s 读超时），超时按失败归类、last_test_error 落可读摘要——否则弹窗「测试中」会转圈到 5 分钟。
3. **权益门与节流**：测试端点挂 `ai_feature("image-generate") + require_tier_access`（与生成同门，旧权益快照隐式放行语义按 `__ai_feature__` 自动继承）；试画消耗供应商额度，免费用户不得借测试白嫖生成。同用户节流约 30s 一次——生成链无频次机制可复用，用 module-global dict（部署已核实单进程：Dockerfile 无 `--workers`、打包 uvicorn 单进程；先例 `_LAST_ENT_RESYNC`），并留测试重置缝（对齐 `stop_dispatcher` 的测试出口形态）。
4. **models 派生放后端**：create/update 中「请求未显式携带 `models` → 落 `[default_model]`」。显式性判定不能靠 `"models" in data`：create 端点 `body.model_dump()` 会把字段默认值 `[]` 带进 data，键永远在场——create 以 `model_fields_set` 判显式（先例 cover_seed），且显式空数组亦按派生处理（防旧客户端发空数组顶掉派生）；显式非空清单（备份 importer 走直写 DB，不经此层）原样尊重。`default_model` 为空时派生为 `[]` 不落 `[""]`。派生不做在纯前端——后端是数据唯一写入方。旧配置多模型清单在下次保存时自然收敛，无功能损失。
5. **火山预设**：`IMAGE_PROVIDERS` volcengine `models` 改为 `["doubao-seedream-5-0-260128", "doubao-seedream-4-5-251128", "doubao-seedream-4-0-250828"]`，预填取首个（5.0）；作家可自由改任意 id（如 flash 变体）。其余五家无新证据不动。
6. **卡片改版**：配置卡以「模型：{default_model}」mono 行替代 chips 列表（chips 的数据源 models 派生后语义坍缩）；测试状态以 `.b` 胶囊呈现在卡头（ok/err 语气，随 list 返回的 last_test_status 渲染）。已核实 `config_to_dict` 输出三字段、`ImageConfig` 前端接口需补 `last_test_error/last_tested_at`。已知取舍：新建态测试通过→保存后 create 会重置三列，卡片显示「未测试」——行为自洽，文案在 ADJUSTMENTS 登记说明。

## Risks / Trade-offs

- 试画有真实费用（一次最小图，几分钱级）→ 权益门＋节流兜底；错误提示文案告知作家「测试会真实生成一张小图」。
- 旧配置显式多模型清单被下次保存收敛 → 当前无消费方，接受；显式请求路径（备份/导入）不受影响。
- 六家真实响应形状仍未真机验证，测试端点自身可能按家踩坑 → 适配器解析已有测试桩兜底；真机抽检任务显式列出六家。
- 测试失败不该阻止保存（配置可以先存后修）→ spec 已钉「保存不被测试失败阻止」。
