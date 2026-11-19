/**
 * 对话复制的纯拼装（c-chat-copy：Aui2Dock「复制对话」按钮唯一消费方）。
 * 口径：只收 user/assistant 且有实际文本的行——trace 卡/空回执（content 空、
 * 只带卡面）不进剪贴板；顺序保持消息序。产出 Markdown（**角色**＋正文块），
 * 粘到任何编辑器/文档都可读。
 */

export type ChatCopyMessage = {
  role: string;
  content?: string | null;
};

const ROLE_LABEL: Record<string, string> = {
  user: "我",
  assistant: "助手",
};

export function conversationToMarkdown(messages: ReadonlyArray<ChatCopyMessage>): string {
  const blocks: string[] = [];
  for (const m of messages) {
    const label = ROLE_LABEL[m.role];
    const text = (m.content ?? "").trim();
    if (!label || !text) continue;
    blocks.push(`**${label}**\n\n${text}`);
  }
  return blocks.join("\n\n");
}
