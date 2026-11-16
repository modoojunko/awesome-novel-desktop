// AuiDock——assistant-ui spike（c-tool-flow 批2b：boss 拍板「react 不要变」路线验证）
// 同 useChatSession store、同 streamAssistantChat 后端；仅对话呈现层换 assistant-ui
// primitives。?aui=1 时替换 ChatDock 渲染做目验对比。spike 简化：产物卡/授权卡/
// 页签分隔文本化（完整卡面映射留正批）。
import { useMemo } from "react";
import {
  AssistantRuntimeProvider,
  useExternalStoreRuntime,
  ThreadPrimitive,
  MessagePrimitive,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import type { ToolCallMessagePartComponent } from "@assistant-ui/core/react";
import { useChatSession, type ChatMessage } from "@/hooks/useChatSession";
import { threadKeyOf, type ChatPageScope } from "@/lib/chatRegistry";
import { streamAssistantChat } from "@/lib/chatApi";
import { CardBody } from "@/components/novel/chat/ChatDock";

/** ChatMessage → ThreadMessageLike（text / 工具步 tool-call / 思考 reasoning） */
function convert(m: ChatMessage): ThreadMessageLike {
  if (m.role === "user") {
    return {
      role: "user",
      content: [{ type: "text", text: m.text ?? "" }],
      id: m.id,
    };
  }
  if (m.role === "assistant" && m.kind === "text") {
    const parts: Array<Extract<ThreadMessageLike["content"][number], object>> = [];
    if (m.thinking) parts.push({ type: "reasoning", text: m.thinking });
    for (const s of m.steps) {
      parts.push({
        type: "tool-call",
        toolCallId: s.stepId,
        toolName: s.tool,
        args: {},
        argsText: "{}",
        result: s.resultNote,
      });
    }
    parts.push({ type: "text", text: m.text ?? "" });
    return { role: "assistant", content: parts, id: m.id };
  }
  if (m.role === "assistant" && m.kind === "card") {
    // Route A：产物卡＝data part（by_name 卡面组件渲染 CardBody 原卡）
    return {
      role: "assistant",
      content: [
        {
          type: "data",
          name: "card",
          data: { kind: m.cardKind ?? "text", payload: m.cardPayload ?? {} },
        },
      ],
      id: m.id,
    };
  }
  if (m.role === "assistant" && m.kind === "auth") {
    // Route A：授权卡＝data part（approve/deny 走 dock 回调闭包）
    return {
      role: "assistant",
      content: [
        {
          type: "data",
          name: "auth",
          data: {
            gateId: m.gateId ?? "",
            preview: m.gatePreview ?? {},
            humanOnly: Boolean(m.gateHumanOnly),
            expired: m.gateState === "expired",
          },
        },
      ],
      id: m.id,
    };
  }
  // 兜底（gate/分隔等）：按助手文本渲染
  return {
    role: "assistant",
    content: [{ type: "text", text: m.text ?? "" }],
    id: m.id,
  };
}

export function AuiDock({
  projectId,
  page,
  scope,
}: {
  projectId: string;
  page: string;
  scope: ChatPageScope;
}) {
  const { state, dispatch, onEvent } = useChatSession();
  const threadKey = threadKeyOf(scope);
  const messages = state.threads[threadKey] ?? [];

  const conversable = messages.filter((m) => convert(m) !== null);

  const runtime = useExternalStoreRuntime({
    messages: conversable,
    convertMessage: convert,
    isRunning: state.runActive,
    onNew: async () => {
      // 输入走下方普通表单（streamAssistantChat 驱动 store）——Thread composer 不用
      void dispatch({ type: "clear_thread", thread: threadKey });
    },
  });

  const approveGateApi = async (gateId: string, decision: "approved" | "denied") => {
    dispatch({ type: "gate_resolved", gateId, approved: decision === "approved" });
    const { approveGate } = await import("@/lib/chatApi");
    await approveGate(projectId, gateId, decision).catch((e: Error) =>
      dispatch({ type: "gate", thread: threadKey, text: e.message }),
    );
  };

  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || state.runActive) return;
    dispatch({
      type: "user_send",
      thread: threadKey,
      id: `u-${Date.now()}`,
      text: trimmed,
      page,
    });
    const focus = scope.chapterRef ? { ref: scope.chapterRef } : undefined;
    void streamAssistantChat(
      projectId,
      { message: trimmed, page, thread: threadKey, focus },
      { onEvent: (e) => onEvent(e, threadKey), onError: () => {} },
    );
  };

  return (
    <div className="chatdock aui" data-testid="aui-dock">
      <div className="chatdock-head">
        <span className="chatdock-avatar">助</span>
        <b>写作助手 · AUI</b>
      </div>
      <AssistantRuntimeProvider runtime={runtime}>
        <ThreadPrimitive.Root className="chatdock-stream aui-stream">
          <ThreadPrimitive.Viewport className="aui-viewport" autoScroll>
            <ThreadPrimitive.Messages
              components={{
                UserMessage: AuiUser,
                AssistantMessage: (props) => (
                  <AuiAssistant
                    onGateApprove={(gid) => void approveGateApi(gid, "approved")}
                    onGateDeny={(gid) => void approveGateApi(gid, "denied")}
                  />
                ),
              }}
            />
            {conversable.length === 0 && (
              <div className="aui-empty">（空对话——发一句话开始。）</div>
            )}
          </ThreadPrimitive.Viewport>
        </ThreadPrimitive.Root>
        <form
          className="chatdock-composer"
          onSubmit={(e) => {
            e.preventDefault();
            const input = e.currentTarget.elements.namedItem(
              "aui-input",
            ) as HTMLInputElement | null;
            if (input?.value.trim()) {
              send(input.value);
              input.value = "";
            }
          }}
        >
          <input name="aui-input" placeholder="想改哪里、要写什么，直接说…" />
          <button type="submit" disabled={state.runActive}>
            发送
          </button>
        </form>
      </AssistantRuntimeProvider>
    </div>
  );
}

