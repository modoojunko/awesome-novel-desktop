/** 归档世界要素建议（lore-keeping）跨视图暂存：归档时写入，世界页 06 读取确认。
 *  会话内内存态（后端 lore-suggest 本身 stateless，丢失=重开一次体检无害）。 */

import type { WorldLoreSuggestion } from "./ai";

export interface PendingLore extends WorldLoreSuggestion {
  origin: string; // 章节引用（vol-N-ch-M），幂等键
}

const store = new Map<string, PendingLore[]>();

export function recordLoreSuggestions(
  projectId: string,
  origin: string,
  list: WorldLoreSuggestion[],
): void {
  if (!list.length) return;
  const prev = store.get(projectId) ?? [];
  const fresh = list.filter(
    (s) =>
      !prev.some(
        (p) => p.origin === origin && p.key === s.key && p.set === s.set,
      ),
  );
  store.set(projectId, [...prev, ...fresh.map((s) => ({ ...s, origin }))]);
}

export function getLoreSuggestions(projectId: string): PendingLore[] {
  return store.get(projectId) ?? [];
}

export function dropLoreSuggestion(
  projectId: string,
  item: PendingLore,
): void {
  store.set(
    projectId,
    (store.get(projectId) ?? []).filter(
      (p) => !(p.origin === item.origin && p.key === item.key && p.set === item.set),
    ),
  );
}
