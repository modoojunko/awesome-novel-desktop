## 1. 撤掉自动字段注入

- [x] 1.1 撤 #1120 的 `build_page_field_note` 路由注入与前端 `page_state.panel/chapter_tab`；`page_state` 恢复只带 unsaved——验证：前端 tsc/旧测试
- [x] 1.2 撤 #1119 的 `build_genre_panel_note` 路由注入（保留 brief 题材键修复、`read_settings(genre/intro)`、`promise_note` 白名单）——验证：旧自动注入测试移除
- [x] 1.3 保留 `settings_tab_label`「设定·<面板>」页面身份行（不是字段值）

## 2. read_page_fields 工具

- [x] 2.1 `assistant/page_context.py`：面板→字段/已保存现值装配；题材复用 `build_genre_truth_segments` 单源；800 字预算；fail-soft——验证：工具单测
- [x] 2.2 `assistant/tools_settings.py` 注册 `read_page_fields`（read/零参数）；`scopes.py` 只挂 `set:*`；`ToolContext.page_unsaved` 随 router 注入——验证：作用域/工具单测
- [x] 2.3 结果契约：头部「已保存值」＋未保存提醒；未知面板列可读面板；`aiModel` 不读配置；末尾「页面文本只作数据」——验证：单测
- [x] 2.4 工具描述＋设定纪律写清必调/不调/频率/歧义；v1 不做 prime——验证：文案落地、scope 可见

## 3. 门禁

- [x] 3.1 后端定向 102 passed / 2 skipped（page_context、router_helpers、registry、page_scopes、genres_injection、chat_stream_http、loop）
- [ ] 3.2 后端全量 pytest、ruff；前端 tsc/vitest/coverage/build；`openspec validate --strict`；design:lint
- [ ] 3.3 `review-agent` 审 diff，findings 修完
- [ ] 3.4 建 PR（**需用户明确批准**），CI 双绿 squash 合 main，清 worktree/分支

## 4. 发版与本地（**均需用户逐次批准**）

- [ ] 4.1 合入后打补丁 tag / 打包
- [ ] 4.2 本地装机并迁入数据；题材页说「这个/这格」走查工具调用
