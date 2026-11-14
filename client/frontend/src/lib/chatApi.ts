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
    | "step_start"
    | "step_end"
    | "thinking"
    | "narration"
    | "artifact"
    | "permission_required"
    | "gate"
    | "gate_result"
    | "run_end"
    | "error";
  runId?: string;
  stepId?: string;
  tool?: string;
  label?: string;
  resultNote?: string;
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

export async function loadAssistantSession(
  projectId: string,
): Promise<{ sessionId: string; pageCursor: string; grants: Record<string, unknown>; messages: AssistantSessionMessage[] }> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/session`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "会话读取失败"));
  return await r.json();
}

export async function resetAssistantSession(projectId: string): Promise<void> {
  const r = await fetch(`${API_BASE}/novels/${projectId}/assistant/session/reset`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (r.status === 401) {
    handleAuthExpiry();
    throw new Error("登录状态已失效，请重新登录");
  }
  if (!r.ok) throw new Error(detailMessage((await r.json().catch(() => null))?.detail, "重置失败"));
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

/**
 * 助手对话流：POST /assistant/chat（SSE）。返回 abort 函数（中断＝已产出保留）。
 * 终态口径：run_end｜error 见过才算干净结束；两者皆无＝服务端异常中止，按失败收尾
 * （c-prose-stream-silent-hang 同口径——SHALL NOT 静默永挂）。
 */
export function streamAssistantChat(
  projectId: string,
  body: { message: string; page: string },
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
