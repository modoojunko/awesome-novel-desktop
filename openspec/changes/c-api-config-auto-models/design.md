# Design — c-api-config-auto-models

## 上下文

- 探针 URL 构造已按接口格式统一（`connection.py _build_probe`），八家端点实勘吻合，无需动。
- 连接测试路径（`test_connection`）＝models GET ＋「你好」对话探针，会真实生成一次（计费）。自动拉清单若复用它，Key 一失焦就烧一次生成——不可接受，故新增**轻探针**。
- 创建后自动测试（`POST /api-configs/{id}/test`）本就把清单落库，书内面板数据源不动；本改只补表单这一段。

## 决策

### D1 轻探针独立于连接测试（新增 `fetch_models`，不改 `test_connection`）

复用 `_build_probe` 的 endpoint/headers/extractor，只走 GET 分支：
- 200 且 API JSON → `{ok, status:"ok", models}`；
- 200 非 API JSON → `endpoint_mismatch`（沿用 `_non_api_response` 文案，提前暴露填错网址）；
- anthropic 格式 404 → `{ok:true, models:[], candidates, note:NO_MODEL_LIST_NOTE}`（**不发**降级生成探针——这是与 `test_connection` 的关键差异）；
- 401/403/429/5xx/网络错误 → 与测试路径同口径的失败信封。
- Key 为空且非 ollama → `auth_error`（同测试路径前置校验）。

### D2 新端点 `POST /api-configs/fetch-models`（raw、未保存态）

- body＝`FetchModelsBody{vendor_id, base_url, api_key, api_format}`（`TestRawBody` 去 `model` 的姊妹体）；鉴权同 test-connection（登录态）。
- 选 raw 而非「先建后拉」：拉取发生在保存前，配置尚不存在。

### D3 触发时机（前端）

- Key 输入框 `onBlur` 且值非空 → 拉取；Ollama（免 Key）→ vendor 选定/Base URL 失焦即拉。
- vendor/Base URL/接口格式变化且 Key 已填 → 重拉（防抖，在途请求按「最后一次参数」去重：参数相同的在途请求直接复用，不同参数的取消旧响应采用新响应——用请求序号丢弃过期响应即可，不强求 AbortController）。
- 拉取失败不阻塞、不重试轰炸：显示 warn 提示＋「重新拉取」动词出口。

### D4 默认选中规则（拍板：默认选第一个，与 10-05 登记默认值调和）

清单到位后：`登记默认模型 ∈ 清单 → 选中它；否则选中清单首项`。登记默认模型目前仅 DeepSeek（`deepseek-v4-pro`），与「默认选第一个」仅在 DeepSeek 一家分歧，保登记值（10-05 拍板的推荐默认权重更高）。用户手动改选后，后续清单刷新不覆盖手选值。

### D5 选择器形态：组合框＋`.mp-*` 弹层（2026-10-07 评审整改后实况）

- **交付形态＝组合框**：`#cfModel` 保持可编辑输入框（存量测试/e2e 契约不破），输入即搜索（`aria-autocomplete=list`）；弹层 `.mp-panel`（`role=listbox`，条目 `role=option`＋id＋`aria-activedescendant`＋`tabIndex=-1`），键盘 ↑↓/Enter 选中/Esc 收起（Home/End 未做；IME 组合期按键放行给输入法）。设计稿期的「选中值按钮＋.sel-panel/.sel-search」方案（复用 GenreSettingForm）在实现时改为组合框——`.sel-*` 样式锁在 `.settings-v` 作用域、Modal 内不可复用，且输入框兼任搜索消掉了一个冗余控件。
- **弹层 portal 到 body＋fixed 锚定输入框矩形**（评审 P1：Modal `.mcard` overflow-y:auto 会裁剪卡内绝对定位浮层——GenreSettingForm 的「就地展开」与 Modal 自身 portal 是同坑先例）；随滚动/resize 重锚、近视口底缘向上翻转。
- **关闭机制**：外点＝document pointerdown 落在输入框/弹层之外即收起；弹层内部 mousedown 整体 preventDefault（滚动条/说明区拖点不抢焦点不误关）；Esc 只收弹层（stopPropagation，防 Modal 的 window Esc 把整窗关掉）。
- 手填出口常驻：清单非空时输入框本身就是手填（清单外 id 合法——部分端点 /models 与可调用模型不同步）；清单为空/拉取失败时为主入口。
- `candidates` chips（DeepSeek/无清单端点）展示在弹层顶部，点击即选。
- 原型 `model-config.html` 演示同一交互（原型的弹层在自身页内绝对定位，无 Modal 裁剪问题；差异已在此登记，不追 portal）。

### D6 落库归一化补齐（service）

`test_api_config` 自动落库前过 `_normalize_models(raw, truncate=True)`：与手动路径同款去空白/去重保序，超 100 **截断**（手动 PUT 仍 422 报错——那是用户显式行为；自动路径截断静默保平安）。抽 `_normalize_models(raw: list[str], *, truncate: bool = False)` 单源两用。

### D7 候选表刷新（有据才登记）

官方文档（api-docs.deepseek.com/api/list-models，2026-10-07 实勘）现返回 `deepseek-flash`（V4.1-Flash）、`deepseek-v4-pro`；`deepseek-v4-flash` 已不存在。`VENDOR_MODEL_CANDIDATES.deepseek` 更新为 `["deepseek-flash", "deepseek-v4-pro"]`，vision 实验版无据撤下。前端 `VENDOR_DEFAULTS` 的默认模型 `deepseek-v4-pro` 仍在册，不动。

## 权衡与非目标

- **不复用 test-connection 做自动拉取**：生成探针计费＋慢；轻探针零成本。代价＝多一个端点，可接受。
- **不做「点开弹层再拉」**：Key 失焦时点已经拉过；弹层打开只读已有清单（带「重新拉取」）。减一次重复网络往返。
- **编辑态不加模型字段**：卡片「测试连接」已能刷新清单落库，编辑弹窗保持最小。
- **书内 ModelSettingForm 不动**：长清单搜索是后续优化（数据源已是全量清单）。
- **`refresh-models` stub 不动**：死代码，不在本改清偿范围。

## 风险

- ~~弹层嵌在 Modal 内：绝对定位面板的溢出裁剪需实测~~ → **评审实锤并已修**：`.mcard` overflow 裁剪卡内浮层（长清单必现），弹层已 portal 到 body＋fixed 锚定（见 D5）。
- design-parity 门禁：原型 `model-config.html` 同批补选择器，否则 0.002 差异红线。
- e2e `config-page.spec.ts` ④ 钉了 `#cfModel` 与 POST body：选择器保留 `#cfModel` id（组合框输入框承载），POST body 断言语义不变（默认选中＝预填值）。
