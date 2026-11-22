// chatApi——助手 SSE 流式客户端（c-writing-agent 批E）。
// 事件契约对齐后端 assistant/loop.py；解析骨架沿用 lib/ai.ts（sawTerminal 判死
// ＋401 认证统一出口），事件幂等交给 useChatSession（本层只转发）。

import { getToken } from "./auth";
import { getApiBaseUrl } from "./env";
import { handleAuthExpiry } from "./api";
import { detailMessage } from "./ai";

const API_BASE = `${getApiBaseUrl()}/api`;

/** 后端 assistant/loop.py 事件契约（批E 前端消费面）。 */
export type AgentEvent = {
  type:
    | "run_start"
    | "clear"
    | "step_start"
    | "step_end"
    | "thinking"
    | "narration"
    | "narration_delta"
    | "artifact"
    | "permission_required"
    | "gate"
    | "gate_result"
    | "run_end"
    | "effect"
    | "plan"
    | "error";
  runId?: string;
  stepId?: string;
  tool?: string;
  domain?: string;
  label?: string;
  resultNote?: string;
  /** 本步工具入参（step_end）——工具卡展开的参数预览 */
  args?: Record<string, unknown>;
  /** 本步是否成功（step_end）——过程泡泡绿勾/红叉 */
  ok?: boolean;
  /** 本步内模型 API 调用记录（coding agent 反馈口径，boss 拍板 2026-11-15） */
  apiCalls?: { op: string; model: string; ms: number; tokens_in: number; tokens_out: number; ok: boolean }[];
  text?: string;
  cardId?: string;
  kind?: string;
  payload?: unknown;
  gateId?: string;
  preview?: unknown;
  humanOnly?: boolean;
  reason?: string;
  feature?: string;
  tierRequired?: string;
  tier_required?: string;
  approved?: boolean;
  refusal?: string;
  message?: string;
  usage?: string;
  steps?: number;
  toolCalls?: number;
  degraded?: boolean;
  /** 任务计划快照（c-agent-action-contract；plan 事件与 run_end 最终态） */
  plan?: unknown;
  planIncomplete?: number;
  /** run_end 携带本轮写操作 effects（NovelWorkspace 按域刷新） */
  effects?: { action: string; domain: string; target?: string; description?: string }[];
  /** 单条即时 effect 事件（c-agent-nav：navigate 中途翻页，不等 run_end） */
  action?: string;
  target?: string;
  description?: string;
};

export interface AssistantStreamHandlers {
  onEvent: (event: AgentEvent) => void;
  onError: (message: string, kind?: string) => void;
  onDone?: () => void;
}

/** 后端 AssistantSession 序列化（GET /session 回看）。 */
export interface AssistantSessionMessage {
  id: string;
  seq: number;
  role: string;
  page: string;
  content: string;
  cardKind: string;
  status: string;
  payload: Record<string, unknown>;
  createdAt: string;
}

export interface AssistantContextUsage {
  estTokens: number;
  window: number;
  pct: number;
}

export async function loadAssistantSession(
  projectId: string,
  thread = "",
): Promise<{
  sessionId: string;
  pageCursor: string;
  grants: Record<string, unknown>;
  context?: AssistantContextUsage;
  messages: AssistantSessionMessage[];
}> {
  const q = thread ? `?thread=${encodeURIComponent(thread)}` : "";
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/session${q}`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "会话读取失败"));
  return await r.json();
}

export async function resetAssistantSession(projectId: string, thread = ""): Promise<void> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/session/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ thread }),
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "重置失败"));
}

/** 产物卡采纳回执落库（重开书后「已采纳」徽标与 stale 防护不丢）。 */
export async function adoptAssistantMessage(projectId: string, cardId: string): Promise<void> {
  await apiJsonWithAuth(
    `${API_BASE}/novels/${projectId}/assistant/messages/${encodeURIComponent(cardId)}/adopt`,
    {},
  );
}

export async function approveGate(
  projectId: string,
  gateId: string,
  decision: "approved" | "denied",
): Promise<void> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ gateId, decision }),
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "批复失败"));
}

export async function setPermissionTier(
  projectId: string,
  tier: "confirm_each" | "allow_book" | "allow_all",
): Promise<void> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/permission-tier`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ tier }),
  });
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "档位设置失败"));
}

/** 停止当前线程的在跑 run（服务端协同取消——已产出保留；openworker 停止语义）。 */
export async function stopAssistantRun(projectId: string, thread: string): Promise<void> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ thread }),
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "停止失败"));
}

