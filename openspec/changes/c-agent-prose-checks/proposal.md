## Why

真机实测（2026-11-22）：正文页人味检测标出问题行，作家问助手「你能看到这些问题行么」，助手只能读章纲/正文/设定，检测结果够不着——只能请作家把标红的行贴过来。

根因两条：人味检测是本地现算（`write/renwei_check.py`），findings 只活在 ProsePane 内存态，后端没有读取口；朱雀检测结果虽在 `zhuque_results` 表持久化、有现成零额度读档，但助手也没有对应工具。另有口径缺口：屏上标注是按编辑器当前文本（可能未保存）算的，后端只读已保存正文会在主场景（生成后未保存）算不出同一批行。

## What Changes

- 新增后端只读工具 `read_prose_checks`：人味检测现算（段号/原句/为什么/改法）＋朱雀检测存档（判 AI/疑似的段、结果是否过期）；`chapter_ref` 可缺省＝当前章；只挂 `ch:prose`/`ch:style` 两域。
- 聊天请求 `page_state` 增加 `prose_text`（屏上正文全文，发送时刻读取）：只进 ToolContext（工具现算用），**绝不进提示词**；跨章问别章时工具回落已保存正文，不拿屏上文本冒充。
- 朱雀存档过期（正文指纹不一致）只给段号/级别不给原句（段号可能对不上，防按错句改），提示重检。
- 不做窄正则 prime（boss 拍板 2026-11-19）；触发条件写进工具描述与正文纪律。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assistant-tools`: 新增「正文检测问题行按需查询」要求（工具契约、正文源优先级、朱雀过期口径、预算、域）。
- `assistant-chat-ui`: 页面态上行扩展——`page_state` 可携带屏上正文文本，仅供工具上下文。

## Impact

- 后端：`assistant/tools.py`（`ToolContext.page_prose`＋工具实现/注册）、`assistant/router.py`（`page_state.prose_text` 解析→ToolContext）、`assistant/scopes.py`（域挂载＋正文纪律）。
- 前端：`ProsePane.tsx`（`ProseHandle.getProse`）、`NovelWorkspace.tsx`（章视图 getter 透传）、`Aui2Dock.tsx`（`page_state.prose_text` 上行）、`lib/chatApi.ts`（类型）。
- 测试：后端工具单测＋Aui2Dock 契约用例；注册表/域不变量自动覆盖。
- 不动：检测端点、标注持久化、提示词模板。
