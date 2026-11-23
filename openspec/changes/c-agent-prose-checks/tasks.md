## 1. 后端工具

- [x] 1.1 `ToolContext.page_prose` 字段（只进工具上下文，不进提示词）
- [x] 1.2 `_read_prose_checks` 实现：人味现算（`check_prose`）＋朱雀读档（`get_stored_result`），正文源优先级（屏上文本仅限 focus_ref 章）、过期档不出原句、2000 字明细预算
- [x] 1.3 注册表条目：`kind=read`／`risk_level=low`／`feature_key` 空／`chapter_ref` 可缺省
- [x] 1.4 `scopes.py`：`ch:prose`＋`ch:style` 挂载；正文纪律补按需查一句

## 2. 页面态上行

- [x] 2.1 `router.py`：`page_state.prose_text` 解析（str、≤50000 字）→ `_stream_chat` → `ToolContext`
- [x] 2.2 `ProseHandle.getProse()`（`docToProse(editor.getJSON())`）
- [x] 2.3 `NovelWorkspace`：章视图下把稳定 getter 传给 Aui2Dock
- [x] 2.4 `Aui2Dock`：发送时刻取值，`page_state.prose_text` 非空才带；onSubmit 依赖更新
- [x] 2.5 `lib/chatApi.ts`：`page_state` 类型扩展

## 3. 测试

- [x] 3.1 `tests/test_assistant_prose_checks.py`：正文源优先级/跨章保护/未保存标注/人味格式化/朱雀新鲜·过期·无档·读失败/预算截断/缺参
- [x] 3.2 `test_page_scopes.py` 目录断言（`tools_for_thread` 含新工具，非正文域不含）
- [x] 3.3 `Aui2Dock.test.tsx`：`page_state.prose_text` 上行时效与省略两用例
- [x] 3.4 HTTP 级钉：`page_state.prose_text` 落进 ToolContext、不进提示词（`test_assistant_chat_stream_http`）
- [x] 3.5 全量回归（后端 assistant 套 318 绿＋前端全量 2337 绿＋tsc 零错）

## 4. 收尾

- [ ] 4.1 真机走查（装包另批）：未保存正文问「人味检测标红的行你看得见么」→ 助手调工具并报出与屏上一致的行＋原句＋改法
- [ ] 4.2 归档本变更（随 PR）
