import { useCallback, useEffect, useState } from "react";
import type { ApiConfig, FlatModelOption, ModelStatus } from "../types/api-config";
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
  let status: ModelStatus = "no_key";
  if (!hasKeys) status = "no_key";
  else if (!currentConfigId) status = "no_model";
  else if (configs.find((c) => c.id === currentConfigId)) status = "configured";
  else status = "invalid";

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
