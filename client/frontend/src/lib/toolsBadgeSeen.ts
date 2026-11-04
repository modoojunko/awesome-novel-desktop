// 顶栏「写作工具」徽标的本地已看账（c-tools-badge-seen）：引导语义，不是未读信箱——
// 看过任务清单/详情后，已完成未取任务不再计数；新任务完成＝新任务 id，引导重亮。
// 纯前端 localStorage（按设备），后端不存已看状态；读写全部 fail-soft，坏账退回「没看过」。
const KEY = "tools_badge_seen_v1";
/** 账本上限：防历史 id 无限累积（删除任务留下的死 id 随裁剪淘汰） */
const CAP = 500;

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

/** 消账：把这批任务 id 记成已看过（合并写回；超限裁最旧的） */
export function markTasksSeen(ids: string[]): void {
  if (ids.length === 0) return;
  try {
    const merged = new Set([...seenTaskIds(), ...ids]);
    localStorage.setItem(KEY, JSON.stringify([...merged].slice(-CAP)));
  } catch {
    // 存不进（隐私模式等）＝下次引导照旧，静默
  }
}
