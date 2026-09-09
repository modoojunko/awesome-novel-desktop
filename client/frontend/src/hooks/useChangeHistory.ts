import { useCallback, useEffect, useState } from "react";
import type { ChangeEntry } from "../types/api-config";
import { getToken } from "../lib/auth";

const API_BASE = "/api/v1";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { "Authorization": `Bearer ${token}` } : {};
}

export function useChangeHistory(projectId: string | undefined) {
  const [history, setHistory] = useState<ChangeEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    if (!projectId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(
        `${API_BASE}/novels/${projectId}/model-history`,
        { headers: authHeaders() },
      );
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      setHistory(data.history || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const restoreVersion = async (entryId: string) => {
    if (!projectId) return;
    const resp = await fetch(
      `${API_BASE}/novels/${projectId}/model-history/${entryId}/restore`,
      { method: "POST", headers: authHeaders() },
    );
    if (resp.status === 400) {
      const err = await resp.json();
      throw new Error(err.detail || "恢复失败");
    }
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    await fetchHistory();
  };

  return { history, loading, error, restoreVersion, refresh: fetchHistory };
}
