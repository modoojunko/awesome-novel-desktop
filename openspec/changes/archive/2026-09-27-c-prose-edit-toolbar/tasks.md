## 1. 前端

- [x] 1.1 编辑框连体样式：编辑顶条（上圆角/无下边）＋ `.editor-wrap.editing`（下圆角/无上边）合成一个控件
- [x] 1.2 工具箱：撤销/重做图标按钮（真实 history 链路＋置灰态，useEditorState 订阅）
- [x] 1.3 顶条其余保持：正在编辑正文 · N 字 / 写完自动保存 / 完成

## 2. 测试与门禁

- [x] 2.1 vitest 全量绿；tsc 零新增；design:lint 无阻断
- [x] 2.2 e2e：helpers 断言工具栏在场；新增「撤销/重做按钮生效」用例；正文相关 spec 隔离栈复跑
- [x] 2.3 openspec validate --strict

## 实现偏差与顺带修复（记录）

- **格式按钮不做**（spec 已写死）：纯文本存储下加粗/斜体无法持久化（保存即丢，AI 提示词/预览/下载全吃纯文本）。真格式需另立「富文本存储」立项。
- **顺带封掉数据破坏路径**：TipTap `setContent` 默认入撤销史 → 开章后按撤销/⌘Z 会把上一章内容（或空文档）写回本章并自动保存。外部载入改走自建事务（`addToHistory:false` + `preventUpdate` + 光标回文首），载入不进历史；e2e「开章不入历史」用例钉住。
- 空章占位补 CSS 兜底（`.editor:empty::before` + `data-placeholder`）：Placeholder 扩展只管「一个空段落」，零段落空文档原先无占位。
