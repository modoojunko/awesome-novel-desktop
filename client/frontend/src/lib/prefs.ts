/**
 * 本地偏好（localStorage，设备级）：
 * - 默认字号/行距（全局写作偏好：新建章节正文的排版基线）
 * - 归档 AI 摘要开关（默认开；关闭后归档用正文前 200 字降级摘要，不消耗 AI 额度）
 * - 归档 AI 摘要首次提示（会员第一次归档前弹「将消耗 AI 额度」提示）
 * - 本书覆盖（book.html modalPrefs，PR 5）：字号/行距/归档 AI 摘要可按书落库，
 *   未设置的书回落全局默认（key: pref.book.{projectId}.{fs|lh|ai_summary}）。
 */

const KEY_AI_SUMMARY = "pref.archive_ai_summary";
const KEY_NOTICE_SHOWN = "pref.archive_notice_shown";
const KEY_FONT_SIZE = "pref.default_font_size";
const KEY_LINE_HEIGHT = "pref.default_line_height";
const KEY_ZHUQUE_SHOW = "pref.zhuque_show";

export type FontSizePref = "fs-s" | "fs-m" | "fs-l";
export type LineHeightPref = "lh-tight" | "lh-comfy" | "lh-loose";

export function getDefaultFontSize(): FontSizePref {
  try {
    const v = localStorage.getItem(KEY_FONT_SIZE);
    return v === "fs-s" || v === "fs-l" ? v : "fs-m";
  } catch {
    return "fs-m";
  }
}

export function setDefaultFontSize(v: FontSizePref) {
  try {
    localStorage.setItem(KEY_FONT_SIZE, v);
  } catch {
    // 忽略
  }
}

export function getDefaultLineHeight(): LineHeightPref {
  try {
    const v = localStorage.getItem(KEY_LINE_HEIGHT);
    return v === "lh-tight" || v === "lh-loose" ? v : "lh-comfy";
  } catch {
    return "lh-comfy";
  }
}

export function setDefaultLineHeight(v: LineHeightPref) {
  try {
    localStorage.setItem(KEY_LINE_HEIGHT, v);
  } catch {
    // 忽略
  }
}

/** 「在写作台显示朱雀检测」（c-zhuque-ai-detect）：应用级开关，默认开。
 *  关＝右栏检测行/标题区结果条/正文标注三处不出现，已配置 Key 不受影响。 */
export function getZhuqueShow(): boolean {
  try {
    return localStorage.getItem(KEY_ZHUQUE_SHOW) !== "off";
  } catch {
    return true;
  }
}

export function setZhuqueShow(enabled: boolean) {
  try {
    localStorage.setItem(KEY_ZHUQUE_SHOW, enabled ? "on" : "off");
    window.dispatchEvent(new CustomEvent("zhuque-show-changed", { detail: enabled }));
  } catch {
    // localStorage 不可用：保持默认开
  }
}

export function getArchiveAiSummaryEnabled(): boolean {
  try {
    return localStorage.getItem(KEY_AI_SUMMARY) !== "off";
  } catch {
    return true;
  }
}

export function setArchiveAiSummaryEnabled(enabled: boolean) {
  try {
    localStorage.setItem(KEY_AI_SUMMARY, enabled ? "on" : "off");
  } catch {
    // localStorage 不可用（隐私模式等）：保持默认开
  }
}

export function isArchiveNoticeShown(): boolean {
  try {
    return localStorage.getItem(KEY_NOTICE_SHOWN) === "1";
  } catch {
    return true; // 读不到就不再打扰
  }
}

export function markArchiveNoticeShown() {
  try {
    localStorage.setItem(KEY_NOTICE_SHOWN, "1");
  } catch {
    // 忽略
  }
}

// ---------------------------------------------------------------------------
// 本书偏好（modalPrefs）：per-project 覆盖，未设置回落全局默认
// ---------------------------------------------------------------------------

type BookPrefKey = "fs" | "lh" | "ai_summary" | "last_write";

function bookKey(projectId: string, key: BookPrefKey): string {
  return `pref.book.${projectId}.${key}`;
}

/** 本书字号：未设置回落全局默认。 */
export function getBookFontSize(projectId: string): FontSizePref {
  try {
    const v = localStorage.getItem(bookKey(projectId, "fs"));
    return v === "fs-s" || v === "fs-l" || v === "fs-m" ? v : getDefaultFontSize();
  } catch {
    return getDefaultFontSize();
  }
}

export function setBookFontSize(projectId: string, v: FontSizePref) {
  try {
    localStorage.setItem(bookKey(projectId, "fs"), v);
  } catch {
    // 忽略
  }
}

