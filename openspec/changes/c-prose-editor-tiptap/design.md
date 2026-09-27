# 设计：正文编辑器迁移 TipTap

## 选型

TipTap（ProseMirror 内核）胜出：长文写作场景社区沉淀最深、IME/组合期处理是 ProseMirror 的成熟强项、React 绑定官方维护（支持 React 19）、headless 设计不绑样式——现有版式 CSS 可原样保留。Lexical 更轻但长文场景沉淀少；Slate API 历史 breaking 多；Quill 套装太重、段落版式定制别扭。版本取 TipTap 3.x（`@tiptap/react` + `@tiptap/pm`），StarterKit 裁剪到只剩 paragraph/text/history/undo-redo 相关（其它扩展不装）。

## 序列化单源（契约核心）

- `chapterForm` 同层新增 `proseDoc.ts`：`proseToDoc(text): JSONContent[]`（`\n` 分段 → paragraph 节点数组）与 `docToProse(doc): string`（段落取 textContent 按 `\n` join，`replace(/\u00A0/g," ")` 对齐现 `collectParagraphs` 口径）。空串 ↔ 空文档（零段落）互转，保住 `:empty` placeholder 行为。
- 编辑器是**纯文本投影**：schema 只有 paragraph；`editorProps` 挂 paste 处理（`editor.commands.insertContent(text, { contentType: "text" })` 或 transformPastedHTML 兜底）实现粘贴归一。

## 外部 prose 同步（受控策略）

沿用现有 `lastRenderedRef` 思想改为「prose 指纹比对」：store 的 `prose` 变化时，若与编辑器当前 `docToProse()` 一致（本地输入回路）则跳过；否则 `editor.commands.setContent(doc, { emitUpdate: false })`。覆盖：载章、归档恢复（reload）、润色/扩写/压缩采纳、AI 完成落盘。本地输入经 `onUpdate → docToProse → setProse`（防抖仍在 store，1.5s 不动）。

## AI 流式写入（事务化）

- `startStream`：`streamBase` 取当前 `docToProse()`；每个 chunk 以事务在文档末尾段落追加文本（TipTap `insertContentAt(docEnd, chunk, { updateSelection: false })`），SHALL NOT `setContent` 整文档重建。
- 历史分组：流式首个 chunk 起，每个事务携带 history 分组 meta（PM `history$` / `newGroupDelay` 机制），使整次流式成为**一个撤销单元**；「停止」走既有 `finishStream(收到的部分, false)`，撤销单元到停止点为止。
- 流式期间编辑态强制不可编辑（`editable(false)`），完成后 `setProse(next)` 走外部同步路径一次；`qcReport`、onWriteProgress、停止按钮全部不动。

## ProseHandle 逐个映射

`focus()`→`editor.commands.focus()`；`captureNow()`→PM selection 换算纯文本偏移（`state.doc.textBetween(0,from)` 数偏移，SelectionCapture 形状不变）；`startWriting/continueWriting`→流式；`stopWriting`→abort+收尾；`polish/expand/compress`→采纳替换改为 `insertContentAt(range→范围, text)` 事务（对照预览弹窗不动）。

## 只读与两态

`editable` 计算＝`editing && !notEditable && !streaming`，接到 `editor.setEditable()`（TipTap 对 contenteditable 属性与行为同管）；`.editor` 宿主类挂 TipTap 的 editorOptions.attributes 上保住 e2e/a11y 判定口；`prose-edit` 两态顶行、锁定期无入口（c-prose-edit-gate）零改动。`.editor-wrap`、`.editor-status`、`.generating`（流式样式）类照挂。

## 测试口径

- vitest：ProsePane 序列化往返（多段/空段/全空格段/NBSP）、两态与锁定 editable 矩阵、流式 mock（chunk→追加、撤销单元）、粘贴归一；jsdom 可跑（ProseMirror 依赖 DOM，jsdom 够用；不行的用例降级为 e2e）。
- e2e：`.editor` 选择器、`contenteditable=false` 断言、typing、自动保存三态、frontier/ghost/归档横幅全部保留——理论上零适配；重点回归 free-writing-flow（IME 无法自动化，**手测项**：拼音组词中途等待/切窗/连续输入不丢字）。
- 手测清单（并入 tasks）：拼音组合期外部事件（保存往返、AI 完成）、撤销/重做跨 AI 生成、从 Word/网页粘贴。

## 风险与对策

- **打包体积** +~150KB gz：桌面应用可接受；vite manualChunks 把 tiptap/pm 单拆 chunk，不进首屏主包。
- **React 19 兼容**：@tiptap/react 3.x 声明支持；落实现前先装依赖跑通最小挂载（tasks 第一步即验证，失败则退 @tiptap/core 直挂——接口面相同）。
- **IME 无法自动化**：以 spec 场景＋手测清单双重兜底；e2e 保留 contenteditable/文本断言作回归护栏。
- **迁移期行为差异**（如空段落的 `<br>` 占位、连续 Enter 的段落语义）：序列化单源函数先写死口径并配单测，实现照单测对齐。
