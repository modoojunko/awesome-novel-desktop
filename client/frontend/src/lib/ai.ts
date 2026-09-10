import { getToken } from "./auth";
import { getApiBaseUrl } from "./env";

const API_BASE = `${getApiBaseUrl()}/api`;

/** 归一化后端 detail：字符串直接用；对象取 message（防 `[object Object]`）。 */
export function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail) return detail;
  if (detail && typeof detail === "object") {
    const m = (detail as { message?: unknown }).message;
    if (typeof m === "string" && m) return m;
  }
  return fallback;
}

export interface StreamCallbacks {
  onChunk: (text: string) => void;
  /** meta：done 事件附带的完工检查（ai-prompt-crafting 三工序③） */
  onDone: (fullText: string, meta?: StreamDoneMeta) => void;
  onError: (error: string) => void;
}

/** 字数校验（目标 ±10% 口径；below_limit = 低于目标 90%） */
export interface WordCheck {
  target: number;
  actual: number;
  below_limit: boolean;
  message?: string;
}

/** 叙事自查命中的规则（提示性质，非阻断） */
export interface SelfCheckIssue {
  rule: string;
  excerpts: string[];
}

export interface StreamDoneMeta {
  word_check?: WordCheck;
  self_check?: SelfCheckIssue[];
}

// ---------------------------------------------------------------------------
// Streaming SSE helpers
// ---------------------------------------------------------------------------

export function streamChapterWrite(
  projectId: string,
  chapterRef: string,
  callbacks: StreamCallbacks,
  promptOverride?: string,
): AbortController {
  // promptOverride：AI 弹窗编辑后的提示词覆盖（空串/未传 = 后端自动组装）
  return doStreamFetch(
    `${API_BASE}/novels/${projectId}/chapters/${chapterRef}/write`,
    promptOverride ? { prompt: promptOverride } : undefined,
    callbacks,
  );
}

export function streamChapterContinue(
  projectId: string,
  chapterRef: string,
  cursorPosition: number,
  callbacks: StreamCallbacks,
): AbortController {
  return doStreamFetch(
    `${API_BASE}/novels/${projectId}/chapters/${chapterRef}/write/continue`,
    { cursor_position: cursorPosition },
    callbacks,
  );
}

function doStreamFetch(
  url: string,
  body: Record<string, unknown> | undefined,
  callbacks: StreamCallbacks,
): AbortController {
  const controller = new AbortController();
  const token = getToken();

  const init: RequestInit & { signal: AbortSignal } = {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    signal: controller.signal,
  };

  if (body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  fetch(url, init)
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        callbacks.onError(detailMessage(err?.detail, "写作出错"));
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) {
        callbacks.onError("无法读取响应流");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.type === "chunk") {
              callbacks.onChunk(data.text);
            } else if (data.type === "done") {
              callbacks.onDone(data.full_text, {
                word_check: data.word_check,
                self_check: data.self_check,
              });
            } else if (data.type === "error") {
              callbacks.onError(data.error);
            }
          } catch {
            // Skip malformed lines
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        callbacks.onError(err.message || "网络错误");
      }
    });

  return controller;
}

// ---------------------------------------------------------------------------
// Non-streaming AI helpers (polish / expand)
// ---------------------------------------------------------------------------

async function doJsonPost(
  url: string,
  body: Record<string, unknown>,
): Promise<any> {
  const token = getToken();
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => null);
    // 无 JSON 体的 5xx = 网关层（nginx 无上游/服务重启中），不是应用错误——
    // 别把 "Bad Gateway" 直接丢给用户
    if (!err) {
      const infra = res.status === 502 || res.status === 503 || res.status === 504;
      throw new Error(
        infra ? "服务暂时不可用（可能正在重启），请稍后重试" : `请求失败（HTTP ${res.status}）`,
      );
    }
    throw new Error(detailMessage(err?.detail, "请求出错"));
  }
  return res.json();
}

export async function polishText(
  projectId: string,
  chapterRef: string,
  selectedText: string,
  contextBefore: string,
  contextAfter: string,
): Promise<string> {
  const data = await doJsonPost(
    `${API_BASE}/novels/${projectId}/chapters/${chapterRef}/write/polish`,
    { selected_text: selectedText, context_before: contextBefore, context_after: contextAfter },
  );
  return data.polished_text;
}

export async function expandText(
  projectId: string,
  chapterRef: string,
  selectedText: string,
  contextBefore: string,
  contextAfter: string,
): Promise<string> {
  const data = await doJsonPost(
    `${API_BASE}/novels/${projectId}/chapters/${chapterRef}/write/expand`,
    { selected_text: selectedText, context_before: contextBefore, context_after: contextAfter },
  );
  return data.expanded_text;
}

// ---------------------------------------------------------------------------
// Two-stage prompt pipeline (ai-prompt-crafting)
// ---------------------------------------------------------------------------

