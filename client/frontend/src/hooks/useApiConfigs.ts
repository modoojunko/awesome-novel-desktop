// 模型配置域数据源（c-fetch-unify 收编）：原 9 处手写 fetch + 自拼 authHeaders
// 全部迁回中心栈 request()——401 踢出／503 全局提示／member_required 广播不再缺位。
import { useCallback, useEffect, useState } from "react";
import type { ApiConfig, FetchModelsResult } from "../types/api-config";
import { errMessage, request } from "../lib/api";

const V1 = "/api/v1";

export function useApiConfigs() {
  const [configs, setConfigs] = useState<ApiConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConfigs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await request<ApiConfig[]>(`/api-configs`, { apiBase: V1 });
      setConfigs(data);
    } catch (e) {
      // 本页就是 /config：503 只会是云托管冷启动，就地报错不强跳
      const msg = (e as { status?: number })?.status === 503
        ? "云端服务唤醒中，请稍后重试"
        : errMessage(e, "加载配置失败");
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  const addConfig = async (body: {
    name: string;
    vendor_id: string;
    base_url: string;
    api_key: string;
    api_format: "openai" | "anthropic";
    models?: string[];
    /** relay（中转站）必须显式登记：域名检测对任意站方地址必然落兜底（c-relay-vendor-entry） */
    vendor_override?: string;
  }): Promise<ApiConfig> => {
    let config: ApiConfig;
    try {
      config = await request<ApiConfig>(`/api-configs`, {
        apiBase: V1,
        method: "POST",
        body: JSON.stringify(body),
      });
    } catch (e) {
      if ((e as { status?: number })?.status === 409) throw new Error("名称已被使用");
      throw e;
    }
    setConfigs((prev) => [config, ...prev]);
    return config;
  };

  const updateConfig = async (
    id: string,
    body: Record<string, any>,
  ): Promise<ApiConfig> => {
    let config: ApiConfig;
    try {
      config = await request<ApiConfig>(`/api-configs/${id}`, {
        apiBase: V1,
        method: "PUT",
        body: JSON.stringify(body),
      });
    } catch (e) {
      if ((e as { status?: number })?.status === 409) throw new Error("名称已被使用");
      throw e;
    }
    setConfigs((prev) => prev.map((c) => (c.id === id ? config : c)));
    return config;
  };

  const deleteConfig = async (
    id: string,
  ): Promise<{ affected_projects: number; affected_names: string[] }> => {
    const result = await request<{ affected_projects: number; affected_names: string[] }>(
      `/api-configs/${id}`,
      { apiBase: V1, method: "DELETE" },
    );
    setConfigs((prev) => prev.filter((c) => c.id !== id));
    return result;
  };

  const restoreConfig = async (id: string): Promise<ApiConfig> => {
    // 撤销删除：后端软删后 restore 复活同一 id
    const config = await request<ApiConfig>(`/api-configs/${id}/restore`, {
      apiBase: V1,
      method: "POST",
    });
    setConfigs((prev) => [config, ...prev]);
    return config;
  };

  const refresh = fetchConfigs;

  // 后台状态探针（挂载/轮询形态）：保持静默降级——非 ok/网络失败不惊动用户
  const refreshStatus = useCallback(async () => {
    try {
      const data = await request<Array<Partial<ApiConfig> & { id: string }>>(
        `/api-configs/status`,
        { apiBase: V1, quiet: true },
      );
      setConfigs((prev) =>
        prev.map((c) => {
          const statusEntry = data.find((s) => s.id === c.id);
          return statusEntry
            ? {
                ...c,
                last_test_status: statusEntry.last_test_status ?? null,
                models: statusEntry.models ?? c.models,
              }
            : c;
        }),
      );
    } catch {
      /* 探测失败保持静默（原口径）；真实故障由 fetchConfigs 的错误态兜底 */
    }
  }, []);

  const refreshModels = async (id: string) => {
    return request(`/api-configs/${id}/refresh-models`, { apiBase: V1, method: "POST" });
  };

  const testConfig = async (id: string): Promise<{ ok: boolean; status: string; models?: string[]; error?: string }> => {
    const result = await request<
      Partial<ApiConfig> & { ok: boolean; status: string; error?: string }
    >(`/api-configs/${id}/test`, { apiBase: V1, method: "POST" });
    // Refresh configs to pick up persisted test status
    if (result.ok || result.status) {
      setConfigs((prev) =>
        prev.map((c) =>
          c.id === id
            ? {
                ...c,
                last_test_status: (result.status ?? c.last_test_status) as ApiConfig["last_test_status"],
                models: result.models ?? c.models,
              }
            : c,
        ),
      );
    }
    return result;
  };

  const testRawConfig = async (body: {
    vendor_id: string;
    base_url: string;
    api_key: string;
    api_format: "openai" | "anthropic";
    model?: string | null;
  }): Promise<{ ok: boolean; status: string; models?: string[]; error?: string }> => {
    return request(`/api-configs/test-connection`, {
      apiBase: V1,
      method: "POST",
      body: JSON.stringify(body),
    });
  };

  // 只拉清单轻探针（c-api-config-auto-models）：表单「Key 失焦自动拉清单」用，零生成调用
  const fetchRawModels = async (body: {
    vendor_id: string;
    base_url: string;
    api_key: string;
    api_format: "openai" | "anthropic";
  }): Promise<FetchModelsResult> => {
    return request(`/api-configs/fetch-models`, {
      apiBase: V1,
      method: "POST",
      body: JSON.stringify(body),
    });
  };

  return {
    configs,
    loading,
    error,
    addConfig,
    updateConfig,
    deleteConfig,
    restoreConfig,
    refresh,
    refreshStatus,
    refreshModels,
    testConfig,
    testRawConfig,
    fetchRawModels,
  };
}
