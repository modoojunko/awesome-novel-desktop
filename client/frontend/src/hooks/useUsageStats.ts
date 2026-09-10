import { useCallback, useEffect, useState } from "react";
import { getToken } from "../lib/auth";

const API_BASE = "/api/v1";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { "Authorization": `Bearer ${token}` } : {};
}

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
      let url = "";
      if (options.configId) url = `${API_BASE}/api-configs/${options.configId}/usage`;
      else if (options.projectId)
        url = `${API_BASE}/novels/${options.projectId}/usage`;
      else url = `${API_BASE}/api-configs/usage-summary`;
      const resp = await fetch(url, { headers: authHeaders() });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }, [options.configId, options.projectId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return { data, loading, error, refresh: fetchData };
}
