## 1. 出处标签改文案

- [x] 1.1 `KnowledgeBasePage` 列表行「源自：书名 · 章号」→「案例书：书名 · 章号」（书名/章号与按值渲染逻辑不动）——验证：定向 vitest 断言案例书标签
- [x] 1.2 `KnowledgeBasePage` 实例详情「出处」段、知识详情弹窗实例群同改；条目级来源段标题「源自小说」→「案例书」——验证：抽屉/弹窗用例同步
- [x] 1.3 `KnowledgeTreePanel` 树抽屉实例行同改——验证：树面板用例断言案例书标签
- [x] 1.4 搜索、DB、API 零改动；后端仅同步一处口径注释（`deconstruct_import.py`，无逻辑改动）——验证：`git diff` 无逻辑变更

## 2. 门禁

- [x] 2.1 前端 `tsc --noEmit`＋全量 vitest/coverage＋`npm run build`＋`openspec validate c-kb-case-book-label --strict` 通过
- [x] 2.2 `review-agent` 审 diff，findings 修完再合。证据：No findings（仅标签文案，逻辑零改动）
- [ ] 2.3 建 PR（待 boss 点头），CI 双绿 squash 合 main，清 worktree/分支
