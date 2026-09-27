// 正文序列化单源（c-prose-editor-tiptap）：prose ↔ TipTap 文档无损往返。
// 契约 = spec「正文编辑器核心契约」：\n 分段纯文本、空串↔空文档、NBSP 归一。
import { describe, expect, it } from "vitest";

import { docToProse, linesToParagraphs, proseToDoc } from "@/components/novel/workbench/proseDoc";

describe("proseDoc 序列化（纯文本 ↔ TipTap 文档）", () => {
  it("空串 = 空文档（零段落，占位可见）", () => {
    const doc = proseToDoc("");
    expect(doc.type).toBe("doc");
    expect(doc.content).toBeUndefined();
    expect(docToProse(doc)).toBe("");
  });

  it("多段往返无损（\\n 分段一一对应）", () => {
    const prose = "第一段开头。\n第二段有两句话。\n第三段。";
    const back = docToProse(proseToDoc(prose));
    expect(back).toBe(prose);
  });

  it("空行保留为空段落", () => {
    const prose = "甲段\n\n乙段";
    const back = docToProse(proseToDoc(prose));
    expect(back).toBe(prose);
  });

  it("全空格段落不丢", () => {
    const prose = "甲段\n   \n乙段";
    const back = docToProse(proseToDoc(prose));
    expect(back).toBe(prose);
  });

  it("NBSP 归一为普通空格（对齐旧 collectParagraphs 口径）", () => {
    const doc = proseToDoc("");
    doc.content = [
      { type: "paragraph", content: [{ type: "text", text: "前\u00A0后" }] },
    ];
    expect(docToProse(doc)).toBe("前 后");
  });

  it("尾部换行产生尾随空段落（往返保留）", () => {
    const prose = "甲段\n";
    const back = docToProse(proseToDoc(prose));
    expect(back).toBe(prose);
  });

  it("linesToParagraphs 归一 CRLF 并保空段", () => {
    const paras = linesToParagraphs("甲\r\n\r\n乙");
    expect(paras).toHaveLength(3);
    expect(paras[0].content?.[0]).toMatchObject({ type: "text", text: "甲" });
    expect(paras[1].content).toBeUndefined();
    expect(paras[2].content?.[0]).toMatchObject({ type: "text", text: "乙" });
  });
});