/**
 * 助手对话流：POST /assistant/chat（SSE）。返回 abort 函数（中断＝已产出保留）。
 * 终态口径：run_end｜error 见过才算干净结束；两者皆无＝服务端异常中止，按失败收尾
 * （c-prose-stream-silent-hang 同口径——SHALL NOT 静默永挂）。
 */
export function streamAssistantChat(
  projectId: string,
  body: {
    message: string;
    page: string;
    thread?: string;
    focus?: { ref: string };
    tool_hint?: { tool: string; args: Record<string, unknown> };
    /** 页面未保存标记（c-agent-page-ops）：只进模型提示词（界面零渲染） */
    page_state?: { unsaved?: string[] };
    /** 深度思考开关（c-agent-thinking-bubbles）：显式覆盖 API 配置的思考开关 */
    thinking?: boolean;
    /** 助手本轮按次模型覆盖对（c-agent-thinking-bubbles）：不改本书绑定 */
    api_config_id?: string;
    model?: string;
  },
  handlers: AssistantStreamHandlers,
): () => void {
  const controller = new AbortController();
  fetch(`${API_BASE}/novels/${projectId}/assistant/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        if (response.status === 401) {
          handleAuthExpiry();
          handlers.onError("登录状态已失效，请重新登录");
          return;
        }
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        handlers.onError(`${detailMessage(err?.detail, "助手出错")}（HTTP ${response.status}）`);
        return;
      }
      const reader = response.body?.getReader();
      if (!reader) {
        handlers.onError("无法读取响应流");
        return;
      }
      const decoder = new TextDecoder();
      let buffer = "";
      let sawTerminal = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const data = JSON.parse(line.slice(6)) as AgentEvent;
            if (data.type === "run_end" || data.type === "error") sawTerminal = true;
            handlers.onEvent(data);
          } catch {
            /* 非 JSON 行跳过 */
          }
        }
      }
      if (!sawTerminal) {
        handlers.onError("连接中断——已产出的内容都保留着，重发即可继续。");
      } else {
        handlers.onDone?.();
      }
    })
    .catch((e: unknown) => {
      if ((e as Error)?.name === "AbortError") return; // 主动中断不算错误
      handlers.onError((e as Error)?.message || "连接失败");
    });
  return () => controller.abort();
}

/** 助手人格（顶栏控制中心入口；作家可查看/编辑/恢复默认——boss 拍板 2026-11-15）。 */
export interface AssistantPersona {
  identity: Record<string, string>;
  customized: boolean;
}

export async function loadAssistantPersona(
  projectId: string,
): Promise<AssistantPersona> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/persona`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "人格读取失败"));
  return await r.json();
}

export async function updateAssistantPersona(
  projectId: string,
  identity: Record<string, string>,
): Promise<AssistantPersona> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/persona`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ identity }),
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "人格保存失败"));
  return await r.json();
}

export async function clearAssistantPersona(projectId: string): Promise<void> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/persona`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "恢复默认失败"));
}

export async function loadWriterProfile(
  projectId: string,
): Promise<{ sections: Record<string, unknown>; paused: boolean }> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/profile`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "画像读取失败"));
  return await r.json();
}

export async function updateWriterProfile(
  projectId: string,
  updates: Record<string, unknown>,
): Promise<void> {
  await apiJsonWithAuth(`${API_BASE}/novels/${projectId}/assistant/profile/update`, {
    updates,
  });
}

export async function clearWriterProfile(projectId: string): Promise<void> {
  await apiJsonWithAuth(`${API_BASE}/novels/${projectId}/assistant/profile/clear`, {});
}

export async function pauseWriterProfile(
  projectId: string,
  paused: boolean,
): Promise<void> {
  await apiJsonWithAuth(`${API_BASE}/novels/${projectId}/assistant/profile/pause`, {
    paused,
  });
}

async function apiJsonWithAuth(url: string, data: unknown): Promise<void> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify(data),
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "操作失败"));
}

/** 上下文容量：tokens → 「万」口语刻度（128000 → 「12.8万」；9999 → 「9999」）。 */
export function formatWan(n: number): string {
  if (n >= 10000) {
    const v = (n / 10000).toFixed(1).replace(/\.0$/, "");
    return `${v}万`;
  }
  return String(Math.max(0, Math.round(n)));
}
