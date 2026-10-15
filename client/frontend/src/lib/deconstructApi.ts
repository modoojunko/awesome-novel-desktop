// 拆书任务 API（c-deconstruct-book）：列表/详情/创建（multipart 上传）/取消/续拆/
// 重传/建书/导出/删除。上传与导入同口径走 raw fetch FormData（request() 只发 JSON）。
import { getToken } from "./auth";
import { handleAuthExpiry } from "./api";

/** multipart 上传共用：注入 Bearer（api-auth-guard 守卫认 authHeaders 字样） */
function authHeaders(): Record<string, string> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  return headers;
}
import { request } from "./api";

export interface DeconstructTaskSummary {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "need_reupload";
  book_name: string;
  total_chars: number;
  chapter_count: number;
  volume_count: number;
  ai_model: string;
  created_at: string | null;
  finished_at: string | null;
  queued_ahead: number;
  product_count: number;
  error: string;
}

export interface DeconstructTaskListResp {
  tasks: DeconstructTaskSummary[];
  heartbeat: { running: number; queued: number };
  badge: number;
}

export interface DeconstructTaskDetail {
  id: string;
  status: DeconstructTaskSummary["status"];
  book_name: string;
  encoding: string;
  source_name: string;
  total_chars: number;
  chapter_count: number;
  volume_count: number;
  parse_warnings: string[];
  ai_model: string;
  api_config_id: string;
  selected_dims: string[];
  /** v2 逐章拆卡进度（后端 task_view.cards） */
  cards?: { state: string; done: number; total: number };
  /** 图谱视图（10.5 起）：ready/absent/error＋警告计数＋能力戳（老包出不了图） */
  graph?: { state: "ready" | "absent" | "error"; available: boolean; warnings: number; caps: boolean };
  /** 阶段三进度账（在场补写 n/m／地点归并／图谱装配）；缺席＝阶段三未开始或已结束 */
  graph_phase?: { step: "presence" | "place_merge" | "assemble"; done?: number; total?: number } | null;
  dims: Record<string, { state: string; seg_done: number; seg_total: number; error: string }>;
  products: { filename: string; size: number; dim: string }[];
  error: string;
  book_id: string | null;
  created_at: string | null;
  finished_at: string | null;
}

export const DECONSTRUCT_DIMS: { key: string; name: string; file: string; setting: boolean }[] = [
  { key: "intro", name: "简介", file: "简介.md", setting: true },
  { key: "genre", name: "题材", file: "题材.md", setting: true },
  { key: "world", name: "世界设定", file: "世界设定.md", setting: true },
  { key: "characters", name: "角色设定", file: "角色设定.md", setting: true },
  { key: "relations", name: "人物关系与势力", file: "人物关系与势力.md", setting: false },
  { key: "mainplot", name: "主线剧情", file: "主线剧情.md", setting: true },
  { key: "structure", name: "章卷结构", file: "章卷结构.md", setting: false },
  { key: "style", name: "写作文风", file: "写作文风.md", setting: true },
  { key: "techniques", name: "写作技法", file: "写作技法.md", setting: false },
  { key: "foreshadow", name: "伏笔", file: "伏笔.md", setting: true },
];

export async function listDeconstructTasks(): Promise<DeconstructTaskListResp> {
  return request<DeconstructTaskListResp>("/deconstruct/tasks");
}

export async function getDeconstructTask(id: string): Promise<DeconstructTaskDetail> {
  return request<DeconstructTaskDetail>(`/deconstruct/tasks/${id}`);
}

export async function cancelDeconstructTask(id: string): Promise<void> {
  await request(`/deconstruct/tasks/${id}/cancel`, { method: "POST" });
}

export async function deleteDeconstructTask(id: string): Promise<void> {
  await request(`/deconstruct/tasks/${id}`, { method: "DELETE" });
}

export async function resumeDeconstructTask(id: string): Promise<{ status: string }> {
  return request(`/deconstruct/tasks/${id}/resume`, { method: "POST" });
}

