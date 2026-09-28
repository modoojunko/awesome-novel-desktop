// 正文序列化单源（c-prose-editor-tiptap）：prose ↔ TipTap 文档无损往返。
// 契约 = spec「正文编辑器核心契约」：\n 分段纯文本、空串↔空文档、NBSP 归一。
import { describe, expect, it } from "vitest";

import {
  docToProse,
  linesToParagraphs,
  normalizeStreamedProse,
  proseDelta,
  proseToDoc,
} from "@/components/novel/workbench/proseDoc";

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

// ── AI 流式归一（fix/stream-mirror-normalize）：流式所见＝落库最终态 ──

describe("normalizeStreamedProse（与后端生成出口同口径）", () => {
  it("段间空行收敛为单换行", () => {
    expect(normalizeStreamedProse("段1。\n\n段2。")).toBe("段1。\n段2。");
    expect(normalizeStreamedProse("段1。\n\n\n\n段2。")).toBe("段1。\n段2。");
  });

  it("CRLF 归一为 LF", () => {
    expect(normalizeStreamedProse("段1。\r\n段2。\r段3。")).toBe("段1。\n段2。\n段3。");
  });

  it("去首部换行；尾部保留（流式期后续分块可能接续）", () => {
    expect(normalizeStreamedProse("\n\n段1。")).toBe("段1。");
    expect(normalizeStreamedProse("段1。\n\n")).toBe("段1。\n");
  });

  it("空串安全", () => {
    expect(normalizeStreamedProse("")).toBe("");
  });
});

describe("proseDelta 增量（归一具前缀稳定性，取增量安全）", () => {
  it("全量增长取增量；无增长返回空串", () => {
    expect(proseDelta("段1。", 0)).toBe("段1。");
    expect(proseDelta("段1。\n段2。", "段1。".length)).toBe("\n段2。");
    expect(proseDelta("段1。", 3)).toBe("");
  });

  it("分块跨空行：前缀稳定不回改已插入内容", () => {
    const after1 = normalizeStreamedProse("段1。\n\n");
    const after2 = normalizeStreamedProse("段1。\n\n段2。");
    expect(after2.startsWith(after1)).toBe(true);
    expect(proseDelta(after2, after1.length)).toBe("段2。");
  });

  it("分块跨行中：增量从行内接续（无多余拆段）", () => {
    const after1 = normalizeStreamedProse("他说到一半");
    const after2 = normalizeStreamedProse("他说到一半，停了。");
    expect(proseDelta(after2, after1.length)).toBe("，停了。");
  });
});
