// 拆书入口结构判定（c-deconstruct-book 11）：本地秒级判定，不耗模型额度。
// 与后端 deconstruct/textparse.structure_verdict 同规则；阈值由后端
// test_shared_constants_parity 对拍钉死，改任一侧必须两侧同改。

export const SINGLE_CHAPTER_RISK_CHARS = 30_000;
export const AVG_CHAPTER_WARN_CHARS = 20_000;
export const TINY_CHAPTER_CHARS = 200;
export const TINY_CHAPTER_MIN_COUNT = 5;

/** 拆卡单章喂料上限（超长章取头 4000＋尾 2000 的合计）＝后端 deconstruct/pipeline 实际喂料，
 *  单源 textparse.CARD_TEXT_LIMIT，parity 钉对拍——risk 文案里的字数随它走。 */
export const CARD_TEXT_LIMIT = 6_000;

/** 无 BOM 的 UTF-16/32 被当 GBK 解出来会满屏空字节——按解失败处理（与后端 NUL_RATIO_LIMIT 同值）。 */
export const NUL_RATIO_LIMIT = 0.002;

export type StructureLevel = "ok" | "warn" | "risk";

export interface StructureVerdict {
  level: StructureLevel;
  issues: string[];
  chapterCount: number;
  avgChapterChars: number;
}

export interface StructureInput {
  /** 逐章去空白字数（本地正则切分；未识别到章标题行为空数组＝整本单章同口径） */
  chapterChars: number[];
  totalChars: number;
}

export function structureVerdict(input: StructureInput): StructureVerdict {
  const n = input.chapterChars.length;
  const total = input.totalChars;
  const avg = n > 0 ? Math.floor(total / n) : 0;
  // risk 只盯「无章标题回退」形态（chapterChars 空＝未识别到章标题行）；
  // 带章标题的单章不算——容量与章长另有提示口径，不在此拦。
  const risk = n === 0 && total >= SINGLE_CHAPTER_RISK_CHARS;
  const issues: string[] = [];
  if (risk) {
    issues.push(
      `未识别到章节标题：全书 ${total} 字将按单章拆解，而拆卡只分析每章开头/结尾约 ${CARD_TEXT_LIMIT} 字——` +
        "大部头几乎不会被读到，质量会很差。建议规范章节标题（每章一行「第X章 标题」）后重传",
    );
  } else {
    if (avg > AVG_CHAPTER_WARN_CHARS && n >= 3) {
      issues.push(`平均每章约 ${avg} 字，远超常见网文章长——部分章标题可能漏识别，章节切分可能不准`);
    }
    const tiny = input.chapterChars.filter((c) => c < TINY_CHAPTER_CHARS).length;
    if (tiny >= Math.max(TINY_CHAPTER_MIN_COUNT, Math.floor(n * 0.3))) {
      issues.push(`${tiny}/${n} 章不足 ${TINY_CHAPTER_CHARS} 字——可能把目录行误认为章标题，建议删除目录后重传`);
    }
  }
  return {
    level: risk ? "risk" : issues.length > 0 ? "warn" : "ok",
    issues,
    chapterCount: n,
    avgChapterChars: avg,
  };
}

/** UTF-16/32 BOM 直判（与后端 detect_encoding 同规则）：命中返回编码名，否则 null。 */
export function detectUtfBom(raw: Uint8Array): "utf-16" | "utf-32" | null {
  if (raw.length >= 4 && ((raw[0] === 0xff && raw[1] === 0xfe && raw[2] === 0 && raw[3] === 0) || (raw[0] === 0 && raw[1] === 0 && raw[2] === 0xfe && raw[3] === 0xff))) {
    return "utf-32";
  }
  if (raw.length >= 2 && ((raw[0] === 0xff && raw[1] === 0xfe) || (raw[0] === 0xfe && raw[1] === 0xff))) {
    return "utf-16";
  }
  return null;
}

export function nulRatioOverLimit(text: string): boolean {
  const stripped = text.replace(/\x00/g, "");
  return text.length - stripped.length > text.length * NUL_RATIO_LIMIT;
}
