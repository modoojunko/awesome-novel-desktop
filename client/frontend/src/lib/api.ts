import { getToken } from "./auth";

import { getApiBaseUrl } from "./env";
import { toast } from "./toast";

const BASE = `${getApiBaseUrl()}/api`;

/** 503 全局提示节流：挂载期并发请求同时失败只弹一条 */
let _last503ToastAt = 0;
const TOAST_503_THROTTLE_MS = 8000;

/**
 * 503 就地提示（不强跳 /config，避免丢编辑上下文）：
 * - app 级：未配 AI Key（后端 require_ai_access 抛 JSON detail 含「未配置」），引导去配置
 * - infra 级：云托管冷启动（瞬时 30–60s，HTML/空响应体），提示稍后重试
 */
function notify503(kind: "app" | "infra") {
  const now = Date.now();
  if (now - _last503ToastAt < TOAST_503_THROTTLE_MS) return;
  _last503ToastAt = now;
  if (kind === "app") {
    toast.error("尚未配置模型 API Key，AI 功能暂不可用", {
      action: {
        label: "去配置",
        onClick: () => {
          window.location.hash = "/config";
        },
      },
    });
  } else {
    toast.info("云端服务唤醒中（约 30–60 秒），请稍后重试");
  }
}

export interface RequestOptions {
  method?: string;
  body?: string;
  headers?: Record<string, string>;
  /** 静默能力探测：不触发全局副作用（member_required 升级弹窗、503 全局提示、401 踢出） */
  quiet?: boolean;
  /** 503 不弹全局提示：抛带 status 的错误，由调用方就地提示（如 PromptManagementPage） */
  soft503?: boolean;
}

/** 带 HTTP 状态的错误（request() 抛出形状；调用方断言用同一类型，勿再就地重复声明）。 */
export type ApiError = Error & {
  status?: number;
  reason?: string;
  novels?: string[];
  field?: string;
  current?: unknown;
  rev?: number;
};

/**
 * 统一错误文案取值（仓库口径，同 useStoryArc）：**只有确有后端响应（status 存在）
 * 且为 4xx**时才透出原文——后端 4xx 的 detail 是可行动中文；网络层失败（无 status，
 * Chromium「Failed to fetch」/ WKWebView「Load failed」）与 5xx（含 503 兜底的英文
 * 「Service unavailable」）一律回落调用方的中文兜底，避免英文/空文案漏给用户。
 */
export function errMessage(e: unknown, fallback: string): string {
  const err = e as Partial<ApiError> | null;
  const usable =
    typeof err?.status === "number" &&
    err.status >= 400 &&
    err.status < 500 &&
    typeof err.message === "string" &&
    !!err.message;
  return usable ? (err.message as string) : fallback;
}

