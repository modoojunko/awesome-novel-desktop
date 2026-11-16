// Aui2Dock——@agentscope-ai/chat（阿里 Spark Chat）正式版 dock
// ChatAnywhere 容器＋ref.updateMessage 流式直控＋内置 Markdown。
// busy 态交给 ChatAnywhere 自己的 loading（onSubmit 时 setLoading(true) 经
// useInput 上下文）——外层不再自管 busy（曾因闭包卡死输入无响应）。
import { useCallback, useRef } from "react";
import { ConfigProvider } from "@agentscope-ai/design";
import { ChatAnywhere, uuid, useInput } from "@agentscope-ai/chat";
import type { ChatAnywhereRef } from "@agentscope-ai/chat";
import { threadKeyOf, type ChatPageScope } from "@/lib/chatRegistry";
import { streamAssistantChat } from "@/lib/chatApi";

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
        { message: query, page, thread: threadKey },
        {
          onEvent: (e) => {
            const cur = api?.getMessage(assistantId);
            const base = cur?.content ?? "";
            if (e.type === "narration") {
              api?.updateMessage({
                id: assistantId,
                role: "assistant",
                content: base + String(e.text ?? ""),
                msgStatus: "generating",
              });
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
    [projectId, page, threadKey],
  );

  return (
    <div className="chatdock aui2" data-testid="aui2-dock">
      <div className="chatdock-head">
        <span className="chatdock-avatar">助</span>
        <b>写作助手</b>
      </div>
      <ConfigProvider>
        <LoadingSync dockRef={ref} />
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

/** busy 同步桥：dock 内监听本组件 isRunning 不可得——ChatAnywhere 输入框自身的
 *  loading 由其 useInput 上下文管理（onSubmit 期间 Sender 自动显示停止态）。
 *  此组件仅为保持 hooks 结构清晰占位；流结束后 loading 由 Sender 内部恢复。 */
function LoadingSync({ dockRef }: { dockRef: React.RefObject<ChatAnywhereRef | null> }) {
  const { setLoading } = useInput();
  // 轮询不可取——Sender 的 loading 在 onSubmit 返回后自动恢复；
  // 这里只需在挂载时确保非 loading 态（曾出现初始 loading=true 卡死输入）
  setLoading(false);
  void dockRef;
  return null;
}
