/**
 * 对话复制的纯拼装（c-chat-copy：Aui2Dock「复制对话」按钮唯一消费方）。
 * 口径：只收 user/assistant 且有实际文本的行——trace 卡/空回执（content 空、
 * 只带卡面）与页面切换分隔标记（历史装载插的 `—— 切换到X ——` 行，role 是
 * assistant 但非助手发言）不进剪贴板；顺序保持消息序。产出 Markdown
 * （**角色**＋正文块），粘到任何编辑器/文档都可读。
 */

export type ChatCopyMessage = {
  role: string;
  content?: string | null;
};

const ROLE_LABEL: Record<string, string> = {
  user: "我",
  assistant: "助手",
};

/** 页面切换分隔标记（Aui2Dock 历史装载唯一插入形态：`—— 切换到{页名} ——`） */
const PAGE_MARKER_RE = /^——\s*切换到.*——$/;

export function conversationToMarkdown(messages: ReadonlyArray<ChatCopyMessage>): string {
  const blocks: string[] = [];
  for (const m of messages) {
    const label = ROLE_LABEL[m.role];
    const text = (m.content ?? "").trim();
    if (!label || !text || PAGE_MARKER_RE.test(text)) continue;
    blocks.push(`**${label}**\n\n${text}`);
  }
  return blocks.join("\n\n");
}
