// SseChatAdapter——我们后端 SSE → assistant-ui ChatModelAdapter（Route A 核心）。
// 逐事件翻译：step_start/step_end→tool-call part、narration→text part、
// thinking→reasoning part、artifact→artifact 工具卡（tools.Fallback 渲染产物卡）、
// gate→gate 工具卡（授权按钮）。abortSignal 贯通（停止钮）。
// 输入消息＝run options 末条 user 消息（composer 经 runtime.thread.append 进来）。
import { getToken } from "@/lib/auth";
import type {
  ChatModelAdapter,
  ChatModelRunOptions,
  ChatModelRunResult,
} from "@assistant-ui/react";

type SseEvent = { type: string; [k: string]: unknown };

export class SseChatAdapter implements ChatModelAdapter {
  private projectId: string;
  private page: string;
  private thread: string;
  private focusRef?: string;
  /** chips 结构化触发（c-tool-flow 批2）：本轮 tool_hint（append 前设置） */
  toolHint: { tool: string; args: Record<string, unknown> } | null = null;

  constructor(cfg: { projectId: string; page: string; thread: string; focusRef?: string }) {
    this.projectId = cfg.projectId;
    this.page = cfg.page;
    this.thread = cfg.thread;
    this.focusRef = cfg.focusRef;
  }

  async *run({ messages, abortSignal }: ChatModelRunOptions): AsyncGenerator<ChatModelRunResult, void> {
    // 输入＝末条 user 消息文本（composer/runtime.thread.append 进来）
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    const userText = (lastUser?.content ?? [])
      .filter((c): c is { type: "text"; text: string } => c.type === "text")
      .map((c) => c.text)
      .join("\n");

    const parts: Array<Extract<ChatModelRunResult["content"], readonly unknown[]>[number]> = [];
    const controller = new AbortController();
    if (abortSignal) {
      if (abortSignal.aborted) controller.abort();
      else
        abortSignal.addEventListener("abort", () => controller?.abort(), { once: true });
    }

    // 事件队列：SSE 读流任务推送，生成器逐条消费（异步桥）
    const buffered: (SseEvent | "__done")[] = [];
    let waiter: ((v: SseEvent | "__done") => void) | null = null;
    const push = (v: SseEvent | "__done") => {
      if (waiter) {
        const w = waiter;
        waiter = null;
        w(v);
      } else {
        buffered.push(v);
      }
    };
    const nextEvent = () =>
      buffered.length
        ? Promise.resolve(buffered.shift()!)
        : new Promise<SseEvent | "__done">((res) => (waiter = res));

    void (async () => {
      try {
        const response = await fetch(`/api/novels/${this.projectId}/assistant/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${getToken()}`,
          },
          body: JSON.stringify({
            message: userText,
            page: this.page,
            thread: this.thread,
            focus: this.focusRef ? { ref: this.focusRef } : undefined,
            tool_hint: this.toolHint ?? undefined,
          }),
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          push({ type: "error", message: `HTTP ${response.status}` });
          push("__done");
          return;
        }
        const reader = response.body.getReader();
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
              push(JSON.parse(line.slice(6)) as SseEvent);
            } catch {
              /* 非 JSON 行跳过 */
            }
          }
        }
        push("__done");
      } catch (e) {
        if ((e as Error)?.name === "AbortError") {
          push("__done");
          return;
        }
        push({ type: "error", message: (e as Error)?.message || "连接失败" });
        push("__done");
      }
    })();

    // 事件循环：逐事件更新 parts 并全量交付（流式可见）
    while (true) {
      const ev = await nextEvent();
      if (ev === "__done") break;

      if (ev.type === "step_start") {
        parts.push({
          type: "tool-call",
          toolCallId: String(ev.stepId ?? `t${parts.length}`),
          toolName: String(ev.tool ?? "tool"),
          args: {},
          argsText: "{}",
        });
      } else if (ev.type === "step_end") {
        const id = String(ev.stepId ?? "");
        const idx = parts.findIndex(
          (p) => p.type === "tool-call" && p.toolCallId === id,
        );
        if (idx >= 0) {
          const p = parts[idx] as { result?: unknown };
          (p as { result?: unknown }).result = { note: ev.resultNote };
        }
      } else if (ev.type === "artifact") {
        // 产物卡＝artifact 工具卡（tools.Fallback 分支渲染 CardBody 原卡）
        const payload = (ev.payload ?? {}) as Record<string, unknown>;
        parts.push({
          type: "tool-call",
          toolCallId: String(ev.cardId ?? `art-${parts.length}`),
          toolName: `artifact:${String(payload.kind ?? "text")}`,
          args: {},
          argsText: "{}",
          result: { kind: payload.kind ?? "text", payload },
        });
      } else if (ev.type === "narration") {
        const chunk = String(ev.text ?? "");
        const last = parts[parts.length - 1];
        if (last && last.type === "text") {
          (last as { text: string }).text += chunk;
        } else {
          parts.push({ type: "text", text: chunk });
        }
      } else if (ev.type === "thinking") {
        const chunk = String(ev.text ?? "");
        const last = parts[parts.length - 1];
        if (last && last.type === "reasoning") {
          (last as { text: string }).text += chunk;
        } else {
          parts.push({ type: "reasoning", text: chunk });
        }
      } else if (ev.type === "gate") {
        parts.push({
          type: "tool-call",
          toolCallId: String(ev.gateId ?? `gate-${parts.length}`),
          toolName: "gate",
          args: {},
          argsText: "{}",
          result: {
            gateId: ev.gateId,
            preview: (ev as Record<string, unknown>).preview ?? {},
            humanOnly: Boolean((ev as Record<string, unknown>).humanOnly),
          },
        });
      } else if (ev.type === "error") {
        parts.push({
          type: "tool-call",
          toolCallId: `err-${parts.length}`,
          toolName: "error",
          args: {},
          argsText: "{}",
          result: { message: ev.message },
        } as Extract<ChatModelRunResult["content"], readonly unknown[]>[number]);
      }

      // 每事件全量 content 交付（流式：narration/thinking 增量可见）
      yield { content: [...parts] } as ChatModelRunResult;
    }
  }
}
