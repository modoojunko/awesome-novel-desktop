## Why

2026-11-22 真机走查：知识库还在用「源自：斩神」这种措辞标出处。这本书在这里是**写法案例**，不是内容来源——「源自」读起来像在承认内容抄自原书，合规口径不合适。改成「案例书：斩神」：同一本书作为案例出现，展示的数据和逻辑都不变。

## What Changes

- **只改出处标签文案**：知识库列表行、实例详情「出处」段、知识详情弹窗实例群、知识树抽屉的「源自：」→「案例书：」；知识详情弹窗条目级来源段标题「源自小说」→「案例书」。
- **原有逻辑一律不动**：书名与章号照旧展示、空值不渲染整行、条件判断、搜索、后端、DB、API 全部不改。
- **回归约束**：三个前端用例文件的出处断言同步改为「案例书：」，钉住文案不再回退到「源自」。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `knowledge-base`: MODIFIED「知识库浏览界面」——出处行标签改为「案例书」，SHALL NOT 再用「源自」措辞；来源书名与章号展示逻辑不变。

## Impact

- 前端：`client/frontend/src/pages/KnowledgeBasePage.tsx`（列表行/实例详情/知识详情两段）、`client/frontend/src/components/tools/KnowledgeTreePanel.tsx`（树抽屉实例行）。
- 测试：`knowledgeBaseCoverage`、`knowledgeBasePage`、`knowledgeTreePanel` 三个用例文件同步断言。
- 无后端、无 DB schema、无 API、无搜索行为变更；不影响撤回清理、版本对账与用户本机数据。
- 合规口径：界面指代来源书时统一用「案例书」，不出现「源自」措辞；原文摘句（用户本机拆书产物）维持既有「看原句」折叠展示，不在本改动范围。