/** AI 润色整章提示词：素材包 → 大模型润色 → 校验落库（后端 502 时不动既有行） */
export async function polishWritePrompt(
  projectId: string,
  chapterRef: string,
): Promise<string> {
  const data = await doJsonPost(
    `${API_BASE}/novels/${projectId}/chapters/${chapterRef}/write/prompt/polish`,
    {},
  );
  return data.prompt as string;
}

// ---------------------------------------------------------------------------
// 题材五行 AI（genre-signup-redesign tasks 4.2 / D18）
// ---------------------------------------------------------------------------

/** 题材五行字段（01 口味胶囊不走 AI；promise_note 随 core_promise 出参）。 */
export type GenreAiField =
  | "core_promise"
  | "forbidden_list"
  | "cost_ratio"
  | "battlefield"
  | "track";

/** 按字段强类型出参（与后端归一化后契约一致）。 */
export interface GenreAiResult {
  /** core_promise → {value, note}；forbidden_list → [{tagId|text}]；
   *  cost_ratio → 1-10 数字；battlefield → string[]；track → 文本。 */
  value:
    | { value: string; note: string }
    | Array<{ tagId?: string; text?: string }>
    | number
    | string[]
    | string;
}

/**
 * 题材字段 AI：POST /novels/{id}/settings/ai/genre/{field}
 * - 走既有 `{stype}/{field}` 通道（后端仅 genre 特判 field 级 prompt）
 * - 输入＝书名 + 简介 + 已填题材（后端自读），context 可传本格当前值
 */
export async function genreAi(
  field: GenreAiField,
  payload: { title: string; context?: Record<string, unknown> },
  projectId: string,
): Promise<GenreAiResult> {
  return doJsonPost(
    `${API_BASE}/novels/${projectId}/settings/ai/genre/${field}`,
    { title: payload.title, context: payload.context ?? {} },
  );
}

// ---------------------------------------------------------------------------
// Outline AI draft (outline-ai-draft)
// ---------------------------------------------------------------------------

/** AI 起草章纲：主线卡+设定+前情 → 结构化草稿（不落库，表单承接；失败 502 可重试） */
export async function draftOutline(
  projectId: string,
  chapterRef: string,
): Promise<Record<string, unknown>> {
  return doJsonPost(
    `${API_BASE}/novels/${projectId}/chapters/${chapterRef}/outline/ai-draft`,
    {},
  );
}

// ---------------------------------------------------------------------------
// 简介 AI 三能力（genre-signup-redesign tasks 3.5 / D7）
// ---------------------------------------------------------------------------

export type IntroAiAction = "introspect" | "fill" | "polish";

/** 简介 AI 返回（体检为 six_segments/taboo/verdict；补缺失 missing/act；润色 original/polished/act）。 */
export interface IntroAiResult {
  six_segments?: Array<{ name: string; status: "ok" | "missing"; excerpt?: string; note?: string }>;
  taboo?: { hits: Array<{ rule: string; excerpts: string[] }> };
  verdict?: "strong" | "ok" | "weak";
  /** 标题对照（D21）：书名与简介是否互相印证；缺字段＝模型没给，前端不渲染该行。 */
  title_check?: {
    fit: "ok" | "mismatch" | "generic";
    note: string;
    suggestions: string[];
  };
  missing?: Array<{ name: string; candidate: string }>;
  original?: string;
  polished?: string;
  act?: "insert" | "replace";
  [k: string]: unknown;
}

/** AI 前置失败的可分派原因（与后端 ai_state / detail.reason 同枚举）。 */
export type AiBlockReason = "member_required" | "no_key" | "missing_model" | "invalid";

/** 从错误里取分派原因；顺序 member_required → no_key → missing_model（invalid 归 missing_model 处理）。 */
export function aiBlockReason(e: unknown): AiBlockReason | null {
  const r = (e as { reason?: string })?.reason;
  if (r === "member_required" || r === "no_key" || r === "missing_model" || r === "invalid") {
    return r;
  }
  return null;
}

/**
 * 简介 AI：POST /novels/{id}/settings/ai/intro/{action}
 * - 入参 content ＝ 当前编辑框的 synopsis 草稿（不读存储旧文）、title ＝ 书名
 * - 失败抛错，调用方按 aiBlockReason(e) 分派文案与跳转
 */
export async function introAi(
  action: IntroAiAction,
  payload: { title: string; content: string; missingSegments?: string[] },
  projectId: string,
): Promise<IntroAiResult> {
  const body: Record<string, unknown> = { title: payload.title, content: payload.content };
  if (action === "fill" && payload.missingSegments?.length) {
    body.missing_segments = payload.missingSegments;
  }
  return doJsonPost(`${API_BASE}/novels/${projectId}/settings/ai/intro/${action}`, body);
}
