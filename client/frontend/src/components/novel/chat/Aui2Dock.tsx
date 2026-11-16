// Aui2Dock——@agentscope-ai/chat（阿里 Spark Chat）Route 对比 spike（?aui=2）
// ChatAnywhere 容器＋ref.updateMessage 流式直控（绕开 store 通知链）＋内置 Markdown。
// 产物卡 spike 简化为文本化；customCards 卡面映射留正批。
import { useCallback, useRef, useState } from "react";
import { ConfigProvider } from "@agentscope-ai/design";
import { ChatAnywhere, uuid } from "@agentscope-ai/chat";
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
  const [busy, setBusy] = useState(false);

  const onSubmit = useCallback(
    async (data: { query: string }) => {
      const query = data.query?.trim();
      if (!query || busy) return;
      setBusy(true);
      const api = ref.current;
      const userMsg = { id: uuid(), role: "user" as const, content: query };
      api?.updateMessage(userMsg);
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
                content:
                  base +
                  "\n\n---\n[产物卡已生成——本实验版以文本呈现，正式版渲染原卡]",
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
    [projectId, page, threadKey, busy],
  );

  return (
    <div className="chatdock aui2" data-testid="aui2-dock">
      <div className="chatdock-head">
        <span className="chatdock-avatar">助</span>
        <b>写作助手</b>
        <span style={{ fontSize: 11, color: "var(--muted)", marginLeft: 6 }}>
          · 实验版 2（Spark Chat）
        </span>
      </div>
      <ConfigProvider>
        <ChatAnywhere ref={ref} onInput={{ onSubmit }} />
      </ConfigProvider>
    </div>
  );
}
