# c-chapter-tab-scroll：章工作台内容页签列内滚动——伏笔台账超高被裁不可达（#586）

## Why
用户反馈（09-29）：章工作台「伏笔」页签伏笔数量多时，超出页面的内容无法滚动查看。根因：书工作台外层 `.wb` 封顶视口且 `overflow:hidden`，滚动依赖各页签容器自滚——章纲页签正常（`.og-pane` 自带 `flex:1; min-height:0; overflow-y:auto`），而伏笔页签容器 `.hooks-wrap` 自 #398 引入起只有 padding、无滚动声明，内容超高即被 `.wb` 裁掉不可达。同样的结构性缺陷存在于全部五个内容页签（设定/文风/角色关系/操作/伏笔）。

## What Changes（#586=1eb6e4e4，squash 上 main=b5eb65bb）
- 在 c-workbench-col-rhythm（#449）引入的内容型面板单源规则（同一选择器组，book.css:1432）统一补上 `.og-pane` 口径的列内滚动契约 `flex:1; min-height:0; overflow-y:auto`——一处修复，五个内容页签（`.settings-pane`/`.style-pane`/`.relations-pane`/`.actions-pane`/`.hooks-wrap`）一并遵守
- 评审（review-agent 两轮）零 finding：#585 关系图滚轮缩放已 `preventDefault` 且自带固定视口、五个页签类名全仓单点消费、页签子组件无内层裁切、portal 弹窗不受影响、短内容布局零变化；e2e 全仓唯一 `toBeInViewport` 断言在 settings-v 作用域不涉本改动
- specs：workbench「中栏节奏单源（内容衬垫与版心）」Requirement 增补「列内滚动」条款＋新 Scenario「超高页签内容可滚动到达」（随本归档 PR 同步，#586 实现为纯 CSS 未带 spec）

## Capabilities
- workbench（MODIFIED：中栏节奏单源——增补列内滚动契约）

## Impact
纯 CSS 一处（book.css +5/−2），docs-only 归档件。门禁：真实 book.css 还原工作台 DOM 链 A/B 实测（40 条伏笔：修复后页签内滚动正常、页面整体不滚；回退声明即复现原始 bug）＋NovelWorkspace/workbenchExtras vitest 25 绿（基于 #584/#585 后 main）＋design:lint 通过。CI 基建秒挂（steps=[] 签名）按先例 admin 合入；main 补验待 Actions 恢复。
