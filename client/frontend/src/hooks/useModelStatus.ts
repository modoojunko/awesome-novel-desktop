// 模型就绪态与选型（c-fetch-unify 收编）：手写 fetch 迁回中心栈 request()。
// fetchModel 失败不再静默停留旧值——错误态可见（c-silent-data-guards 同型口径）。
import { useCallback, useEffect, useState } from "react";
import type { AiState, FlatModelOption, ModelStatus } from "../types/api-config";
import { useApiConfigs } from "./useApiConfigs";
import { errMessage, request } from "../lib/api";

const V1 = "/api/v1";

export function useModelStatus(projectId: string | undefined) {
  const { configs, loading: configsLoading, updateConfig, refresh: refreshConfigs } = useApiConfigs();
  const [currentConfigId, setCurrentConfigId] = useState<string | null>(null);
  const [currentConfigName, setCurrentConfigName] = useState<string | null>(null);
  const [currentModel, setCurrentModel] = useState<string | null>(null);
  // D13：就绪态由后端判定层下发，前端只消费（不再本地推导四态）
  const [aiState, setAiState] = useState<AiState>("no_key");
  const [aiMessage, setAiMessage] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchModel = useCallback(async () => {
    if (!projectId) {
      setLoading(false);
      return;
    }
    try {
      const data = await request<{
        api_config_id?: string;
        config_name?: string;
        model?: string;
        ai_state?: AiState;
        message?: string;
      }>(`/novels/${projectId}/ai-model`, { apiBase: V1 });
      setCurrentConfigId(data.api_config_id ?? null);
      setCurrentConfigName(data.config_name || null);
      setCurrentModel(data.model ?? null);
      if (data.ai_state) setAiState(data.ai_state as AiState);
      setAiMessage(data.message ?? "");
      setError(null);
    } catch (e) {
      // 失败可见：就绪态不静默停留旧值误导「可写」（返回值仍保留上一次快照供展示）
      setError(errMessage(e, "模型状态没读出来，可重试"));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchModel();
  }, [fetchModel]);

  const hasKeys = configs.length > 0;
  // 模型面板用的四态 = 后端 ai_state 的投影（同一事实源，不再本地判）
  const statusMap: Record<AiState, ModelStatus> = {
    ready: "configured",
    member_required: "no_key",
    no_key: "no_key",
    missing_model: "no_model",
    invalid: "invalid",
    // 写作能力包未就绪（c-prompt-pack-client）：模型配置本身可能完好——按 configured
    // 投影，缺件引导由 PromptPackCard 承担，不在此误报「没配 Key」
    prompts_missing: "configured",
  };
  const status: ModelStatus = statusMap[aiState] ?? "no_key";

  // Build flat model options
  const modelOptions: FlatModelOption[] = [];
  for (const config of configs) {
    if (config.models && config.models.length > 0) {
      for (const model of config.models) {
        modelOptions.push({
          api_config_id: config.id,
          config_name: config.name,
          model,
          vendor: config.vendor,
        });
      }
    }
  }

  const selectModel = async (
    apiConfigId: string | null,
    model: string | null,
  ) => {
    if (!projectId) return;
    // 绑定校验 400：request() 已把后端可读 detail 透成 message（前端保留 draft + 行内报错，D12）
    await request(`/novels/${projectId}/ai-model`, {
      apiBase: V1,
      method: "PUT",
      body: JSON.stringify({ api_config_id: apiConfigId, model }),
    });
    setCurrentConfigId(apiConfigId);
    setCurrentModel(model);
    await fetchModel();
  };

  /** 该配置的候选模型 id（端点不提供 /models 时的起点；不触网）。
   *  探测类：失败静默回空（quiet 不踢出），不阻塞补模型路径。 */
  const fetchCandidates = useCallback(async (configId: string) => {
    try {
      return await request<{ candidates: string[]; note: string }>(
        `/api-configs/${configId}/model-candidates`,
        { apiBase: V1, quiet: true },
      );
    } catch {
      return { candidates: [] as string[], note: "" };
    }
  }, []);

  /** 给某个配置补模型 id（供应商不提供 /models 列表时的手动出口）。 */
  const addModelToConfig = useCallback(
    async (configId: string, modelId: string) => {
      const cfg = configs.find((c) => c.id === configId);
      const next = [...(cfg?.models ?? []), modelId];
      await updateConfig(configId, { models: next });
      await refreshConfigs();
    },
    [configs, updateConfig, refreshConfigs],
  );

  return {
    status,
    aiState,
    aiMessage,
    /** 配置列表（卡片分组头：名称/供应商/连接状态徽标）。 */
    configs,
    /** 补模型后刷新配置清单。 */
    refreshConfigs,
    addModelToConfig,
    fetchCandidates,
    modelOptions,
    currentModel,
    currentConfigId,
    currentConfigName,
    hasKeys,
    loading: loading || configsLoading,
    error,
    selectModel,
    refresh: fetchModel,
  };
}
