/** 图像配置/资产/设置 API 客户端（c-cover-avatar 阶段 2）。
 *
 * 后端统一信封 {ok,data}；图片 URL 是相对 /api 路径，渲染时必须过 mediaUrl()，
 * 否则 VITE_API_BASE_URL 非空时 <img> 会打到前端 origin。
 */
import { getToken } from "./auth";
import { getApiBaseUrl } from "./env";
import { api, type ApiError } from "./api";

export type ImageKind = "cover" | "avatar";
export type ImageProvider =
  | "volcengine"
  | "aliyun"
  | "zhipu"
  | "openai"
  | "minimax"
  | "openai-compat";

export interface ImageConfig {
  id: string;
  name: string;
  provider: ImageProvider;
  base_url: string;
  api_key_masked: string;
  default_model: string;
  models: string[];
  declared_capabilities: Record<string, unknown>;
  is_default: boolean;
  status: "active" | "deleted";
  last_test_status?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ImageRef {
  asset_id: string;
  url: string;
  thumb_url: string;
  links?: { full: string; thumb: string };
  status?: string;
  width: number;
  height: number;
  version: number;
  source: string;
  style_key?: string | null;
  adopted_at?: string | null;
  url_expires_at?: string;
}

export interface ImageAsset extends ImageRef {
  novel_id: string;
  character_id?: string | null;
  kind: ImageKind;
  status: "candidate" | "current" | "previous";
  mime: string;
  bytes: number;
  expires_at?: string | null;
  undo_expires_at?: string | null;
  prompt_hash?: string | null;
  prompt_text?: string | null;
  negative_prompt?: string | null;
  prompt_template_version?: number | null;
  seed?: number | null;
  undo_token?: string;
}

export interface BookImageSettings {
  novel_id: string;
  style_key: string;
  cover_prompt: string;
  cover_seed: number | null;
  image_config_id: string | null;
  image_model: string;
  effective_image_config_id: string | null;
  effective_image_model: string;
  effective_source: "explicit" | "default" | "none";
}

export interface CharacterImageSettings {
  character_id: string;
  avatar_prompt: string;
  seed: number | null;
}

export type ImageJobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface ImageBatchItemState {
  id: string;
  character_id: string;
  item_index: number;
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "cancelled_billed";
  seed: number | null;
  prompt_hash: string | null;
  produced_count: number;
  billed_n: number;
  duration_ms: number;
  error_kind: string | null;
  error_message: string | null;
}

export interface ImageJob {
  id: string;
  user_id: string;
  novel_id: string;
  character_id: string | null;
  target_type: "book" | "character" | "batch";
  target_id: string;
  purpose: "generate" | "test" | "batch";
  kind: ImageKind;
  status: ImageJobStatus;
  image_config_id: string | null;
  provider: string;
  model: string;
  style_key: string | null;
  prompt_hash: string | null;
  base_seed: number | null;
  requested_n: number;
  produced_count: number;
  billed_n: number;
  cancelled_billed_count: number;
  duration_ms: number;
  error_kind: string | null;
  error_message: string | null;
  cancel_requested: boolean;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  items?: ImageBatchItemState[];
}

export interface PromptPreview {
  kind: ImageKind;
  prompt: string;
  negative_prompt: string;
  prompt_hash: string;
  prompt_template_version: number;
  style_key: string;
  size: { width: number; height: number };
  seed: number;
  candidate_seeds: number[];
  model: string | null;
  model_unbound: boolean;
  provider: string | null;
  capabilities: Record<string, boolean>;
  needs_scene?: boolean;
  uses_default_subject?: boolean;
  sources: Record<string, unknown>;
}

export const IMAGE_PROVIDERS: Array<{
  id: ImageProvider;
  label: string;
  base_url: string;
  models: string[];
  apply_url: string;
}> = [
  {
    id: "volcengine", label: "火山引擎 Seedream",
    base_url: "https://ark.cn-beijing.volces.com/api/v3",
    models: ["doubao-seedream-4-0-250828"],
    apply_url: "https://console.volcengine.com/ark",
  },
  {
    id: "aliyun", label: "阿里云百炼 Qwen-Image",
    base_url: "https://dashscope.aliyuncs.com/api/v1",
    models: ["qwen-image-2.0-pro", "qwen-image-2.0"],
    apply_url: "https://bailian.console.aliyun.com/",
  },
  {
    id: "zhipu", label: "智谱 CogView",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    models: ["cogview-4", "cogview-3-flash"],
    apply_url: "https://bigmodel.cn/console/",
  },
  {
    id: "openai", label: "OpenAI gpt-image-1",
    base_url: "https://api.openai.com/v1",
    models: ["gpt-image-1"],
    apply_url: "https://platform.openai.com/api-keys",
  },
  {
    id: "minimax", label: "MiniMax image-01",
    base_url: "https://api.minimax.chat/v1",
    models: ["image-01"],
    apply_url: "https://platform.minimaxi.com/",
  },
  {
    id: "openai-compat", label: "OpenAI 兼容",
    base_url: "",
    models: [],
    apply_url: "",
  },
];

function mediaUrl(path: string): string {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const base = getApiBaseUrl().replace(/\/$/, "");
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

async function unwrap<T>(p: Promise<unknown>): Promise<T> {
  const r = (await p) as { data?: T };
  if (!r || r.data === undefined) throw new Error("响应缺少 data");
  return r.data;
}

function httpError(message: string, status: number, code?: string): ApiError {
  const e = new Error(message) as ApiError;
  e.status = status;
  if (code) e.code = code;
  return e;
}

export const imageApi = {
  mediaUrl,

  listConfigs: (includeDeleted = false) =>
    unwrap<ImageConfig[]>(
      api.get(`/image-configs${includeDeleted ? "?include_deleted=true" : ""}`),
    ),

  createConfig: (body: {
    name: string; provider: ImageProvider; base_url: string; api_key: string;
    default_model: string; models: string[]; is_default?: boolean;
  }) => unwrap<ImageConfig>(api.post("/image-configs", body)),

  updateConfig: (id: string, body: Record<string, unknown>) =>
    unwrap<ImageConfig>(api.put(`/image-configs/${id}`, body)),

  deleteConfig: (id: string) =>
    unwrap<{
      id: string; status: string; default_image_config_id?: string | null;
      affected_book_count?: number;
    }>(
      api.delete(`/image-configs/${id}`),
    ),

  restoreConfig: (id: string) =>
    unwrap<ImageConfig>(api.post(`/image-configs/${id}/restore`)),

  listAssets: (
    novelId: string,
    params: { kind?: ImageKind; character_id?: string; status?: string; limit?: number } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.kind) q.set("kind", params.kind);
    if (params.character_id) q.set("character_id", params.character_id);
    if (params.status) q.set("status", params.status);
    q.set("limit", String(params.limit ?? 100));
    return unwrap<ImageAsset[]>(api.get(`/novels/${novelId}/image-assets?${q}`));
  },

  uploadAsset: (
    novelId: string, file: File, kind: ImageKind, characterId?: string,
    onProgress?: (percent: number) => void,
  ): Promise<ImageAsset> => new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${getApiBaseUrl()}/api/novels/${novelId}/image-assets`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100));
    };
    xhr.onerror = () => reject(new Error("网络连接失败，请重试"));
    xhr.onload = () => {
      let body: any = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* empty/non-json */ }
      if (xhr.status >= 200 && xhr.status < 300 && body?.data) {
        onProgress?.(100);
        resolve(body.data as ImageAsset);
        return;
      }
      const detail = body?.detail;
      const msg = typeof detail === "object" ? detail?.message : detail;
      reject(httpError(msg || "上传失败", xhr.status || 0, detail?.code));
    };
    const form = new FormData();
    form.append("kind", kind);
    if (characterId) form.append("character_id", characterId);
    form.append("file", file);
    xhr.send(form);
  }),

  adoptAsset: (assetId: string) =>
    unwrap<ImageAsset>(api.post(`/image-assets/${assetId}/adopt`)),

  undoAsset: (assetId: string, token: string) =>
    unwrap<{ restored_asset_id: string | null; removed_asset_id: string }>(
      api.post(`/image-assets/${assetId}/undo`, { undo_token: token }),
    ),

  deleteAsset: (assetId: string) =>
    unwrap<{ deleted_asset_id: string }>(api.delete(`/image-assets/${assetId}`)),

  refreshLinks: (assetId: string) =>
    unwrap<{ links: { full: string; thumb: string }; url_expires_at: string }>(
      api.get(`/image-assets/${assetId}/links`),
    ),

  getBookSettings: (novelId: string) =>
    unwrap<BookImageSettings>(api.get(`/novels/${novelId}/image-settings`)),

  patchBookSettings: (novelId: string, body: Record<string, unknown>) =>
    unwrap<BookImageSettings>(api.patch(`/novels/${novelId}/image-settings`, body)),

  getCharacterSettings: (novelId: string, characterId: string) =>
    unwrap<CharacterImageSettings>(
      api.get(`/novels/${novelId}/characters/${characterId}/image-settings`),
    ),

  patchCharacterSettings: (novelId: string, characterId: string, body: Record<string, unknown>) =>
    unwrap<CharacterImageSettings>(
      api.patch(`/novels/${novelId}/characters/${characterId}/image-settings`, body),
    ),

  coverPrompt: (novelId: string) =>
    unwrap<PromptPreview>(api.get(`/novels/${novelId}/image-prompt`)),

  avatarPrompt: (novelId: string, characterId: string) =>
    unwrap<PromptPreview>(
      api.get(`/novels/${novelId}/characters/${characterId}/image-prompt`),
    ),

  createImageJob: (
    novelId: string,
    body: { kind: ImageKind; character_id?: string; n?: number; purpose?: "generate" | "test" },
  ) => unwrap<ImageJob>(api.post(`/novels/${novelId}/image-jobs`, body)),

  createAvatarBatch: (novelId: string, characterIds: string[]) =>
    unwrap<ImageJob>(api.post(`/novels/${novelId}/avatar-batches`, { character_ids: characterIds })),

  listImageJobs: (
    novelId: string,
    params: { kind?: ImageKind; status?: ImageJobStatus; limit?: number } = {},
  ) => {
    const q = new URLSearchParams();
    if (params.kind) q.set("kind", params.kind);
    if (params.status) q.set("status", params.status);
    q.set("limit", String(params.limit ?? 20));
    return unwrap<ImageJob[]>(api.get(`/novels/${novelId}/image-jobs?${q}`));
  },

  getImageJob: (jobId: string) => unwrap<ImageJob>(api.get(`/image-jobs/${jobId}`)),

  cancelImageJob: (jobId: string) =>
    unwrap<ImageJob>(api.post(`/image-jobs/${jobId}/cancel`)),

  retryImageJob: (jobId: string) =>
    unwrap<ImageJob>(api.post(`/image-jobs/${jobId}/retry`)),
};
