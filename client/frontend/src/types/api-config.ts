export type VendorId = 'openai' | 'anthropic' | 'deepseek' | 'glm' | 'kimi' | 'qwen' | 'ollama' | 'openai-compat';
export type ApiFormat = 'openai' | 'anthropic';
export type ConnectionStatus = 'ok' | 'auth_error' | 'endpoint_mismatch' | 'timeout' | 'network_error' | 'rate_limited' | 'unknown' | 'untested';
export type ModelStatus = 'no_key' | 'no_model' | 'configured' | 'invalid';

/** 后端判定层下发的 AI 就绪态（与 detail.reason 同枚举，D13）。 */
// prompts_missing（c-prompt-pack-client 4.1）：写作能力包未就绪——与后端 AI_STATES 同批（D13）
export type AiState =
  | 'ready'
  | 'member_required'
  | 'no_key'
  | 'missing_model'
  | 'invalid'
  | 'prompts_missing';
export type ChangeType = 'initial' | 'switch' | 'clear' | 'restore';

/** 思考强度（c-thinking-config）：GLM-5.3 契约三档 reasoning_effort（low 轻度/high 增强/max 深度）。 */
export type ThinkingEffort = 'low' | 'high' | 'max';

export interface ApiConfig {
  id: string;
  name: string;
  vendor: VendorId;
  vendor_display_name: string;
  api_format: ApiFormat;
  /** 思考开关（c-thinking-config）：开＝thinking:enabled＋reasoning_effort；关＝disabled（现状语义） */
  thinking_enabled: boolean;
  thinking_effort: ThinkingEffort;
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

/** 按次模型对（c-prose-model-select）：生成正文弹窗的「生成模型」选择位。
 *  仅本次生成生效——不落库、不改本书绑定（`GET /novels/{id}/ai-model` 不变）。 */
export interface ModelSelection {
  api_config_id: string;
  model: string;
}

/** 只拉清单轻探针结果（c-api-config-auto-models）：candidates/note 仅端点不提供清单时出现。 */
export interface FetchModelsResult {
  ok: boolean;
  status: ConnectionStatus | 'ok';
  models?: string[] | null;
  candidates?: string[];
  note?: string;
  error?: string;
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
