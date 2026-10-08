/**
 * 带回数据层单例（c-lossless-upgrade 5.1）：候选 + 搬运 job 全局一份数据、
 * 一处轮询——替换 useLegacyDb 在书架与账户菜单的两处独立挂载（书架请求预算
 * 门禁：空闲期零额外请求；轮询仅在「有 running 任务」时开启）。
 *
 * 状态面：
 *  - status：/backup/db-migration/candidates 快照（含 carried/suppressed 两字段）
 *  - job：/backup/db-migration/status 快照（state running 时轮询；done 后停轮询、
 *    自动刷 candidates——carried 翻转、常驻行换态）
 */

import { useSyncExternalStore } from 'react';
import { api } from '@/lib/api';
import type { LegacyStatus } from '@/hooks/useLegacyDb';

export interface CarryManifestBook { name: string; words: number }
export interface CarryManifest {
  books: CarryManifestBook[];
  books_total: number;
  configs: Array<{ name: string }>;
  configs_total: number;
}

/** candidates 载荷（c-lossless-upgrade：carried/suppressed 两字段 + recommended 挂 manifest） */
export interface CarryCandidate {
  filename: string;
  stamp: string;
  recommended: boolean;
  carried?: boolean;
  suppressed?: boolean;
  unreadable: boolean;
  book_count: number | null;
  manifest?: CarryManifest | null;
}

export interface CarryJob {
  state: 'idle' | 'running' | 'done' | 'error';
  kind?: string;
  progress?: {
    stage: string;
    tables_total?: number;
    tables_done?: number;
    table?: string;
    rows_inserted?: number;
  } | null;
  report?: CarryReport | null;
}

export interface CarryReport {
  status: string;
  reason?: string;
  dead_keys?: number | null;
  complete?: boolean | null;
  book_count_source?: number | null;
  book_count_migrated?: number | null;
  tables_skipped?: Array<{ table: string; reason?: string }>;
  fk_violations?: unknown[];
}

interface CarryState {
  status: LegacyStatus | null;
  job: CarryJob | null;
}

let state: CarryState = { status: null, job: null };
let inflightCandidates = false;
let pollTimer: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();

const emit = () => listeners.forEach((l) => l());
const set = (patch: Partial<CarryState>) => {
  state = { ...state, ...patch };
  emit();
};

export async function refreshCarry(): Promise<void> {
  if (inflightCandidates) return; // 并发去重（书架+账户菜单同时挂载只发一请求）
  inflightCandidates = true;
  try {
    const res = await api.get('/backup/db-migration/candidates', { quiet: true });
    if (res.code === 0) set({ status: res.data as LegacyStatus });
  } catch {
    /* 静默降级：旧数据检测失败不阻塞书架 */
  } finally {
    inflightCandidates = false;
  }
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function pollOnce() {
  try {
    const res = await api.get('/backup/db-migration/status', { quiet: true });
    const job = (res.data ?? null) as CarryJob | null;
    set({ job });
    if (job?.state === 'running' && job.kind !== 'migration') {
      // 非 migration 的 job（备份/导出）不属本 store 观察面
      stopPoll();
    } else if (job?.state !== 'running') {
      stopPoll();
      await refreshCarry(); // done/error → 候选态翻转（carried/常驻行换态）
    }
  } catch {
    /* 轮询失败静默重试（下一拍） */
  }
}

/** 附着/启动搬运后开启轮询（已开则幂等） */
export function watchCarryJob() {
  if (pollTimer) return;
  void pollOnce();
  pollTimer = setInterval(() => void pollOnce(), 1000);
}

/** 应用启动/进入书架时的一次性探测（job 若在跑顺带附着） */
export async function probeCarry() {
  await refreshCarry();
  try {
    const res = await api.get('/backup/db-migration/status', { quiet: true });
    const job = (res.data ?? null) as CarryJob | null;
    if (job?.state === 'running' && job.kind === 'migration') {
      set({ job });
      watchCarryJob();
    }
  } catch { /* 静默 */ }
}

export function snoozeCarry(filename: string) {
  return api.post('/backup/db-migration/dismiss', { filename }, { quiet: true })
    .then(() => refreshCarry());
}

export function subscribeCarry(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function carrySnapshot(): CarryState {
  return state;
}

export function useCarryStore(): CarryState {
  return useSyncExternalStore(subscribeCarry, carrySnapshot, carrySnapshot);
}

/** 测试复位 */
export function resetCarryStoreForTests() {
  stopPoll();
  state = { status: null, job: null };
  emit();
}
