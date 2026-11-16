// Aui2Dock——@agentscope-ai/chat（阿里 Spark Chat）正式版 dock
// ChatAnywhere 容器＋ref.updateMessage 流式直控＋内置 Markdown。
// busy 态交给 ChatAnywhere 自己的 loading（onSubmit 时 setLoading(true) 经
// useInput 上下文）——外层不再自管 busy（曾因闭包卡死输入无响应）。
import { useCallback, useEffect, useRef } from "react";
import { ConfigProvider } from "@agentscope-ai/design";
import { ChatAnywhere, uuid } from "@agentscope-ai/chat";
import type { ChatAnywhereRef } from "@agentscope-ai/chat";
import { threadKeyOf, matchRegistration, type ChatPageScope } from "@/lib/chatRegistry";
import { streamAssistantChat, loadAssistantSession } from "@/lib/chatApi";

export function Aui2Dock({
  projectId,
  page,
  scope,
}: {
  projectId: string;
  page: string;
  scope: ChatPageScope;
}) {
  const threadKey = threadKeyOf(scope);
  const ref = useRef<ChatAnywhereRef>(null);
  const threadKeyRef = useRef(threadKey);
  threadKeyRef.current = threadKey;
  /** chips 结构化触发（c-tool-flow 批2）：下一次 submit 携带的 tool_hint */
  const pendingHintRef = useRef<{ tool: string; args: Record<string, unknown> } | null>(null);

  // 历史接续：切线程时装载该页签会话（user/assistant 文本行；tool 行不进流）
  useEffect(() => {
    const api = ref.current;
    if (!api) return;
    void (async () => {
      try {
        const sess = await loadAssistantSession(projectId, threadKey);
        api.removeAllMessages();
        for (const m of sess.messages ?? []) {
          if (m.role === "user" && m.content) {
            api.updateMessage({ id: m.id ?? uuid(), role: "user", content: m.content, history: true });
          } else if (m.role === "assistant" && m.content) {
            api.updateMessage({ id: m.id ?? uuid(), role: "assistant", content: m.content, history: true });
          }
        }
      } catch {
        /* 历史失败静默 */
      }
    })();
  }, [projectId, threadKey]);

  const onSubmit = useCallback(
    async (data: { query: string }) => {
      const query = (data?.query ?? "").trim();
      if (!query) return;
      const api = ref.current;
      api?.updateMessage({ id: uuid(), role: "user", content: query });
      const assistantId = uuid();
      api?.updateMessage({
        id: assistantId,
        role: "assistant",
        content: "",
        msgStatus: "generating",
      });

      await streamAssistantChat(
        projectId,
        {
          message: query,
          page,
          thread: threadKeyRef.current,
          focus: scope.chapterRef ? { ref: scope.chapterRef } : undefined,
          tool_hint: pendingHintRef.current ?? undefined,
        },
        {
          onEvent: (e) => {
            const cur = api?.getMessage(assistantId);
            const base = cur?.content ?? "";
            if (e.type === "narration_delta") {
              api?.updateMessage({
                id: assistantId,
                role: "assistant",
                content: base + String(e.text ?? ""),
                msgStatus: "generating",
              });
            } else if (e.type === "narration") {
              // 整段 narration（协议路径无 delta 时兜底／系统话术）——不与 delta 重复拼接：
              // delta 路径的正文已增量送达，此分支只在 base 为空时落全文
              if (!base) {
                api?.updateMessage({
                  id: assistantId,
                  role: "assistant",
                  content: String(e.text ?? ""),
                  msgStatus: "generating",
                });
              }
            } else if (e.type === "step_end") {
              api?.updateMessage({
                id: assistantId,
                role: "assistant",
                content: base + `\n\n● ${e.tool ?? "tool"} ✓`,
                msgStatus: "generating",
              });
            } else if (e.type === "artifact") {
              api?.updateMessage({
                id: assistantId,
                role: "assistant",
                content: base + "\n\n---\n[产物卡已生成]",
                msgStatus: "generating",
              });
            } else if (e.type === "error") {
              api?.updateMessage({
                id: assistantId,
                role: "assistant",
                content: base + `\n\n⚠ ${e.message ?? ""}`,
                msgStatus: "error",
              });
            }
          },
          onError: (msg) => {
            api?.updateMessage({
              id: assistantId,
              role: "assistant",
              content: `⚠ ${msg}`,
              msgStatus: "error",
            });
          },
          onDone: () => {
            const cur = api?.getMessage(assistantId);
            api?.updateMessage({
              id: assistantId,
              role: "assistant",
              content: cur?.content ?? "",
              msgStatus: "finished",
            });
          },
        },
      );
    },
    [projectId, page, scope.chapterRef],
  );

  return (
    <div className="chatdock aui2" data-testid="aui2-dock">
      <div className="chatdock-head">
        <span className="chatdock-avatar">助</span>
        <b>写作助手</b>
      </div>
      <ConfigProvider>
        <div className="chatdock-chips" data-testid="aui2-chips">
          {(matchRegistration(scope)?.chips(scope) ?? [])
            .filter((c) => !c.open)
            .map((c) => (
              <button
                key={c.key}
                type="button"
                className="chatchip"
                data-testid={`aui2-chip-${c.key}`}
                onClick={() => {
                  pendingHintRef.current = { tool: c.key, args: {} };
                  void onSubmit({ query: c.command });
                }}
              >
                {c.label}
              </button>
            ))}
        </div>
        <ChatAnywhere
          ref={ref}
          onInput={{ onSubmit }}
          onUpload={[]}
          uiConfig={{ quickInput: [] }}
          cardConfig={{}}
          onStop={() => {}}
        />
      </ConfigProvider>
    </div>
  );
}
