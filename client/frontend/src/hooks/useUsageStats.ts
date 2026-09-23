import { useCallback, useEffect, useState } from "react";
import { errMessage, request } from "../lib/api";

// c-fetch-unify：手写 fetch 迁回中心栈
const V1 = "/api/v1";

type Period = "month" | "week" | "custom";

export function useUsageStats(options: {
  configId?: string;
  projectId?: string;
  period?: Period;
  startDate?: string;
  endDate?: string;
}) {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      let path = "";
      if (options.configId) path = `/api-configs/${options.configId}/usage`;
      else if (options.projectId)
        path = `/novels/${options.projectId}/usage`;
      else path = `/api-configs/usage-summary`;
      const json = await request(path, { apiBase: V1 });
      setData(json);
    } catch (e) {
      setError(errMessage(e, "用量统计没读出来，可重试"));
    } finally {
      setLoading(false);
    }
  }, [options.configId, options.projectId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refresh: fetchData };
}
