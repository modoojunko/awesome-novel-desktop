/** 归档世界要素建议（lore-keeping）跨视图暂存：归档时写入，世界页 06 读取确认。
 *  sessionStorage 兜底（同一标签页刷新不丢；后端 lore-suggest stateless，
 *  丢失=对该章重跑一次归档建议，无害）。 */

import type { WorldLoreSuggestion } from "./ai";

export interface PendingLore extends WorldLoreSuggestion {
  origin: string; // 章节引用（vol-N-ch-M），幂等键
}

const KEY_PREFIX = "lore-suggestions:";

function load(projectId: string): PendingLore[] {
  try {
    const raw = sessionStorage.getItem(KEY_PREFIX + projectId);
    const list = raw ? (JSON.parse(raw) as PendingLore[]) : [];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

function save(projectId: string, list: PendingLore[]): void {
  try {
    if (list.length) sessionStorage.setItem(KEY_PREFIX + projectId, JSON.stringify(list));
    else sessionStorage.removeItem(KEY_PREFIX + projectId);
  } catch {
    /* 存储不可用（隐私模式等）退化为会话内存态 */
  }
}

export function recordLoreSuggestions(
  projectId: string,
  origin: string,
  list: WorldLoreSuggestion[],
): void {
  if (!list.length) return;
  const prev = load(projectId);
  const fresh = list.filter(
    (s) =>
      !prev.some(
        (p) => p.origin === origin && p.key === s.key && p.set === s.set,
      ),
  );
  if (fresh.length) save(projectId, [...prev, ...fresh.map((s) => ({ ...s, origin }))]);
}

export function getLoreSuggestions(projectId: string): PendingLore[] {
  return load(projectId);
}

export function dropLoreSuggestion(
  projectId: string,
  item: PendingLore,
): void {
  save(
    projectId,
    load(projectId).filter(
      (p) => !(p.origin === item.origin && p.key === item.key && p.set === item.set),
    ),
  );
}
