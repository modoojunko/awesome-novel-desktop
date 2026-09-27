## 1. 依赖与骨架

- [x] 1.1 装 `@tiptap/react`＋`@tiptap/pm`＋`@tiptap/starter-kit`＋`@tiptap/extensions`（3.31.3）；React 19 挂载经全量 e2e 实测通过（未走 @tiptap/core 直挂退路）
- [x] 1.2 ProsePane 换 TipTap 内核：schema 仅段落（StarterKit 裁剪到 document/paragraph/text/undo-redo）、`.editor` 宿主类与 contenteditable 属性经 `editorProps.attributes` 保留、fs/lh 偏好类照挂、`.editor-wrap`/`.editor-status`/`.generating` 不动
- [x] 1.3 版式迁移：段落 CSS（段首缩进/680 版心/宋体）天然命中 ProseMirror 节点；空文档占位改用 Placeholder 扩展（`.is-editor-empty::before`）

## 2. 序列化与同步

- [x] 2.1 `proseDoc.ts` 单源＋7 单测（多段/空段/全空格段/NBSP/空串/尾部空段/CRLF）
- [x] 2.2 外部 prose 同步：指纹比对＋`setContent(emitUpdate:false)`＋光标回文首（对齐旧契约）；覆盖载章/归档恢复 reload/采纳/AI 完成四路径
- [x] 2.3 粘贴归一：handlePaste 走纯文本（多段落结构保留、格式剥离）

## 3. AI 流式与选区

- [x] 3.1 `startStream` 事务化：chunk 追加到插入点（`addToHistory:false`，SHALL NOT 整文档重建）
- [x] 3.2 `finishStream` 两步收尾（删流式区间不入史＋整段写回入史）→ 整次生成＝一个可撤销单元；停止/失败/`qcReport`/`onWriteProgress` 照旧；流式期 `setEditable(false)`
- [x] 3.3 `captureNow` 改读 **DOM 选区**＋`posAtDOM` 映射（PM 消化 selectionchange 有延迟，读 `state.selection` 会拿到旧点——实测定案）；润色/扩写/压缩采纳替换走范围事务（`insertContentAt({from,to})`）

## 4. 只读与两态

- [x] 4.1 `setEditable` 接 `editing && !notEditable && !streaming`；`prose-edit` 两态顶行、锁定横幅、frontier/ghost 口径零改动
- [x] 4.2 旧层退役：`execCommand`/`proseToHtml`/`collectParagraphs`/`escapeHtml` 全删；编辑器**单实例长驻**（deps=[]，切章走 setContent）

## 5. 测试与门禁

- [x] 5.1 vitest：序列化 7 条＋全量 878/878 绿（真依赖安装，环境噪音亦清零）
- [x] 5.2 e2e：隔离栈全量终验（结果见 PR）；新增两条编辑器内核回归——「流式写入可整体撤销，落库同步」「润色采纳＝范围事务替换，一次撤销还原原文」
- [ ] 5.3 IME 手测清单（appendix-ime-checklist.md）——**待人工在真机过一遍**（自动化只覆盖 composition 挂起逻辑，真实输入法行为无法自动化）
- [x] 5.4 tsc 零新增错误；体积记录：主包 830KB→1.23MB raw（约 +115KB gz），保持单 chunk 未拆（桌面本地应用，无首屏网络成本）
- [x] 5.5 openspec validate --strict

## 实现偏差与顺带修复（记录）

- **撤销分组**：prosemirror-history 无公开分组 API，采用「流式 chunk 不入史＋收尾两次写回」实现整次生成＝一个撤销单元（一次撤销回到生成前）——spec 场景已由 e2e 钉住（prompt-pipeline「流式写入可整体撤销」）。
- **采纳路径顺带修掉一个存量缺陷**：旧 `capture.fullText` 取自 `div.textContent`（段间无 `\n`），多段章节采纳润色会把段落折成一段并被持久化；新实现 fullText/偏移/替换统一在 `\n` 坐标系，采纳后段落结构保留。
- **编辑器单实例长驻**为实测结论（非原设计）：原设计「随章重建」在 React effect 时序下会拿到已销毁实例并卸载子树（实测：加章后整树空白），已改为不重建＋全量 `isDestroyed` 守卫。
- **体积**：未拆 chunk（原备选方案）；桌面打包形态下首屏无网络成本，拆包收益为负（多一个请求、构建配置复杂化）。
