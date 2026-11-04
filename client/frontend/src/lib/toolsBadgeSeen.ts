// 顶栏「写作工具」徽标的本地已看账（c-tools-badge-seen）：引导语义，不是未读信箱——
// 看过任务清单/详情后，已完成未取任务不再计数；新任务完成＝新任务 id，引导重亮。
// 纯前端 localStorage（按设备），后端不存已看状态；读写全部 fail-soft，坏账退回「没看过」。
// 消账必须实时反映到顶栏徽标（评审 P2）：清单页 effect 写账时轮询多半已停表、
// focus 重取也关着——ToolsMenu 经 useSeenTaskIds 订阅账变，消账后当场重算，不等交互。
import { useSyncExternalStore } from "react";

const KEY = "tools_badge_seen_v1";
/** 账本上限：防历史 id 无限累积（删除任务留下的死 id 随裁剪淘汰） */
const CAP = 500;

const listeners = new Set<() => void>();
/** 账本版本号：写成功即自增；快照缓存按它失效，保证 getSnapshot 身份稳定（SES 约束） */
let seq = 0;
let snap: { at: number; set: Set<string> } | null = null;

/** 已看过任务 id 集（坏账容错：非 JSON／非数组／非字符串条目一律当没看过） */
export function seenTaskIds(): Set<string> {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((v): v is string => typeof v === "string"));
  } catch {
    return new Set(); // 坏 JSON／无 localStorage：退回「全都没看过」＝引导照旧
  }
}

/** 消账：把这批任务 id 记成已看过（合并写回；超限裁最旧的），写成功才广播重算 */
export function markTasksSeen(ids: string[]): void {
  if (ids.length === 0) return;
  try {
    const merged = new Set([...seenTaskIds(), ...ids]);
    localStorage.setItem(KEY, JSON.stringify([...merged].slice(-CAP)));
  } catch {
    return; // 存不进（隐私模式等）＝账没变：下次引导照旧，不广播
  }
  seq += 1;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  snap = null; // 新订阅者挂载即重读：不背上一轮订阅者留下的快照（测试间 clear 同理）
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** 响应式已看集：顶栏徽标订阅它，清单/详情页消账后徽标即时归零（无需任何交互） */
export function useSeenTaskIds(): Set<string> {
  return useSyncExternalStore(subscribe, () => {
    if (!snap || snap.at !== seq) snap = { at: seq, set: seenTaskIds() };
    return snap.set;
  });
}
