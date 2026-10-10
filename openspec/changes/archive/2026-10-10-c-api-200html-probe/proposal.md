# c-api-200html-probe

## Why

内测反馈 #1 逐条核对后的残余缺口（issue #781）：用户用 ccswitch 类中转站
（网关对未知路径回 200 网页、真实生成接口正常）配 Key，在「添加配置」表单报
「请检查 Base URL 是否填成了网站地址」——但该配置在生成链路上完全可用。

根因：探测链路的「200 体判废」是**终局裁定**——`client/backend/api_configs/connection.py`
的 `test_connection` 对 models 端点 200 非 API JSON 体（`_non_api_response` 判废）
直接返回 `endpoint_mismatch`；只有 HTTP 404 才降级探对话接口。真网页站与
「models 路径回网页的可用网关」在 200 体形态上同形，旧实现一律按前者处置。

## What Changes

- `test_connection`：models 端点 200 体判废（网页体/软错误信封）时**也降级**为
  最小生成探针（与 404 降级同一路径）——
  - 探通（收到格式正确且含可见回复文本的回复）→ 放行：按「无清单端点」口径返回
    `{ok, models: [], candidates, note}`（该端点不提供清单，手填/候选 id 兜底）；
  - 探不通（真网页站的对话接口也 HTML/不存在）→ **保留判废原文案**
    （「该地址返回的不是 API 数据…看起来像网页。请检查 Base URL…」），
    SHALL NOT 用探针文案顶替；
  - 探针 id 同 404 口径：已选模型（表单手填初值）> 该 vendor 候选 id 首个 >
    （仅 anthropic）占位 id；无 id 的 openai 格式不降级（无 id 的生成探针必然
    无意义），保留原文案。
- `test_connection` 的 404 降级与 200 体判废降级收敛到同一 helper
  `_fallback_probe`（行为守恒，零语义变化）。
- 只拉清单轻探针（`fetch_models`）**零生成调用语义不变**：其 200 体判废仍按失败
  报「不是 API 数据」（`FetchModelsBody` 无 model 字段，轻探针没有「探针优先模型」
  概念，也无从降级；与 openai 404 不降级的既有口径同源）。
- 留痕不变：models_list 行如实记体判废分类（该行描述 models 请求自身结果，
  与 404→not_found＋probe 行同构），最终裁定由 generation_probe 行承载。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `model-api-config`：Requirement「按接口格式探测连接」——200 体判废从终局裁定
  改为先降级探对话接口、探不通才判失败；Scenario「网页地址不算通」判据随之细化，
  新增「200 网页体降级探对话接口」场景。

## Impact

- 代码：`client/backend/api_configs/connection.py`（`test_connection` 的 not_api
  分支＋新增 `_fallback_probe` helper；`fetch_models` 不动）。
- 测试：`client/backend/tests/test_api_format.py` 新增 3 条（200-HTML 降级成功 /
  降级失败保留原文案 / 软错误信封同分支降级）＋网页体无 id 不降级断言加固。
- 用户面：ccswitch 类网关用户「测试连接」不再误报「请检查 Base URL」；真网页站
  仍被判失败并给原文案（早期暴露能力不退化）。表单「自动拉清单」失败提示保持
  原语义（轻探针不发生成请求，判废即报错）——该路径的兜底＝手填模型名后
  「测试连接」，本改动使这条兜底真正可用。
- 零 UI、零共享段、零前端文件（无 Design Impact 段即判定依据）。
