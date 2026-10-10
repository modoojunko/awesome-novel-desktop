/** 旧版数据检测 hook（c-db-per-version）：candidates 免登端点消费，静默降级。
 *
 * 载荷改版本语义（`version`/`kind`/`legacy_generation`/`recommended`＋顶层
 * `current_version`）：`generation`/`schema_version` 代数口径已随库文件名换代退役。
 * `recommended` **由后端单源给出**——前端不得按列表顺序推断推荐位。
 */

import { useCallback, useEffect } from 'react';
import { refreshCarry, snoozeCarry, useCarryStore } from '@/lib/carryStore';

export type LegacyCandidateKind = 'semver' | 'legacy' | 'gen0' | 'sentinel' | 'mismatch';

export interface LegacyCandidate {
  filename: string;
  /** 语义化版本（legacy/gen0/sentinel 为 null） */
  version: string | null;
  kind: LegacyCandidateKind;
  /** 遗留代数名（纯数字 novel-v{k}.db）的代际号，其余为 null */
  legacy_generation: number | null;
  size_bytes: number;
  /** 三件套 max(mtime)：只看主文件会被 WAL 滞后骗到 */
  mtime: number;
  book_count: number | null;
  unreadable: boolean;
  recommended: boolean;
  stamp: string;
  suppressed: boolean;
  /** c-lossless-upgrade：本次已带回（migration.last 完整达成才算） */
  carried?: boolean;
  /** c-carry-degrade-remigrate：曾带回但不完整（书架不自动重弹整卡，提醒行承接） */
  carried_partial?: boolean;
  /** c-lossless-upgrade：recommended 候选的只读内容清单（后端只挂 recommended） */
  manifest?: {
    books: Array<{ name: string; words: number }>;
    books_total: number;
    configs: Array<{ name: string }>;
    configs_total: number;
  } | null;
}

export interface QuarantinedLibrary {
  filename: string;
  size_bytes: number;
  mtime: number;
}

export interface LegacyStatus {
  candidates: LegacyCandidate[];
  quarantined: QuarantinedLibrary[];
  current_version: string;
}

/**
 * 可搬运候选（不可读件只作只读展示，不提供带回动作）。
 */
export function migratableCandidates(status: LegacyStatus | null): LegacyCandidate[] {
  return (status?.candidates ?? []).filter((c) => !c.unreadable);
}

/**
 * 推荐源：后端给的推荐位优先，否则列表首位（列表已按后端顺序排好）。
 */
export function recommendedCandidate(status: LegacyStatus | null): LegacyCandidate | null {
  const items = migratableCandidates(status);
  return items.find((c) => c.recommended) ?? items[0] ?? null;
}

/**
 * c-lossless-upgrade 5.1：本 hook 已收敛为 carryStore 单例的薄壳——书架与账户
 * 菜单共享同一份 candidates 请求（此前两处挂载各发一次，挤占书架请求预算）。
 */
export function useLegacyDb(): {
  status: LegacyStatus | null;
  refresh: () => Promise<void>;
  dismiss: (filename: string) => Promise<void>;
} {
  const { status } = useCarryStore();

  useEffect(() => {
    void refreshCarry();
  }, []);

  const refresh = useCallback(async () => {
    await refreshCarry();
  }, []);

  const dismiss = useCallback(async (filename: string) => {
    await snoozeCarry(filename);
  }, []);

  return { status, refresh, dismiss };
}
