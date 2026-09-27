# 正文编辑器核心迁移 TipTap——段落-only schema，纯文本契约不变

## Why

正文编辑器是 `ProsePane.tsx` 内手搓的 contenteditable 层（全仓唯一富文本面），维护方式已现脆性：

- `document.execCommand("defaultParagraphSeparator")` 已被 MDN 标记废弃，无替代的原生路径；
- 纯文本 ↔ `<p>` HTML 的往返转换（`proseToHtml`/`collectParagraphs`）＋输入期整编辑器 `innerHTML` 重建，撤销/重做完全依赖浏览器原生且会被重建销毁；
- **中文 IME 组合期**的程序性渲染风险：拼音组词中途的重渲会打断组合——对中文长文写作应用这是头号隐患，且难以在自制层内彻底兜住；
- 选区捕获（润色/扩写/压缩）靠 `toString().length` 数偏移，后续「AI 只改选中段」、批注、查找替换等写作向功能没有地基。

产品数据模型端到端是纯文本（chapter.prose `\n` 分段；AI 提示词、预览阅读器、成稿下载全部消费纯文本），**不引入富文本存储**——本变更只换输入面。

## What Changes

- **编辑器内核换 TipTap**（ProseMirror 内核，`@tiptap/react`）：schema 收成「仅段落」（Document = paragraph\*，无其它节点/标记类型）。
- **序列化契约不变**：编辑器 ↔ `chapter.prose` 仍是 `\n` 分段纯文本，序列化层单源函数（`proseToDoc`/`docToProse`）；后端、AI 提示词链、预览阅读器、成稿下载零改动。
- **AI 流式写入改事务**：按 chunk 追加进文档（SHALL NOT 整文档重建），流式写入 SHALL 为可整体撤销的历史单元（完成后一次撤销回到生成前起点）；开始/停止/完成/失败收尾语义与完工检查（qcReport）不变。
- **选区捕获改走编辑器选区模型**：对外的 `SelectionCapture`（纯文本偏移 + text + fullText）形状不变，润色/扩写/压缩采纳替换走事务。
- **只读语义全部保持**：c-prose-edit-gate 的查看/编辑两态（`prose-edit` 入口、contenteditable=false 判定）、归档/frontier/旧稿三套锁优先、流式期间不可编辑，行为与 e2e 断言口径均不变。
- **版式不变**：宋体 17/2.0、680 版心、段首缩进、per-book 字号/行距偏好类照挂。
- **粘贴归一**：任何富文本粘贴一律降为纯文本段落（沿用现行为，改由编辑器层保证）。

**非目标**：不引入格式化工具栏、Markdown 语法、富文本存储；不改后端契约；不改预览阅读器与下载；不改章纲/文风/设定等其它页签。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `workbench`：ADDED「正文编辑器核心契约」（纯文本投影、IME 安全、撤销历史、粘贴归一、只读判定保持、版式保持）。
