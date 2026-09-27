// drawSession — 抽卡会话的本地持久化（c-plan-draw-exclude）。
// 误关/刷新后原批恢复（不重新生成、不重复计量）；排除清单跟目标走（最近 3 批 ≤9 条）；
// 排上/成卷即清。SHALL NOT 落库——localStorage 是会话期用品（先例：落点卡 ever_planned 信号）。
// c-character-intro：cast 分型（键 cs-draw:{pid}:{chRef}）——载荷含盘点结果/三选一/
// 输入指纹（只盖剧情输入，落账写名字不失效）/gapId 批次；appendExclude 的 axis+line
// 过滤会整批丢 cast 条目（cast 是 axis/name/persona 三键），故 cast 专用 appendCastExclude。

import type { CastCard, CastChoice, CastReviewResponse } from "./castReviewApi";

export interface DrawExcludeItem {
  axis: string;
  line: string;
}

const MAX_ITEMS = 9;

export const drawKey = {
  /** 卷抽卡：同卷号一个会话 */
  volume: (pid: string, volNo: number) => `vp-draw:${pid}:vol${volNo}`,
  /** 章抽卡：同卷一个会话（载荷内带 nextNo 复核目标章） */
  chapter: (pid: string, volRef: string) => `cp-draw:${pid}:${volRef}`,
  /** 人物精盘抽卡：跟章走（c-character-intro） */
  cast: (pid: string, chRef: string) => `cs-draw:${pid}:${chRef}`,
};

export function loadDraw<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null; // 私隐模式/配额满：尽力而为，恢复不了就走重抽
  }
}

export function saveDraw(key: string, payload: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(payload));
  } catch {
    /* 尽力而为 */
  }
}

export function clearDraw(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    /* 尽力而为 */
  }
}

/** 当前批并入排除清单（作者按了「换一批」＝这批不要了），保留最近 9 条 */
export function appendExclude(list: DrawExcludeItem[], batch: DrawExcludeItem[]): DrawExcludeItem[] {
  return [...list, ...batch].filter((x) => x.axis && x.line).slice(-MAX_ITEMS);
}

// ── cast 分型（c-character-intro 人物精盘）────────────────────────────────

/** cast 专用排除项（轴/称呼/一句人设；勿走 DrawExcludeItem 的 axis+line 过滤） */
export interface CastExcludeItem {
  axis: string;
  name: string;
  persona: string;
}

/** 当前批并入排除清单（cast 分型：axis/name/persona 三键都齐才算一条，保留最近 9 条） */
export function appendCastExclude(
  list: CastExcludeItem[],
  batch: CastExcludeItem[],
): CastExcludeItem[] {
  return [...list, ...batch]
    .filter((x) => x.axis && x.name && x.persona)
    .slice(-MAX_ITEMS);
}

/** 单个缺口的会话状态（处理记录＋未写入批次；随 gapId 粒度清理） */
export interface CastGapSession {
  /** 锚文本快照（段全文；重盘对回判「段文本是否已变」用） */
  anchor: string;
  /** 三选一当前值 */
  choice: CastChoice;
  /** 作者动过三选一（「AI 建议」标随改选消失） */
  touched: boolean;
  /** 处理状态：written 落账写入 / deferred 延后 / edited 改段 / open 待处理 */
  status: "open" | "written" | "deferred" | "edited";
  /** 写入落账的名字（status=written） */
  writtenName?: string;
  /** 落账时是否建了卡（回执文案分「建卡并写入」/「只加名单」两形） */
  writtenWithCard?: boolean;
  /** 已出批卡（每批 3 张；「换一批」追加、落账/从头再来清） */
  batches: CastCard[][];
  /** 排除清单（换一批带出；≤9） */
  exclude: CastExcludeItem[];
}

/** 精盘会话载荷（跟章走；localStorage 会话期用品） */
export interface CastSession {
  /** 输入指纹（只盖剧情输入：plot_items＋留存格；落账写名字不失效） */
  fp: string;
  /** 盘点结果载荷 */
  review: CastReviewResponse;
  /** 按 gapId 的处理记录与批次 */
  gaps: Record<string, CastGapSession>;
}

export function loadCastSession(key: string): CastSession | null {
  const s = loadDraw<CastSession>(key);
  if (!s || typeof s !== "object" || typeof s.fp !== "string" || !s.review) return null;
  return { fp: s.fp, review: s.review, gaps: s.gaps ?? {} };
}

export function saveCastSession(key: string, session: CastSession): void {
  saveDraw(key, session);
}

/** 按 gapId 粒度清理（该缺口写入落账后／「从头再来」）：只清该缺口的抽卡批次与
 *  排除清单，处理记录（三选一/已写入）保留到全部处理完；其他缺口一概不动。 */
export function pruneCastGap(key: string, gapId: string): void {
  const s = loadCastSession(key);
  if (!s || !s.gaps[gapId]) return;
  s.gaps[gapId] = { ...s.gaps[gapId], batches: [], exclude: [] };
  saveCastSession(key, s);
}

/** 全键清理（全部缺口处理完收场） */
export function clearCastSession(key: string): void {
  clearDraw(key);
}

/** 恢复按档位裁剪：免费档丢 cards 载荷（批次＋排除清单），只留盘点结果与三选一 */
export function trimCastSessionForTier(s: CastSession, isPro: boolean): CastSession {
  if (isPro) return s;
  const gaps: Record<string, CastGapSession> = {};
  for (const [id, g] of Object.entries(s.gaps)) {
    gaps[id] = { ...g, batches: [], exclude: [] };
  }
  return { ...s, gaps };
}

/**
 * 「重新盘点」按段 idx 对回合并：段文本未变的段沿用处理记录与未写入批次，
 * 段文本已变的段作废重来（gapId=f(段 idx) 跨重盘稳定）。
 */
export function mergeCastGaps(
  prev: Record<string, CastGapSession>,
  next: Record<string, CastGapSession>,
): Record<string, CastGapSession> {
  const out: Record<string, CastGapSession> = {};
  for (const [id, g] of Object.entries(next)) {
    const old = prev[id];
    out[id] = old && old.anchor === g.anchor ? { ...g, ...old, anchor: g.anchor } : g;
  }
  return out;
}

/** 输入指纹（ogToPartial 同源归一后字段子集）：只盖剧情输入——plot_items＋留存格
 *  （梗概/挑战/阶段/章末落点）；characters 不入指纹（落账写名字不失效，多缺人回程依赖此条）。 */
export function castInputFingerprint(partial: {
  plot_items?: string[];
  challenge?: string;
  plot_stage?: string;
  ladder_exit?: string;
  outline?: { summary?: string; [k: string]: unknown };
}): string {
  return JSON.stringify({
    plot_items: partial.plot_items ?? [],
    summary: partial.outline?.summary ?? "",
    challenge: partial.challenge ?? "",
    plot_stage: partial.plot_stage ?? "",
    ladder_exit: partial.ladder_exit ?? "",
  });
}
