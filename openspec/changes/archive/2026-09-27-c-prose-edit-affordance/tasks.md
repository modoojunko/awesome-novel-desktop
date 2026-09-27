## 1. 前端

- [ ] 1.1 ProsePane：编辑态顶条（正在编辑正文 · N 字 ＋ 写完自动保存 ＋ 完成）；查看态顶条不变
- [ ] 1.2 编辑区可视化：`.editor-wrap.editing` 面板底色＋细边（--surface/--border）
- [ ] 1.3 进编辑态聚焦且光标落文末（focus → focus("end")）；hint/文案定稿

## 2. 测试与门禁

- [ ] 2.1 vitest 全量绿；tsc 零新增；design:lint 无阻断
- [ ] 2.2 e2e：helpers 进编辑态后断言编辑顶条（prose-done 在场）；重点 spec 隔离栈复跑
- [ ] 2.3 openspec validate --strict
