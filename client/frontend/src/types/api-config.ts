export type VendorId = 'openai' | 'anthropic' | 'deepseek' | 'glm' | 'kimi' | 'qwen' | 'ollama' | 'openai-compat';
export type ApiFormat = 'openai' | 'anthropic';
export type ConnectionStatus = 'ok' | 'auth_error' | 'timeout' | 'network_error' | 'rate_limited' | 'unknown' | 'untested';
export type ModelStatus = 'no_key' | 'no_model' | 'configured' | 'invalid';

/** 后端判定层下发的 AI 就绪态（与 detail.reason 同枚举，D13）。 */
export type AiState = 'ready' | 'member_required' | 'no_key' | 'missing_model' | 'invalid';
export type ChangeType = 'initial' | 'switch' | 'clear' | 'restore';

export interface ApiConfig {
  id: string;
  name: string;
  vendor: VendorId;
  vendor_display_name: string;
  api_format: ApiFormat;
  base_url: string;
  api_key_masked: string;
  status: string;
  last_test_status: ConnectionStatus | null;
  last_test_error: string | null;
  last_tested_at: string | null;
  models: string[];
  models_updated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FlatModelOption {
  api_config_id: string;
  config_name: string;
  model: string;
  vendor: VendorId;
}

export interface UsageSummary {
  total_all_time: number;
  total_this_month: number;
  total_today: number;
  by_config: Array<{ config_id: string; config_name: string; tokens: number }>;
  queried_at: string;
}

export interface NovelUsageStats {
  total_tokens: number;
  by_model: Array<{ model: string; tokens: number }>;
  by_operation: Array<{ operation: string; tokens: number }>;
}

export interface ChangeEntry {
  id: string;
  changed_at: string;
  old_config_name: string | null;
  new_config_name: string | null;
  old_model: string | null;
  new_model: string | null;
  change_type: ChangeType;
}
