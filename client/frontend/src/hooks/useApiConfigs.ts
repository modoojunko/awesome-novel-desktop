// 模型配置域数据源（c-fetch-unify 收编）：原 9 处手写 fetch + 自拼 authHeaders
// 全部迁回中心栈 request()——401 踢出／503 全局提示／member_required 广播不再缺位。
//
// c-model-list-auto-refresh：状态收进 lib/modelCatalog 模块级 store（多实例共享同一份
// 配置与清单）。后台保鲜（ensure-models-fresh）成功后所有订阅者一起更新——本书模型、
// 助手底栏、拆书页不再各自读一份过期快照。
import { useCallback, useEffect } from "react";
import type { ApiConfig, FetchModelsResult, ThinkingEffort } from "../types/api-config";
import { request } from "../lib/api";
import {
  loadModelCatalog,
  patchModelCatalogStatus,
  removeModelCatalogConfig,
  upsertModelCatalogConfig,
  useModelCatalog,
} from "../lib/modelCatalog";

const V1 = "/api/v1";

export function useApiConfigs() {
  const { configs, loading, error } = useModelCatalog();

  useEffect(() => {
    void loadModelCatalog();
  }, []);

  const addConfig = async (body: {
    name: string;
    vendor_id: string;
    base_url: string;
    api_key: string;
    api_format: "openai" | "anthropic";
    models?: string[];
    thinking_enabled?: boolean;
    thinking_effort?: ThinkingEffort;
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
    upsertModelCatalogConfig(config);
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
    upsertModelCatalogConfig(config);
    return config;
  };

  const deleteConfig = async (
    id: string,
  ): Promise<{ affected_projects: number; affected_names: string[] }> => {
    const result = await request<{ affected_projects: number; affected_names: string[] }>(
      `/api-configs/${id}`,
      { apiBase: V1, method: "DELETE" },
    );
    removeModelCatalogConfig(id);
    return result;
  };

  const restoreConfig = async (id: string): Promise<ApiConfig> => {
    // 撤销删除：后端软删后 restore 复活同一 id
    const config = await request<ApiConfig>(`/api-configs/${id}/restore`, {
      apiBase: V1,
      method: "POST",
    });
    upsertModelCatalogConfig(config);
    return config;
  };

  const refresh = loadModelCatalog;

  // 后台状态探针（挂载/轮询形态）：保持静默降级——非 ok/网络失败不惊动用户
  const refreshStatus = useCallback(async () => {
    try {
      const data = await request<Array<Partial<ApiConfig> & { id: string }>>(
        `/api-configs/status`,
        { apiBase: V1, quiet: true },
      );
      patchModelCatalogStatus(
        data.map((entry) => ({
          id: entry.id,
          last_test_status: entry.last_test_status ?? null,
          models: entry.models ?? undefined,
        })),
      );
    } catch {
      /* 探测失败保持静默（原口径）；真实故障由 loadModelCatalog 的错误态兜底 */
    }
  }, []);

  // 已存密钥轻探针（c-model-list-auto-refresh）：编辑态 Key 未重填时拉清单。
  // 成功带清单就顺手回填列表卡片（弹窗内的提交拼装另由页面用返回值更新 editConfig）。
  const refreshModels = async (id: string): Promise<FetchModelsResult> => {
    const result = await request<FetchModelsResult>(`/api-configs/${id}/refresh-models`, {
      apiBase: V1,
      method: "POST",
    });
    if (result.ok && result.models) {
      patchModelCatalogStatus([
        {
          id,
          models: result.models,
          ...(result.models_updated_at
            ? { models_updated_at: result.models_updated_at }
            : {}),
        },
      ]);
    }
    return result;
  };

  // model 可选（编辑弹窗改选模型后试连）：探针优先模型覆盖，缺省用已存 models 首项
  const testConfig = async (
    id: string,
    model?: string,
    thinking?: { thinking_enabled: boolean; thinking_effort: ThinkingEffort },
  ): Promise<{ ok: boolean; status: string; models?: string[]; error?: string }> => {
    const overrides = {
      ...(model ? { model } : {}),
      ...(thinking ?? {}),
    };
    const result = await request<
      Partial<ApiConfig> & { ok: boolean; status: string; error?: string }
    >(`/api-configs/${id}/test`, {
      apiBase: V1,
      method: "POST",
      ...(Object.keys(overrides).length
        ? { body: JSON.stringify(overrides) }
        : {}),
    });
    // 持久化的连接状态/清单回填共享 store（其它选择器一起看到）
    if (result.ok || result.status) {
      patchModelCatalogStatus([
        {
          id,
          last_test_status: (result.status ?? undefined) as
            | ApiConfig["last_test_status"]
            | undefined,
          models: result.models ?? undefined,
        },
      ]);
    }
    return result;
  };

  const testRawConfig = async (body: {
    vendor_id: string;
    base_url: string;
    api_key: string;
    api_format: "openai" | "anthropic";
    model?: string | null;
    thinking_enabled?: boolean;
    thinking_effort?: ThinkingEffort;
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
