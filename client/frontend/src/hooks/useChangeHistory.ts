import { useCallback, useEffect, useState } from "react";
import type { ChangeEntry } from "../types/api-config";
import { errMessage, request } from "../lib/api";

// c-fetch-unify：手写 fetch 迁回中心栈（apiBase 整体替换默认 /api 前缀）
const V1 = "/api/v1";

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
      // 503 storage_busy 等结构化错误：request() 已把可读 detail 透成 message
      const data = await request<{ history: ChangeEntry[] }>(
        `/novels/${projectId}/model-history`,
        { apiBase: V1 },
      );
      setHistory(data.history || []);
    } catch (e) {
      setError(errMessage(e, "切换历史没读出来，可重试"));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const restoreVersion = async (entryId: string) => {
    if (!projectId) return;
    try {
      await request(`/novels/${projectId}/model-history/${entryId}/restore`, {
        apiBase: V1,
        method: "POST",
      });
    } catch (e) {
      throw new Error(errMessage(e, "恢复失败"));
    }
    await fetchHistory();
  };

  return { history, loading, error, restoreVersion, refresh: fetchHistory };
}