/** 本书行距：未设置回落全局默认。 */
export function getBookLineHeight(projectId: string): LineHeightPref {
  try {
    const v = localStorage.getItem(bookKey(projectId, "lh"));
    return v === "lh-tight" || v === "lh-loose" || v === "lh-comfy"
      ? v
      : getDefaultLineHeight();
  } catch {
    return getDefaultLineHeight();
  }
}

export function setBookLineHeight(projectId: string, v: LineHeightPref) {
  try {
    localStorage.setItem(bookKey(projectId, "lh"), v);
  } catch {
    // 忽略
  }
}

/** 本书归档 AI 摘要：未设置回落全局开关。 */
export function getBookArchiveAiSummary(projectId: string): boolean {
  try {
    const v = localStorage.getItem(bookKey(projectId, "ai_summary"));
    return v === "on" ? true : v === "off" ? false : getArchiveAiSummaryEnabled();
  } catch {
    return getArchiveAiSummaryEnabled();
  }
}

export function setBookArchiveAiSummary(projectId: string, enabled: boolean) {
  try {
    localStorage.setItem(bookKey(projectId, "ai_summary"), enabled ? "on" : "off");
  } catch {
    // 忽略
  }
}

// ---------------------------------------------------------------------------
// 预览阅读偏好（preview-reader）：per-project 四轴，只作用预览视图——
// 不读也不写写作偏好（fs/lh 两族，上方 bookKey 区），互不污染（c-preview-reader）。
// ---------------------------------------------------------------------------

export type ReadingSize = "s" | "m" | "l";
export type ReadingLine = "tight" | "comfy" | "loose";
export type ReadingFont = "serif" | "sans" | "kai";
export type ReadingTheme = "paper" | "sepia" | "night";

export interface ReadingPrefs {
  size: ReadingSize;
  font: ReadingFont;
  line: ReadingLine;
  theme: ReadingTheme;
}

/** 默认 中号 · 衬线 · 舒适 · 白纸。 */
const READING_DEFAULT: ReadingPrefs = { size: "m", font: "serif", line: "comfy", theme: "paper" };

const READING_ALLOWED: Record<keyof ReadingPrefs, string[]> = {
  size: ["s", "m", "l"],
  font: ["serif", "sans", "kai"],
  line: ["tight", "comfy", "loose"],
  theme: ["paper", "sepia", "night"],
};

function readingKey(projectId: string, key: string): string {
  return `pref.book.${projectId}.read.${key}`;
}

/** 本书阅读偏好：非法值/缺省逐轴回落默认（不回落写作偏好）。 */
export function getBookReadingPrefs(projectId: string): ReadingPrefs {
  const read = (key: keyof ReadingPrefs): string => {
    try {
      const v = localStorage.getItem(readingKey(projectId, key));
      return v && READING_ALLOWED[key].includes(v) ? v : READING_DEFAULT[key];
    } catch {
      return READING_DEFAULT[key];
    }
  };
  return {
    size: read("size") as ReadingSize,
    font: read("font") as ReadingFont,
    line: read("line") as ReadingLine,
    theme: read("theme") as ReadingTheme,
  };
}

export function setBookReadingPref<K extends keyof ReadingPrefs>(
  projectId: string,
  key: K,
  value: ReadingPrefs[K],
) {
  try {
    localStorage.setItem(readingKey(projectId, key), value);
  } catch {
    // 忽略（隐私模式等）
  }
}

/** 上次写作会话（行头归一「续写」口径，用户拍板 2026-09-16）：
 *  记「哪一章 + 编辑器滚动位置比例」，续写=回到上次退出前的进度。
 *  纯本机 localStorage（设备级），不上传；书内章删除后由消费方校验回落。 */
export interface LastWriteSession {
  ref: string;
  /** 编辑器滚动比例 0..1（内容不足一屏为 0） */
  scroll: number;
  ts: number;
}

export function getLastWriteSession(projectId: string): LastWriteSession | null {
  try {
    const raw = localStorage.getItem(bookKey(projectId, "last_write"));
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<LastWriteSession> | null;
    if (!v || typeof v.ref !== "string" || !v.ref) return null;
    const scroll = typeof v.scroll === "number" ? Math.min(1, Math.max(0, v.scroll)) : 0;
    return { ref: v.ref, scroll, ts: typeof v.ts === "number" ? v.ts : 0 };
  } catch {
    return null;
  }
}

export function setLastWriteSession(projectId: string, ref: string, scroll: number) {
  try {
    localStorage.setItem(
      bookKey(projectId, "last_write"),
      JSON.stringify({ ref, scroll, ts: Date.now() } satisfies LastWriteSession),
    );
  } catch {
    // 忽略
  }
}
