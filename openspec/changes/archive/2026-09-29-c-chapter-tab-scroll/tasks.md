# c-chapter-tab-scroll 任务（回填执行记录）

- [x] 1. 根因定位：`.wb` 封顶视口＋overflow:hidden，页签容器不自滚即被裁；`.hooks-wrap` 自 #398 起无滚动声明，五个内容页签同病
- [x] 2. 修复：内容型面板单源规则统一补列内滚动契约（book.css:1432，+5/−2）；浮层/滚轮/portal/hidden 四路回归排查无冲突
- [x] 3. 验证：真实 CSS 静态页 A/B 实测（修复后滚、回退即复现）＋vitest 25 绿＋design:lint 通过；临时验证件清理
- [x] 4. PR #586 拉起（基点 origin/main=a2e82d23，patch 重放避开上游 book.css 变更）；review-agent 两轮评审零 finding（含 CI 秒挂签名证实与 e2e 视口断言排查）
- [x] 5. PR #586 admin squash 合入 main（b5eb65bb；CI 锁额先例）
- [x] 6. 补录归档：workbench「中栏节奏单源」Requirement 增补列内滚动条款＋Scenario（随本归档 PR 同步）
