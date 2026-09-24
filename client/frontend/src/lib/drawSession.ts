// drawSession — 抽卡会话的本地持久化（c-plan-draw-exclude）。
// 误关/刷新后原批恢复（不重新生成、不重复计量）；排除清单跟目标走（最近 3 批 ≤9 条）；
// 排上/成卷即清。SHALL NOT 落库——localStorage 是会话期用品（先例：落点卡 ever_planned 信号）。

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
