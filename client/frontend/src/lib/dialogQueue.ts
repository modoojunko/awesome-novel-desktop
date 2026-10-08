/**
 * 壳层弹窗队列（c-lossless-upgrade / shell-dialog-queue 规格）：
 * 首启期的系统级引导弹层（带回卡、写作能力包）经同一队列入场——同一时刻只
 * 放行队首，优先级＝数据（carry=1）> 能力（pack=2）；同级按入队先后。
 *
 * 入队只延迟「呈现」，不延迟后台动作（能力包探测/下载照常，见 openPackModal）。
 * 无抢占：已放行（呈现中）的条目不被后来更高优先级者掀翻——优先级只决定
 * 「谁下一个」。放行条件＝各条目自身完成语义：带回条目由用户点「完成确认」后 finish()；
 * 能力包条目在弹窗关闭时 finish()。**一次点击≠一次同意**——队列只共享弹窗位。
 *
 * 先例＝pack-modal:open / legacy-migrate:open 的「事件 + 单点挂载」模式；本模块
 * 是它们的呈现仲裁层。明确不入队（规格钉死）：更新提示条、会员拦截、业务 Modal。
 */

interface QueueEntry {
  id: string;
  priority: number; // 小者先
  seq: number; // 同优先级 FIFO
  /** 成为队首且被放行时恰好调用一次（真正打开弹窗的动作） */
  dispatch: () => void;
}

let entries: QueueEntry[] = [];
let seq = 0;
const listeners = new Set<() => void>();
const released = new Set<string>(); // 已放行、尚未 finish 的 id

const emit = () => listeners.forEach((l) => l());

function releaseHead(): void {
  if (entries.length === 0) return;
  const sorted = entries
    .slice()
    .sort((a, b) => a.priority - b.priority || a.seq - b.seq);
  // 无抢占：任一「已放行」条目持有弹窗位（哪怕排序上已不是队首）——等它 finish
  if (sorted.some((e) => released.has(e.id))) return;
  const head = sorted[0];
  if (!head) return;
  released.add(head.id);
  head.dispatch();
}

export function enqueueDialog(id: string, priority: number, dispatch: () => void): void {
  if (entries.some((e) => e.id === id)) return; // 去重：同条目在途不重复入队
  entries = [...entries, { id, priority, seq: seq++, dispatch }];
  releaseHead();
  emit();
}

/** 条目收尾（完成/关闭）→ 出队并放行下一条目 */
export function finishDialog(id: string): void {
  const had = entries.some((e) => e.id === id);
  entries = entries.filter((e) => e.id !== id);
  released.delete(id);
  if (had) {
    releaseHead();
    emit();
  }
}

/** 登出/切换账号清空队列（防跨账号串台；放行态一并复位） */
export function clearDialogQueue(): void {
  entries = [];
  released.clear();
  emit();
}

/** 队首 id（无则 null）——测试与诊断用 */
export function dialogQueueHead(): string | null {
  if (entries.length === 0) return null;
  return entries
    .slice()
    .sort((a, b) => a.priority - b.priority || a.seq - b.seq)[0]?.id ?? null;
}

export function dialogQueueSnapshot(): string {
  return entries
    .map((e) => `${e.id}${released.has(e.id) ? '*' : ''}`)
    .join(',') || '';
}

export function subscribeDialogQueue(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}
