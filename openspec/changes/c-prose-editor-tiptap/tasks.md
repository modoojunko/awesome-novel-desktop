## 1. 依赖与骨架

- [ ] 1.1 装 `@tiptap/react`＋`@tiptap/pm`（3.x）；最小挂载验证 React 19 兼容（失败退 @tiptap/core 直挂方案）
- [ ] 1.2 ProsePane 换 TipTap 内核：schema 仅段落、`.editor` 宿主类与 contenteditable 属性经 editorOptions.attributes 保留、fs/lh 偏好类照挂、`.editor-wrap`/`.editor-status`/`.generating` 不动
- [ ] 1.3 版式迁移：段首缩进/680 版心/宋体段落 CSS 套到 ProseMirror 节点；空文档占位（placeholder 扩展或 CSS ::before）

## 2. 序列化与同步

- [ ] 2.1 `proseDoc.ts` 单源：`proseToDoc`/`docToProse`（NBSP 归一对齐 collectParagraphs；空段 `<br>` 占位口径）；配单测（多段/空段/全空格段/NBSP/空串）
- [ ] 2.2 外部 prose 同步：prose 指纹比对＋`setContent(emitUpdate:false)`；覆盖载章/归档恢复 reload/润色采纳/AI 完成四路径
- [ ] 2.3 粘贴归一：transformPasted/insertContent 纯文本化，多段落结构保留

## 3. AI 流式与选区

- [ ] 3.1 `startStream` 事务化：chunk 追加到文档末尾（SHALL NOT 整文档重建）＋history 分组 meta（整次流式＝一个撤销单元）
- [ ] 3.2 `finishStream`/停止/失败收尾照旧（setProse 外部同步一次、qcReport、onWriteProgress 不动）；流式期 `setEditable(false)`
- [ ] 3.3 `captureNow` 改 PM 选区换算（SelectionCapture 形状不变）；润色/扩写/压缩采纳替换走范围事务

## 4. 只读与两态

- [ ] 4.1 `setEditable` 接 `editing && !notEditable && !streaming`；`prose-edit` 两态顶行、锁定横幅、frontier/ghost 口径零改动
- [ ] 4.2 `handleInput`/`execCommand`/`proseToHtml`/`collectParagraphs` 旧层退役清理

## 5. 测试与门禁

- [ ] 5.1 vitest：序列化往返、两态/锁定 editable 矩阵、流式 mock（追加＋撤销单元）、粘贴归一；全量对拍 main 基线零新增失败
- [ ] 5.2 e2e：理论零适配（`.editor`/contenteditable 断言保留），隔离栈全量复跑；chapter-rewrite/free-writing-flow 重点回归
- [ ] 5.3 IME 手测清单：拼音组词期不被打断（等待/切窗/连续输入）、撤销/重做跨 AI 生成、Word/网页粘贴降级——结果记入 change 附录
- [ ] 5.4 tsc 零新增；打包体积对比记录（tiptap/pm 拆 chunk 不进首屏主包）
- [ ] 5.5 openspec validate --strict；specs 措辞与实现逐条对上
