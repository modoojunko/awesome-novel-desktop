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
  /** v2 逐章拆卡进度（后端 task_view.cards）；eta_seconds＝按实际速率外推的剩余秒数 */
  cards?: { state: string; done: number; total: number; eta_seconds?: number | null };
  /** 当前动作账（每次模型调用前写）：label＋距今秒数；缺席＝空闲/终态 */
  activity?: { label: string; age_seconds?: number | null } | null;
  /** 图谱视图（10.5 起）：ready/absent/error＋警告计数＋能力戳（老包出不了图）；
   *  error＝装配失败原因（state=error 时非空，供详情页直接呈现） */
  graph?: {
    state: "ready" | "absent" | "error";
    available: boolean;
    warnings: number;
    caps: boolean;
    error?: string;
  };
  /** 阶段三进度账（在场补写 n/m／地点归并／图谱装配）；缺席＝阶段三未开始或已结束 */
  graph_phase?: { step: "presence" | "place_merge" | "assemble"; done?: number; total?: number } | null;
  dims: Record<string, {
    state: string;
    seg_done: number;
    seg_total: number;
    error: string;
    eta_seconds?: number | null;
    /** 降级注记（c-deconstruct-resilience）：分段稿/部分内容被拒绝等原因，warn 呈现 */
    degraded?: string;
  }>;
  products: { filename: string; size: number; dim: string }[];
  error: string;
  /** 失败归因（c-deconstruct-resilience）：auth/config/route/provider_unavailable/
   *  stalled/timeout/content_filter/truncated/invalid_output/rate_limit——失败面板按它给出口 */
  error_kind?: string;
  /** 任务级告警账：单元隔离的章级/批级失败留痕（不再「全绿但缺章」） */
  warnings?: string[];
  /** 换模型续拆历史：append-only */
  model_history?: { api_config_id: string; ai_model: string; at: string }[];
  /** 调用账（按阶段聚合）：calls/attempts/failures/tokens/duration */
  stats?: Record<string, {
    calls: number;
    failures: number;
    attempts: number;
    duration_ms: number;
    tokens_in: number;
    tokens_out: number;
    by_kind?: Record<string, number>;
  }>;
  /** 运行监控账（c-deconstruct-monitor）：仅排队/运行态有，终态 null */
  monitor?: DeconstructMonitor | null;
  book_id: string | null;
  created_at: string | null;
  finished_at: string | null;
}

/** 运行监控账（c-deconstruct-monitor）：单元账只读聚合——在途＋归并批进度＋近 5 分钟
 * 速度窗＋最近调用流水（派发即现，running 行 ok=false＋running=true）；reduce_state 检查点不计。 */
export interface DeconstructMonitor {
  concurrency: number;
  in_flight: number;
  batches: { done: number; total: number };
  /** 本次任务 Token 消耗（完成时入账；随轮询刷新） */
  tokens: { in: number; out: number; total: number };
  speed: {
    window_s: number;
    done: number;
    fail: number;
    avg_ms: number | null;
    out_tokens: number;
    total: number;
  };
  recent: {
    at: string;
    label: string;
    running: boolean;
    duration_ms: number;
    tokens_out: number;
    ok: boolean;
    reason: string;
  }[];
}

export const DECONSTRUCT_DIMS: {
  key: string;
  name: string;
  file: string;
  setting: boolean;
  /** 建书弹窗默认勾选（c-deconstruct-style-transfer）：技法并入文风注入正文，默认带上 */
  book?: boolean;
}[] = [
  { key: "intro", name: "简介", file: "简介.md", setting: true },
  { key: "genre", name: "题材", file: "题材.md", setting: true },
  { key: "world", name: "世界设定", file: "世界设定.md", setting: true },
  { key: "characters", name: "角色设定", file: "角色设定.md", setting: true },
  { key: "relations", name: "人物关系与势力", file: "人物关系与势力.md", setting: false },
  { key: "mainplot", name: "主线剧情", file: "主线剧情.md", setting: true },
  { key: "structure", name: "章卷结构", file: "章卷结构.md", setting: false },
  { key: "style", name: "写作文风", file: "写作文风.md", setting: true },
  { key: "techniques", name: "写作技法", file: "写作技法.md", setting: false, book: true },
  { key: "foreshadow", name: "伏笔", file: "伏笔.md", setting: true },
];

export async function listDeconstructTasks(): Promise<DeconstructTaskListResp> {
  return request<DeconstructTaskListResp>("/deconstruct/tasks");
}

