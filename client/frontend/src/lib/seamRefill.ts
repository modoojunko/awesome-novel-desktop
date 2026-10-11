/** 章际衔接修复（c-seam-refill）SSE 客户端：draft 三选一（知前后补中间）。
 *
 * 事件契约（后端 write/seam_refill.py）：
 *  {"type":"phase","phase":"assemble|model"}  —— 等待呈现（阶段文案轮换）
 *  {"type":"chunk","chars":N}                —— 已生成字数计数（不透传原文，流式片段是 JSON 碎片）
 *  {"type":"done","options":[{key,label,how,text}×3]} —— 三版方案
 *  {"type":"error","error":"…"}              —— 任何失败必发终态（防静默空流）
 */
import { getToken } from "./auth";
import { getApiBaseUrl } from "./env";
import { handleAuthExpiry } from "./api";

const API_BASE = `${getApiBaseUrl()}/api`;

export interface SeamOption {
  key: string;
  label: string;
  how: string;
  text: string;
}

export interface SeamDraftBody {
  para_count?: number;
  findings?: Array<{ title: string; detail: string }>;
  rejected?: Array<{ approach: string; text: string }>;
}

export interface SeamDraftHandlers {
  onPhase?: (phase: string) => void;
  onChars?: (chars: number) => void;
  onDone?: (options: SeamOption[]) => void;
  onError?: (error: string) => void;
}

export function seamRefillDraft(
  projectId: string,
  chapterRef: string,
  body: SeamDraftBody,
  handlers: SeamDraftHandlers,
): AbortController {
  const controller = new AbortController();
  const token = getToken();

  fetch(`${API_BASE}/novels/${projectId}/chapters/${chapterRef}/seam-refill/draft`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    signal: controller.signal,
    body: JSON.stringify(body),
  })
    .then(async (response) => {
      if (!response.ok) {
        if (response.status === 401) {
          handleAuthExpiry();
          handlers.onError?.("登录状态已失效，请重新登录");
          return;
        }
        const err = await response.json().catch(() => ({ detail: response.statusText }));
        const msg =
          typeof err?.detail === "string"
            ? err.detail
            : err?.detail?.message || response.statusText;
        handlers.onError?.(`${msg}（HTTP ${response.status}）`);
        return;
      }
      if (!response.body) {
        handlers.onError?.("响应为空，请重试");
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          for (const line of frame.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            try {
              const ev = JSON.parse(line.slice(6));
              if (ev.type === "phase" && handlers.onPhase) handlers.onPhase(ev.phase);
              else if (ev.type === "chunk" && handlers.onChars) handlers.onChars(ev.chars);
              else if (ev.type === "done" && handlers.onDone) handlers.onDone(ev.options || []);
              else if (ev.type === "error") handlers.onError?.(ev.error || "生成失败");
            } catch {
              // 非 JSON 帧（心跳等）忽略
            }
          }
        }
      }
    })
    .catch((e) => {
      if ((e as Error).name !== "AbortError") {
        handlers.onError?.(`衔接方案生成失败：${(e as Error).message || e}`);
      }
    });
  return controller;
}