export async function request(
  path: string,
  options?: RequestOptions,
): Promise<any> {
  const method = options?.method || 'GET';
  const headers: Record<string, string> = { ...(options?.headers || {}) };

  const token = getToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (options?.body) {
    headers["Content-Type"] = "application/json";
  }

  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: options?.body,
    });
  } catch {
    // 网络层失败统一中文化（无 status ⇒ errMessage 回落调用方兜底）
    throw new Error("网络连接失败，请重试") as ApiError;
  }

  if (res.status === 401) {
    // 踢出口径（c-session-flip-stability）：仅用户动作请求的 401 清凭据+回登录页。
    // 探测类（quiet：启动探测/后台刷新/静默预取）401 零全局副作用——瞬时拒绝
    // 不再把用户正在编辑的页面踢飞；显式失效信号（useAuthHeal code 1 +
    // session_invalid）不经过此分支，不受本豁免影响。
    if (!options?.quiet) {
      localStorage.removeItem("auth_token");
      // 记录踢出时刻：LoginPage 自动登录以此做反弹熔断（c-session-flip-stability
      // 「失效处理不循环」）——否则「自动登录写回凭据 ↔ 业务 401 踢出」互踢成环
      sessionStorage.setItem("last_auth_kick_at", String(Date.now()));
      window.location.href = "/#/login";
    }
    const e = new Error("登录状态已失效，请重新登录") as Error & { status?: number };
    e.status = 401;
    throw e;
  }

  if (res.status === 503) {
    const text = await res.text().catch(() => "");
    let detail = "";
    let reason: string | undefined;
    try {
      const parsed = JSON.parse(text);
      // detail 可能是字符串（旧口径）或对象 {reason, message}（AI 前置三态）
      if (typeof parsed?.detail === "string") {
        detail = parsed.detail;
      } else if (parsed?.detail && typeof parsed.detail === "object") {
        detail = parsed.detail.message || "";
        reason = parsed.detail.reason;
      }
    } catch {
      /* infra 级 503 响应体非 JSON（云托管冷启动） */
    }
    // AI 前置的 no_key / missing_model 是可操作引导，不是服务不可用——不进 infra 全局提示；
    // storage_busy 是本地库瞬时 I/O 错误，由面板就地重试，也不弹「云端唤醒中」
    const isAiPrecondition =
      reason === "no_key" || reason === "missing_model" || reason === "storage_busy";
    if (!isAiPrecondition && !options?.quiet && !options?.soft503) {
      notify503(detail.includes("未配置") ? "app" : "infra");
    }
    const e = new Error(detail || "Service unavailable") as Error & {
      status?: number;
      reason?: string;
    };
    e.status = 503;
    if (reason) e.reason = reason;
    throw e;
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `请求失败（HTTP ${res.status}）` }));
    // AI 会员拦截：后端 403 detail = {reason: "member_required", message}
    // → 广播全局升级引导（MemberBlockPrompt 监听），错误继续抛给调用方
    if (res.status === 403 && err?.detail?.reason === "member_required") {
      const message = err.detail.message || "AI 是会员功能";
      if (!options?.quiet) {
        window.dispatchEvent(
          new CustomEvent("member-block", { detail: { message } }),
        );
      }
      const e = new Error(message) as Error & { reason?: string; status?: number };
      e.reason = "member_required";
      e.status = res.status;
      throw e;
    }
    // detail 可能是对象（如删除题材 409 的 { message, projects }），透传 projects 供 UI 提示引用项目
    // 不变量：4xx 的 message 恒非空——detail 可能是空串 / 对象无 message / 响应体为 null，
    // 一律回落通用文案（调用方 `err.message || 兜底` 的右臂因此真的不可达，见各处 v8 ignore 注释）
    const raw = typeof err.detail === "string" ? err.detail : err.detail?.message;
    const message = raw || `请求失败（HTTP ${res.status}）`;
    // 附带 HTTP 状态码 + detail.reason（AI 前置三态分流用；旧口径只有 member_required）
    const e = new Error(message) as ApiError;
    e.status = res.status;
    if (err.detail && typeof err.detail === "object") {
      if (Array.isArray(err.detail.novels)) e.novels = err.detail.novels;
      if (typeof err.detail.reason === "string") e.reason = err.detail.reason;
      // 角色 rev 冲突（character-settings-v2）：透传冲突格与当前值供"刷新重试"UI
      if (typeof err.detail.field === "string") e.field = err.detail.field;
      if (err.detail.current !== undefined) e.current = err.detail.current;
      if (typeof err.detail.rev === "number") e.rev = err.detail.rev;
    }
    throw e;
  }

  return res.json();
}

