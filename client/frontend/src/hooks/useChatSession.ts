// useChatSession——助手对话状态机（c-writing-agent 批E）。
// run 模型：消息统一 {id, role, kind, runId?}；事件按 runId/stepId/cardId 幂等
// upsert（乱序/重复容错——reducer 直测重点）；abort 保留已产卡与轨迹。

import { useCallback, useMemo, useReducer, useRef } from "react";
import type { AgentEvent } from "@/lib/chatApi";

export type ChatMessageKind = "text" | "card" | "trace" | "divider" | "gate" | "auth" | "error";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  kind: ChatMessageKind;
  text: string;
  page?: string;
  runId?: string;
  // 产物卡
  cardKind?: "struct" | "text" | "report" | "pick";
  cardId?: string;
  cardPayload?: unknown;
  cardStatus?: "draft" | "adopted" | "stale";
  // 授权卡
  gateId?: string;
  gatePreview?: unknown;
  gateHumanOnly?: boolean;
  gateState?: "pending" | "approved" | "denied" | "expired";
  // 轨迹（TraceFolded 数据源：真实工具步）
  steps: { stepId: string; tool: string; resultNote: string }[];
  error?: string;
}

export interface ChatState {
  messages: ChatMessage[];
  /** 一次 run 的进行态：正在流式（步骤逐行点亮） */
  runActive: boolean;
  /** 思考面板实时内容（全量在 ref，逐字进 DOM 会卡——组件侧节流取用） */
  thinkingText: string;
  /** 已等秒数（组件侧计时器渲染，状态机只存起点标记） */
  error: string;
}

type Action =
  | { type: "user_send"; id: string; text: string; page: string }
  | { type: "run_start"; runId: string }
  | { type: "run_end" }
  | { type: "thinking"; text: string }
  | { type: "thinking_flush"; text: string }
  | { type: "step_start"; runId: string; stepId: string; tool: string }
  | { type: "step_end"; runId: string; stepId: string; tool: string; resultNote: string }
  | { type: "narration"; runId: string; text: string }
  | { type: "artifact"; runId: string; cardId: string; kind: string; payload: unknown }
  | { type: "permission_required"; runId: string; gateId: string; preview: unknown; humanOnly: boolean }
  | { type: "gate"; text: string }
  | { type: "gate_resolved"; gateId: string; approved: boolean }
  | { type: "adopt_card"; cardId: string }
  | { type: "error"; message: string }
  | { type: "load_history"; messages: ChatMessage[] }
  | { type: "reset" };

