// 正文序列化单源（c-prose-editor-tiptap）：chapter.prose（\n 分段纯文本）
// ↔ TipTap 文档（仅段落）。后端/AI/预览/下载全部只认纯文本，编辑器只是投影。
// 注意：入参统一走纯 JSON（editor.getJSON()），不收 PM Node（其 content 是 Fragment）。
import type { JSONContent } from "@tiptap/core";

/** 纯文本 → TipTap 文档（仅段落）。空串 = 空文档（零段落，占位提示可见）。
 *  空行保留为空段落（与旧 proseToHtml 的 <p><br></p> 口径一致）。 */
export function proseToDoc(prose: string): JSONContent {
  if (!prose) return { type: "doc" };
  const paragraphs = prose.split("\n").map((line) => {
    const content = line ? [{ type: "text", text: line }] : [];
    return content.length
      ? { type: "paragraph", content }
      : { type: "paragraph" };
  });
  return { type: "doc", content: paragraphs };
}

function nodeText(node: JSONContent): string {
  if (node.type === "text") return node.text ?? "";
  return (node.content ?? []).map(nodeText).join("");
}

/** TipTap 文档（纯 JSON，editor.getJSON()）→ 纯文本：段落文本按 \n join；
 *  NBSP 归一（对齐旧 collectParagraphs 口径）。 */
export function docToProse(doc: JSONContent | undefined | null): string {
  if (!doc) return "";
  return (doc.content ?? [])
    .map((p) => nodeText(p).replace(/\u00A0/g, " "))
    .join("\n");
}

/** 纯文本（\n 分段）→ 段落 JSON 数组（insertContentAt / 粘贴归一用）。 */
export function linesToParagraphs(text: string): JSONContent[] {
  return text.replace(/\r\n?/g, "\n").split("\n").map((line) => {
    const content = line ? [{ type: "text", text: line }] : [];
    return content.length
      ? { type: "paragraph", content }
      : { type: "paragraph" };
  });
}

// ── AI 流式归一（fix/stream-mirror-normalize）────────────────────────────
// 后端生成出口（normalize_generated_prose）在 done 时把段间空行收敛为单换行；
// 流式插入侧对「已收到的全量」做同口径归一并取增量，保证流式所见＝落库最终态
// （否则模型发的段间空行会先被渲染成空段落、done 时才收敛——所见与所得不一致）。

/** 与后端 normalize_generated_prose 同口径：CRLF 归一、段间空行收敛、去首部换行。
 *  尾部换行流式期保留（后续分块可能接续），done 时由后端已去尾部，重排零跳变。 */
export function normalizeStreamedProse(raw: string): string {
  return (raw || "")
    .replace(/\r\n?/g, "\n")
    .replace(/\n{2,}/g, "\n")
    .replace(/^\n+/, "");
}

/** 归一全量取增量：已插入前缀之外的新片段（归一具前缀稳定性，增量安全）。 */
export function proseDelta(full: string, insertedLen: number): string {
  return full.length > insertedLen ? full.slice(insertedLen) : "";
}