function AuiUser() {
  return (
    <MessagePrimitive.Root className="aui-msg aui-user">
      <MessagePrimitive.Parts components={{ Text: AuiUserText }} />
    </MessagePrimitive.Root>
  );
}

function AuiUserText({ text }: { text: string }) {
  return <div className="aui-user-text">{text}</div>;
}

function AuiAssistant({
  onGateApprove,
  onGateDeny,
}: {
  onGateApprove: (gateId: string) => void;
  onGateDeny: (gateId: string) => void;
}) {
  return (
    <MessagePrimitive.Root className="aui-msg aui-assistant">
      <MessagePrimitive.Parts
        components={{
          Text: AuiAssistantText,
          Reasoning: AuiReasoning,
          tools: { Fallback: AuiTool },
          data: {
            by_name: {
              card: AuiCardBody,
              auth: AuiAuthCard,
            },
          },
        }}
      />
    </MessagePrimitive.Root>
  );

  function AuiCardBody({ data }: { data: { kind: string; payload: unknown } }) {
    return (
      <div className="cd-card" data-testid="aui-card">
        <div className="cd-card-head">
          <b>产物</b>
        </div>
        <CardBody kind={data.kind} payload={data.payload} />
        <div className="cd-dim" style={{ padding: "6px 10px" }}>
          初稿——觉得哪里要改，直接说。
        </div>
      </div>
    );
  }

  function AuiAuthCard({
    data,
  }: {
    data: {
      gateId: string;
      preview: unknown;
      humanOnly: boolean;
      expired: boolean;
    };
  }) {
    return (
      <div className="cd-card gate" data-testid="aui-auth-card">
        <div className="cd-card-head">
          <b>{data.humanOnly ? "需要你确认" : "授权写入"}</b>
        </div>
        <pre className="cd-preview">{JSON.stringify(data.preview, null, 1)}</pre>
        {data.expired ? (
          <div className="cd-dim">（重启后待决授权过期——重发指令即可）</div>
        ) : (
          <div className="cd-card-foot">
            <button
              type="button"
              className="cd-btn primary"
              onClick={() => onGateApprove(data.gateId)}
            >
              允许
            </button>
            <button type="button" className="cd-btn" onClick={() => onGateDeny(data.gateId)}>
              拒绝
            </button>
          </div>
        )}
      </div>
    );
  }
}

function AuiAssistantText({ text }: { text: string }) {
  // 轻量人话排版：**粗体**/换行/“- ”列表（React 文本节点自动转义——零依赖零注入面；
  // markdown 库重引挂账未解，先不上）
  const lines = (text ?? "").split("\n");
  return (
    <div className="aui-text">
      {lines.map((ln, i) => {
        const t = ln.trim();
        if (!t) return <div key={i} className="aui-gap" />;
        const li = t.match(/^(?:-|\*)\s+(.*)/);
        if (li) {
          return (
            <div key={i} className="aui-li">
              • {renderBold(li[1])}
            </div>
          );
        }
        return <div key={i}>{renderBold(t)}</div>;
      })}
    </div>
  );
}

function renderBold(s: string) {
  return s.split("**").map((seg, i) =>
    i % 2 === 1 ? <b key={i}>{seg}</b> : <span key={i}>{seg}</span>,
  );
}

function AuiReasoning({ text }: { text: string }) {
  if (!text?.trim()) return null;
  return <div className="aui-reasoning">思考：{text}</div>;
}

const AuiTool: ToolCallMessagePartComponent = ({ toolName, argsText, result }) => {
  return (
    <div className="aui-tool">
      <span className="aui-tool-dot">●</span> {toolName}
      {result ? <div className="aui-tool-result">{String(result).slice(0, 120)}</div> : null}
      {argsText ? null : null}
    </div>
  );
};
