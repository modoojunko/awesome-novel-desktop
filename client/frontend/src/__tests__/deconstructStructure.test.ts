// 拆书入口结构判定库（c-deconstruct-book 11）：阈值 parity 钉在后端
// test_shared_constants_parity.py::TestDeconstructStructureParity，两侧同改。
import { describe, expect, it } from "vitest";
import { detectUtfBom, nulRatioOverLimit, structureVerdict } from "@/lib/deconstructStructure";

describe("structureVerdict", () => {
  it("无章标题大部头 → risk", () => {
    const v = structureVerdict({ chapterChars: [], totalChars: 50_000 });
    expect(v.level).toBe("risk");
    expect(v.issues[0]).toContain("未识别到章节标题");
    expect(v.issues[0]).toContain("第X章");
  });

  it("无章标题小部头（3 万字线下）→ ok：拆卡头尾尚有覆盖，不重复报", () => {
    const v = structureVerdict({ chapterChars: [], totalChars: 29_999 });
    expect(v.level).toBe("ok");
    expect(v.issues).toEqual([]);
  });

  it("带章标题的单章大部头不算 risk（容量/章长另有口径，不在此拦）", () => {
    const v = structureVerdict({ chapterChars: [610_000], totalChars: 610_000 });
    expect(v.level).toBe("ok");
    expect(v.issues).toEqual([]);
  });

  it("平均章长超 2 万 → warn（章标题疑似漏识别）", () => {
    const v = structureVerdict({ chapterChars: [25_000, 25_000, 25_000, 25_000], totalChars: 100_000 });
    expect(v.level).toBe("warn");
    expect(v.issues.join()).toContain("远超常见网文章长");
  });

  it("极短章扎堆 → warn（目录行误识别嫌疑）", () => {
    const v = structureVerdict({ chapterChars: [1, 1, 1, 1, 1, 300], totalChars: 305 });
    expect(v.level).toBe("warn");
    expect(v.issues.join()).toContain("目录");
  });

  it("正常结构 → ok 无问题", () => {
    const v = structureVerdict({ chapterChars: Array.from({ length: 11 }, () => 250), totalChars: 2_750 });
    expect(v.level).toBe("ok");
    expect(v.issues).toEqual([]);
    expect(v.chapterCount).toBe(11);
    expect(v.avgChapterChars).toBe(250);
  });
});

describe("detectUtfBom", () => {
  it("UTF-16LE/BE BOM 命中", () => {
    expect(detectUtfBom(new Uint8Array([0xff, 0xfe, 0x41, 0x00]))).toBe("utf-16");
    expect(detectUtfBom(new Uint8Array([0xfe, 0xff, 0x00, 0x41]))).toBe("utf-16");
  });

  it("UTF-32 BOM 命中（先于 UTF-16 判）", () => {
    expect(detectUtfBom(new Uint8Array([0xff, 0xfe, 0x00, 0x00]))).toBe("utf-32");
    expect(detectUtfBom(new Uint8Array([0x00, 0x00, 0xfe, 0xff]))).toBe("utf-32");
  });

  it("无 BOM（含 UTF-8 BOM/空数组）→ null", () => {
    expect(detectUtfBom(new Uint8Array([0xef, 0xbb, 0xbf, 0x41]))).toBeNull();
    expect(detectUtfBom(new Uint8Array([]))).toBeNull();
  });
});

describe("nulRatioOverLimit", () => {
  it("空字节超限判 true（无 BOM UTF-16 形态）", () => {
    expect(nulRatioOverLimit("a\x00b\x00c\x00")).toBe(true);
  });

  it("正常文本判 false", () => {
    expect(nulRatioOverLimit("正文没有空字节，标点、数字 12345。")).toBe(false);
  });
});
