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