export async function getDeconstructTask(id: string): Promise<DeconstructTaskDetail> {
  return request<DeconstructTaskDetail>(`/deconstruct/tasks/${id}`);
}

/** 产物 md 全文（结果目录「点文件名预览」用，c-deconstruct-product-preview）；
 * 文件名合法性由后端按产物清单校验（清单外 404）。 */
export async function getDeconstructProduct(
  id: string,
  filename: string,
): Promise<{ filename: string; content: string }> {
  return request(`/deconstruct/tasks/${id}/products/${encodeURIComponent(filename)}`);
}

/** 证据报告（c-deconstruct-evidence-report）：作家 md 去证据后，证据章节/可信度/
 * 说明/原文佐证按维度分组在弹窗呈现；后端由任务资料 JSON 现渲染，存量任务同样可看。 */
export interface DeconstructEvidenceCell {
  label: string;
  value: string;
}
export interface DeconstructEvidenceItem {
  head: string;
  cells: DeconstructEvidenceCell[];
}
export interface DeconstructEvidenceSection {
  title: string;
  items: DeconstructEvidenceItem[];
}
export interface DeconstructEvidenceDim {
  dim: string;
  name: string;
  file?: string;
  confidence: string;
  sections: DeconstructEvidenceSection[];
}
export interface DeconstructEvidence {
  task_id: string;
  dims: DeconstructEvidenceDim[];
}

export async function getDeconstructEvidence(id: string): Promise<DeconstructEvidence> {
  return request<DeconstructEvidence>(`/deconstruct/tasks/${id}/evidence`);
}

export async function cancelDeconstructTask(id: string): Promise<void> {
  await request(`/deconstruct/tasks/${id}/cancel`, { method: "POST" });
}

export async function deleteDeconstructTask(id: string): Promise<void> {
  await request(`/deconstruct/tasks/${id}`, { method: "DELETE" });
}

export async function resumeDeconstructTask(
  id: string,
  opts?: { apiConfigId?: string; model?: string },
): Promise<{ status: string }> {
  const body =
    opts?.apiConfigId || opts?.model
      ? { api_config_id: opts.apiConfigId, ai_model: opts.model }
      : {};
  return request(`/deconstruct/tasks/${id}/resume`, { method: "POST", body: JSON.stringify(body) });
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
  items?: string[],
): Promise<{ book_id: string; name: string; skipped: string[]; warnings: string[] }> {
  return request(`/deconstruct/tasks/${id}/import-book`, {
    method: "POST",
    body: JSON.stringify(items ? { items } : {}),
  });
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
  opts: {
    bookName: string;
    apiConfigId: string;
    model: string;
    selectedDims: string[];
    /** 思考档位（c-deconstruct-resilience D10）：off=关思考（默认，推荐）/
     *  low=思考·低 / inherit=跟随模型配置 */
    thinking?: string;
  },
): Promise<CreateTaskResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("book_name", opts.bookName);
  formData.append("api_config_id", opts.apiConfigId);
  formData.append("ai_model", opts.model);
  formData.append("selected_dims", JSON.stringify(opts.selectedDims));
  if (opts.thinking) formData.append("thinking", opts.thinking);
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

// ── 角色库收录（c-charlib-deconstruct-exit） ──────────────────────────────

export interface LibraryCandidateItem {
  key: string;
  name: string;
  role: string;
  persona: string;
  gender: string;
  age: string;
  collected: boolean;
}

export interface LibraryCandidates {
  can_import: boolean;
  reason: string;
  items: LibraryCandidateItem[];
}

export interface ToLibraryResult {
  created: number;
  skipped: number;
  library_ids: string[];
}

/** 收录候选（投影角色＋已收录标记；committed：清单/灰态唯一数据源） */
export async function getLibraryCandidates(taskId: string): Promise<LibraryCandidates> {
  return request<LibraryCandidates>(`/deconstruct/tasks/${taskId}/library-candidates`);
}

/** 收进角色库（第三出口）：只写库不动书；成功后任务记为「已取结果」。 */
export async function toLibrary(
  taskId: string,
  picks: string[],
  rename: boolean,
): Promise<ToLibraryResult> {
  return request<ToLibraryResult>(`/deconstruct/tasks/${taskId}/to-library`, {
    method: "POST",
    body: JSON.stringify({ picks, rename }),
  });
}