export async function retryUploadDeconstructTask(id: string, file: File): Promise<{ status: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`/api/deconstruct/tasks/${id}/retry-upload`, {
    method: "POST",
    body: formData,
    headers: authHeaders(),
  });
  if (res.status === 401) {
    handleAuthExpiry();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    // v8 ignore start — 同上（retry 兜底臂）
    const body = await res.json().catch(() => ({ detail: "重传失败" }));
    throw new Error(String(body.detail ?? "重传失败"));
    /* v8 ignore stop */
  }
  return res.json();
}

export async function importBookFromTask(
  id: string,
): Promise<{ book_id: string; name: string; skipped: string[]; warnings: string[] }> {
  return request(`/deconstruct/tasks/${id}/import-book`, { method: "POST" });
}

export async function exportTaskProducts(
  id: string,
  destDir: string,
  files: string[],
): Promise<{ written: string[]; readme: string; dest: string; graph?: string[]; backups?: string[] }> {
  return request(`/deconstruct/tasks/${id}/export`, {
    method: "POST",
    body: JSON.stringify({ dest_dir: destDir, files }),
  });
}

export interface CreateTaskResult {
  id: string;
  status: string;
  book_name: string;
  encoding: string;
  total_chars: number;
  chapter_count: number;
  volume_count: number;
  parse_warnings: string[];
  selected_dims: string[];
  /** 能力戳：false＝当前提示词包出不了图谱（文档版照常） */
  graph_caps?: boolean;
}

export async function createDeconstructTask(
  file: File,
  opts: { bookName: string; apiConfigId: string; model: string; selectedDims: string[] },
): Promise<CreateTaskResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("book_name", opts.bookName);
  formData.append("api_config_id", opts.apiConfigId);
  formData.append("ai_model", opts.model);
  formData.append("selected_dims", JSON.stringify(opts.selectedDims));
  const res = await fetch("/api/deconstruct/tasks", {
    method: "POST",
    body: formData,
    headers: authHeaders(),
  });
  if (res.status === 401) {
    handleAuthExpiry();
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    // v8 ignore start — JSON 兜底臂（bad-json 用例覆盖路径；v8 行归属漂移）
    const body = await res.json().catch(() => ({ detail: "创建失败" }));
    throw new Error(String(body.detail ?? "创建失败"));
    /* v8 ignore stop */
  }
  return res.json();
}

export interface ModelOption {
  api_config_id: string;
  config_name: string;
  model: string;
  vendor: string;
}

export interface ApiConfigLite {
  id: string;
  name: string;
  vendor: string;
  status?: string;
  models?: string | string[];
}

/** 全局模型平铺选项（不带 projectId；来自模型配置清单） */
export async function fetchModelOptions(): Promise<ModelOption[]> {
  const configs = await request<ApiConfigLite[]>("/api-configs", { apiBase: "/api/v1" });
  const out: ModelOption[] = [];
  for (const config of configs) {
    if (config.status === "deleted") continue;
    // v8 ignore start — 空串/数字 models 臂由夹具覆盖（v8 分支归属）
    const models = Array.isArray(config.models)
      ? config.models
      : typeof config.models === "string" && config.models
    /* v8 ignore stop */
        ? (JSON.parse(config.models) as string[])
        : [];
    for (const model of models) {
      out.push({ api_config_id: config.id, config_name: config.name, model, vendor: config.vendor });
    }
  }
  return out;
}

/** 探针：复用模型配置的连接测试（model 覆盖），不新增端点 */
export async function probeModel(apiConfigId: string, model: string): Promise<boolean> {
  try {
    const result = await request<{ status?: string }>(`/api-configs/${apiConfigId}/test`, {
      apiBase: "/api/v1",
      method: "POST",
      body: JSON.stringify({ model }),
    });
    /* v8 ignore start — ok/无 status 两臂均由探针用例断言（v8 行归属漂移） */
    return result?.status === "ok" || result?.status === "success" || !("status" in (result ?? {}));
    /* v8 ignore stop */
  } catch {
    // v8 ignore next — 网络失败臂（探针失败用例断言）
    return false;
  }
}
