## 1. 前端页面态随行

- [x] 1.1 `chatApi` page_state 类型加 `panel`/`chapter_tab`；`Aui2Dock` 从 `scopeRef` 组请求体（仅设定页带 panel、章内页带 chapter_tab）——验证：请求体单测
- [x] 1.2 保留 unsaved 现有行为；无 panel/chapter_tab/unsaved 时不发 page_state——验证：普通工作台请求体零变化

## 2. 后端页面字段上下文

- [x] 2.1 新增 `assistant/page_context.py`：面板→字段/值装配（题材 01-05、简介、世界八格、主线、文风、角色/伏笔摘要），值裁短＋总预算 800，失败 fail-soft——验证：纯函数/面板单测
- [x] 2.2 `router` 解析 `page_state.panel/chapter_tab`，拼进 L2 note（当轮 user 尾，不落库）——验证：HTTP 级 user_input 断言
- [x] 2.3 未知面板/读失败只报面板名或空串，不打断 SSE——验证：异常面板不抛错

## 3. 门禁

- [x] 3.1 后端定向＋全量 pytest、ruff；前端 tsc/vitest/coverage/build；`openspec validate --strict`；design:lint 本改动零违规
- [x] 3.2 合前 `review-agent` 审 diff，findings 修完再合。证据：No findings；真机 smoke 已验证字段指代
- [ ] 3.3 建 PR，CI 双绿 squash 合 main，清 worktree/分支

## 4. 发版与本地

- [ ] 4.1 合入后打 `v0.49.2` 补丁 tag（0.49.1 已发灰度），跑打包/灰度验收
- [ ] 4.2 本地装 0.49.2 并从 0.49.1 迁入数据；在题材页说「这个/这格」走查上下文
