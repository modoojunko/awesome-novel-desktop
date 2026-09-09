import { useCallback, useEffect, useState } from "react";
import type { AiState, FlatModelOption, ModelStatus } from "../types/api-config";
import { useApiConfigs } from "./useApiConfigs";
import { getToken } from "../lib/auth";

const API_BASE = "/api/v1";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { "Authorization": `Bearer ${token}` } : {};
}

export function useModelStatus(projectId: string | undefined) {
  const { configs, loading: configsLoading } = useApiConfigs();
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
      const resp = await fetch(`${API_BASE}/novels/${projectId}/ai-model`, { headers: authHeaders() });
      if (resp.ok) {
        const data = await resp.json();
        setCurrentConfigId(data.api_config_id);
        setCurrentConfigName(data.config_name || null);
        setCurrentModel(data.model);
        if (data.ai_state) setAiState(data.ai_state as AiState);
        setAiMessage(data.message || "");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
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
    const resp = await fetch(`${API_BASE}/novels/${projectId}/ai-model`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ api_config_id: apiConfigId, model }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    setCurrentConfigId(apiConfigId);
    setCurrentModel(model);
  };

  return {
    status,
    aiState,
    aiMessage,
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
