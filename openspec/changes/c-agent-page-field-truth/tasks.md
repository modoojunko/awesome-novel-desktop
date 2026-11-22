# c-agent-page-field-truth Tasks

## 1. 真值读取与渲染（genres/service.py + context.py）

- [x] 1.1 genres/service.py 新增五格真值渲染函数（含未填点名；输入 resolve_genre_context 产物，None 视为全空），紧邻 build_genre_section；验证：单测全空/全填/部分填三态
- [x] 1.2 context.py 修 brief 题材行死代码（读 theme/sub_genre，None 跳过）；验证：brief 测试填/空两态＋键名回归钉
- [x] 1.3 context.py 新增 build_genre_panel_note(root_path, novel_id)（fail-soft，预算截断 ~400 字符）；验证：单测输出含五格点名

## 2. 注入与工具面（router.py + tools.py + caps/settings.py）

- [x] 2.1 router.py 加 _SET_PANEL_ZH，页签真值注入扩 set:* 分支（「设定·<面板名>」，未知回退「设定」）；验证：note 拼装测试 set:world/set:default 两态
- [x] 2.2 router.py set:genre 线程接 build_genre_panel_note（页签真值后、动态 brief 前，try/except fail-soft）；验证：note 拼装测试含字段真值；ch:og 线程不串味
- [x] 2.3 tools.py read_settings 加 genre/intro 分区＋enum/docstring 更新；验证：run_tool 直测现值/未填点名/简介空态
- [x] 2.4 caps/settings.py genre 白名单加 promise_note（标签「主要看什么」）；验证：写核 merge 测试＋白名单外 theme 拒绝

## 3. 测试锚点（tests/）

- [x] 3.1 test_assistant_router_helpers.py：brief 题材行两态＋键名回归
- [x] 3.2 test_genres_injection.py：五格真值渲染三态
- [x] 3.3 test_assistant_router_helpers.py：read_settings genre/intro 直测（run_tool 样板）
- [x] 3.4 test_agent_page_ops.py：promise_note 写核 merge＋theme 拒绝＋授权卡标签
- [x] 3.5 router note 拼装测试：set:genre 面板名＋字段真值、ch:og 不串味

## 4. 回归与验证

- [x] 4.1 定向 pytest（test_assistant_router_helpers / test_agent_page_ops / test_genres_injection / test_page_scopes / test_assistant_registry / test_assistant_genre_pick）＋ ruff 全绿；再后端全量——3450 passed / 330 skipped，ruff All checks passed
- [x] 4.2 确认零前端改动（git diff 仅 client/backend＋openspec），tsc 无涉
- [ ] 4.3 真机走查（独立栈）：题材页问「当前页面有几个问题」逐格作答；「把我刚说的写进主要看什么」授权卡转写成功；ch: 章纲页签问答无字段真值
- [ ] 4.4 openspec validate --strict 过；review-agent 无 findings 后合入