export const api = {
  // opts 透传（quiet/soft503）：后台轮询类调用需要 quiet（frontend-auth-heal 规范），
  // 没有透传口时只能绕回 request()——见 c-manuscript-download 轮询。
  get: (path: string, opts?: RequestOptions) => request(path, opts),
  post: (path: string, body?: unknown, opts?: RequestOptions) =>
    request(path, { ...opts, method: 'POST', body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: (path: string, body?: unknown, opts?: RequestOptions) =>
    request(path, { ...opts, method: 'PUT', body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: (path: string, body?: unknown, opts?: RequestOptions) =>
    request(path, { ...opts, method: 'PATCH', body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: (path: string, opts?: RequestOptions) => request(path, { ...opts, method: 'DELETE' }),
  /** Fetch phase status for a novel. */
  fetchPhaseStatus: (novelId: string) =>
    request(`/novels/${novelId}/workflow/phase-status`),
  /** Create a new novel. */
  createNovel: (body: { name: string; source?: string; synopsis?: string; genre_profile?: string; genre?: string }): Promise<{ id: string; name: string }> =>
    request('/novels', { method: 'POST', body: JSON.stringify(body) }),
  /** Rename a novel (display name only). */
  renameNovel: (novelId: string, name: string): Promise<{ id: string; name: string }> =>
    request(`/novels/${novelId}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  /** Read story.yaml synopsis. */
  fetchStory: (novelId: string): Promise<{ synopsis: string }> =>
    request(`/novels/${novelId}/story`),
  /** Write story.yaml synopsis (manual backfill). */
  updateStory: (novelId: string, synopsis: string): Promise<{ ok: boolean; synopsis: string }> =>
    request(`/novels/${novelId}/story`, { method: 'PUT', body: JSON.stringify({ synopsis }) }),
  /** Read the story-arc card (fullstory / ending / volumes + has_content). */
  fetchStoryArc: (novelId: string): Promise<any> =>
    request(`/novels/${novelId}/story/arc`),
  /** Write the story-arc card (whole-card overwrite; empty & 待定 are legal). */
  updateStoryArc: (novelId: string, arc: unknown): Promise<any> =>
    request(`/novels/${novelId}/story/arc`, { method: 'PUT', body: JSON.stringify(arc) }),
  /** 主线 AI 四能力（storyline-settings-v2，member-gated；403 raises member-block）：
   *  draft 起草主线 / calibrate 结局校准 / check 主线体检 / tone 行内基调建议 */
  runArcAi: (novelId: string, action: "draft" | "calibrate" | "check" | "tone", body: { input?: string }): Promise<{ value: any }> =>
    request(`/novels/${novelId}/settings/ai/arc/${action}`, { method: 'POST', body: JSON.stringify(body) }),
};

// ---------------------------------------------------------------------------
// Import types
// ---------------------------------------------------------------------------

export interface ChapterImportData {
  title: string;
  content?: string;
  word_count?: number;
}

export interface VolumeImportData {
  title: string;
  chapters: ChapterImportData[];
}

export interface ImportPreviewData {
  title: string;
  volumes: VolumeImportData[];
  warnings?: Array<{ type: string; message: string; details?: Record<string, unknown> | null }>;
}

// ---------------------------------------------------------------------------
// Import API — file upload uses raw fetch (multipart FormData)
// ---------------------------------------------------------------------------

export async function importParse(
  file: File,
  signal?: AbortSignal,
): Promise<ImportPreviewData> {
  const formData = new FormData();
  formData.append("file", file);
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}/novels/import/parse`, {
    method: "POST",
    body: formData,
    headers,
    signal,
  });
  // 401 踢出不豁免：导入是用户动作请求（无 quiet 形态），口径见 request()
  if (res.status === 401) {
    localStorage.removeItem("auth_token");
    window.location.href = "/#/login";
    throw new Error("Unauthorized");
  }
  if (res.status === 503) {
    // 导入端点与 AI Key 无关，503 只会是云托管冷启动：交由调用方就地提示
    const e = new Error("云端服务暂时不可用，请稍后重试") as Error & { status?: number };
    e.status = 503;
    throw e;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "" }));
    throw new Error(err.detail || `导入失败（HTTP ${res.status}）`);
  }
  return res.json();
}

export function importPersist(body: {
  name: string;
  volumes: VolumeImportData[];
}) {
  return api.post("/novels/import/persist", body);
}

/** Fetch the import template .md content. */
export async function downloadTemplate(): Promise<string> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(`${BASE}/novels/import/template`, { headers });
  if (!res.ok) throw new Error("模板下载失败");
  return res.text();
}