let seq = 0;
const nextId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${(seq++).toString(36)}`;

function newAssistantMessage(runId: string | undefined): ChatMessage {
  return { id: nextId("am"), role: "assistant", kind: "text", text: "", runId, steps: [] };
}

/**
 * 当前 run 的文本气泡（run_start 创建、带 runId；历史回看的气泡无 runId 不算）。
 * review 判例 2026-11-14：曾用「无条件改末条消息」——卡片/授权卡/错误行追加后，
 * 其后的 narration 被吞进卡片 text（渲染分支不显示）、后续 step 轨迹挂上卡片丢失。
 * 事件永远落回本 run 的文本气泡；找不到（理论不可达）时新开一条兜底。
 */
function runBubbleIndex(messages: ChatMessage[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.kind === "text" && m.role === "assistant" && m.runId != null) return i;
  }
  return -1;
}

function updateRunBubble(
  messages: ChatMessage[],
  runId: string,
  fn: (m: ChatMessage) => ChatMessage,
): ChatMessage[] {
  const i = runBubbleIndex(messages);
  if (i < 0) {
    return [...messages, newAssistantMessage(runId)];
  }
  const out = messages.slice();
  out[i] = fn(out[i]);
  return out;
}

/**
 * 产物卡目标键（同目标才判 stale——review 判例 2026-11-14：曾按「任意 adopted 卡」
 * 判，跨目标的新卡也被打成旧版且无采纳路径，「过目采纳」循环一次即死）。
 * 走向/卷纲草稿按卷锚定；体检按卷 ref；命名/发散回落卡种。
 */
function cardTargetKey(kind: string, payload: unknown): string {
  const d = (payload ?? {}) as Record<string, unknown>;
  if (d.vol_no != null) return `vol-${d.vol_no}`;
  if (typeof d.ref === "string" && d.ref) return d.ref;
  if (typeof d.entry_id === "string" && d.entry_id) return d.entry_id;
  if (typeof d.chapter_ref === "string" && d.chapter_ref) return d.chapter_ref;
  return kind;
}

export function chatReducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "user_send":
      return {
        ...state,
        messages: [
          ...state.messages,
          { id: action.id, role: "user", kind: "text", text: action.text, page: action.page, steps: [] },
        ],
        error: "",
      };
    case "run_start":
      return {
        ...state,
        runActive: true,
        thinkingText: "",
        messages: [...state.messages, newAssistantMessage(action.runId)],
      };
    case "run_end":
      return { ...state, runActive: false, thinkingText: "" };
    case "thinking":
      return { ...state, thinkingText: state.thinkingText + (action.text ?? "") };
    case "thinking_flush":
      return { ...state, thinkingText: action.text };
    case "step_start": {
      // 进行中的工具步点亮进本 run 气泡的 steps（幂等：同 stepId 不重复）
      return {
        ...state,
        messages: updateRunBubble(state.messages, action.runId, (m) =>
          m.steps.some((s) => s.stepId === action.stepId)
            ? m
            : {
                ...m,
                steps: [
                  ...m.steps.filter((s) => s.stepId !== action.stepId),
                  { stepId: action.stepId, tool: action.tool, resultNote: "" },
                ],
              },
        ),
      };
    }
    case "step_end": {
      // 乱序容错：step_end 晚于 step_start（或单独到达）都收敛到同一 stepId 行
      return {
        ...state,
        messages: updateRunBubble(state.messages, action.runId, (m) => {
          const exists = m.steps.some((s) => s.stepId === action.stepId);
          const steps = exists
            ? m.steps.map((s) =>
                s.stepId === action.stepId ? { ...s, tool: action.tool, resultNote: action.resultNote } : s,
              )
            : [...m.steps, { stepId: action.stepId, tool: action.tool, resultNote: action.resultNote }];
          return { ...m, steps };
        }),
      };
    }
    case "narration":
      return {
        ...state,
        messages: updateRunBubble(state.messages, action.runId, (m) => ({
          ...m,
          text: m.text ? `${m.text}\n${action.text}` : action.text,
        })),
      };
    case "artifact": {
      const cardId = action.cardId || nextId("card");
      // 同 cardId 幂等（重复/晚到事件 upsert 同一张卡）
      const existingIdx = state.messages.findIndex(
        (m) => m.kind === "card" && m.cardId === cardId,
      );
      if (existingIdx >= 0) {
        const out = state.messages.slice();
        out[existingIdx] = { ...out[existingIdx], cardPayload: action.payload };
        return { ...state, messages: out };
      }
      // 同目标已有 adopted 卡 → 新卡到货即标 stale「旧版」（不静默覆盖已采纳版本；
      // stale 卡仍可再采纳——walkthrough B2「再采纳第二版」，采纳后新旧两卡都带 ✓）
      const targetKey = cardTargetKey(action.kind, action.payload);
      const hasAdoptedSameTarget = state.messages.some(
        (m) =>
          m.kind === "card" &&
          m.cardStatus === "adopted" &&
          m.cardKind === (action.kind as ChatMessage["cardKind"]) &&
          cardTargetKey(m.cardKind ?? "text", m.cardPayload) === targetKey,
      );
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: nextId("cm"),
            role: "assistant",
            kind: "card",
            text: "",
            runId: action.runId,
            cardKind: (action.kind as ChatMessage["cardKind"]) || "text",
            cardId,
            cardPayload: action.payload,
            cardStatus: hasAdoptedSameTarget ? "stale" : "draft",
            steps: [],
          },
        ],
      };
    }
    case "permission_required":
      return {
        ...state,
        messages: [
          ...state.messages,
          {
            id: nextId("gm"),
            role: "system",
            kind: "auth",
            text: "",
            gateId: action.gateId,
            gatePreview: action.preview,
            gateHumanOnly: action.humanOnly,
            gateState: "pending",
            steps: [],
          },
        ],
      };
    case "gate_resolved":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.kind === "auth" && m.gateId === action.gateId && m.gateState === "pending"
            ? { ...m, gateState: action.approved ? "approved" : "denied" }
            : m,
        ),
      };
    case "gate":
      return {
        ...state,
        messages: [
          ...state.messages,
          { id: nextId("gm"), role: "system", kind: "gate", text: action.text, steps: [] },
        ],
      };
    case "adopt_card":
      // stale 也可采纳（再采纳第二版＝替换写回；旧卡保留「已采纳」徽标不回退）
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.kind === "card" &&
          m.cardId === action.cardId &&
          (m.cardStatus === "draft" || m.cardStatus === "stale")
            ? { ...m, cardStatus: "adopted" }
            : m,
        ),
      };
    case "error":
      return {
        ...state,
        runActive: false,
        error: action.message,
        messages: state.messages.some((m) => m.kind === "error")
          ? state.messages
          : [
              ...state.messages,
              { id: nextId("err"), role: "system", kind: "error", text: action.message, steps: [] },
            ],
      };
    case "load_history":
      return { ...state, messages: action.messages, runActive: false };
    case "reset":
      return { messages: [], runActive: false, thinkingText: "", error: "" };
    default:
      return state;
  }
}

export function useChatSession() {
  const [state, dispatch] = useReducer(chatReducer, {
    messages: [],
    runActive: false,
    thinkingText: "",
    error: "",
  });
  const sendIdRef = useRef(nextId("send"));
  // 思考增量：全量攒 ref，≤300ms 一次 flush 进 state（review 判例 2026-11-14：
  // 曾逐块 dispatch——思考型模型 4 分钟流式下整列表高频重渲染会卡）
  const thinkingBufRef = useRef("");
  const lastThinkFlushRef = useRef(0);
  const THINKING_FLUSH_MS = 300;

  const onEvent = useCallback((event: AgentEvent) => {
    switch (event.type) {
      case "run_start":
        thinkingBufRef.current = "";
        lastThinkFlushRef.current = 0;
        dispatch({ type: "run_start", runId: event.runId || "" });
        break;
      case "run_end":
        dispatch({ type: "run_end" });
        break;
      case "thinking": {
        thinkingBufRef.current += String(event.text ?? "");
        const now = Date.now();
        if (now - lastThinkFlushRef.current >= THINKING_FLUSH_MS) {
          lastThinkFlushRef.current = now;
          dispatch({ type: "thinking_flush", text: thinkingBufRef.current });
        }
        break;
      }
      case "step_start":
        dispatch({
          type: "step_start",
          runId: event.runId || "",
          stepId: event.stepId || "",
          tool: event.tool || "",
        });
        break;
      case "step_end":
        dispatch({
          type: "step_end",
          runId: event.runId || "",
          stepId: event.stepId || "",
          tool: event.tool || "",
          resultNote: String(event.resultNote ?? ""),
        });
        break;
      case "narration":
        dispatch({ type: "narration", runId: event.runId || "", text: String(event.text ?? "") });
        break;
      case "artifact":
        dispatch({
          type: "artifact",
          runId: event.runId || "",
          cardId: event.cardId || "",
          kind: event.kind || "text",
          payload: event.payload,
        });
        break;
      case "permission_required":
        dispatch({
          type: "permission_required",
          runId: event.runId || "",
          gateId: event.gateId || "",
          preview: event.preview,
          humanOnly: Boolean(event.humanOnly),
        });
        break;
      case "gate":
        dispatch({ type: "gate", text: String(event.refusal || event.message || "需要升级档位。") });
        break;
      case "gate_result":
        dispatch({
          type: "gate_resolved",
          gateId: event.gateId || "",
          approved: Boolean(event.approved),
        });
        break;
      case "error":
        dispatch({ type: "error", message: String(event.message || "出错了") });
        break;
      default:
        break;
    }
  }, []);

  return useMemo(
    () => ({
      state,
      dispatch,
      onEvent,
      newSendId: () => {
        sendIdRef.current = nextId("send");
        return sendIdRef.current;
      },
    }),
    [state, onEvent],
  );
}
