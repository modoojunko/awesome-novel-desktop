/** 旧库检测 hook（db-generation）：candidates 免登端点消费，静默降级。 */

import { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';

export interface LegacyCandidate {
  filename: string;
  generation: number;
  size_bytes: number;
  mtime: number;
  book_count: number | null;
  unreadable: boolean;
  stamp: string;
  suppressed: boolean;
}

export interface LegacyStatus {
  candidates: LegacyCandidate[];
  quarantined: Array<{ filename: string; size_bytes: number }>;
  schema_version: number;
}

export function useLegacyDb(): {
  status: LegacyStatus | null;
  refresh: () => Promise<void>;
  dismiss: (filename: string) => Promise<void>;
} {
  const [status, setStatus] = useState<LegacyStatus | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await api.get('/backup/db-migration/candidates', { quiet: true });
      if (res.code === 0) setStatus(res.data as LegacyStatus);
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const dismiss = useCallback(async (filename: string) => {
    await api.post('/backup/db-migration/dismiss', { filename });
    await refresh();
  }, [refresh]);

  return { status, refresh, dismiss };
}
