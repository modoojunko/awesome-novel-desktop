// c-chat-copy：对话复制拼装纯函数契约（Aui2Dock「复制对话」按钮唯一消费方）。
// 口径钉死：只收 user/assistant 且有实际文本的行；trace 卡/空回执不进剪贴板。
import { describe, expect, it } from "vitest";
import { conversationToMarkdown } from "@/lib/chatCopy";

describe("conversationToMarkdown", () => {
  it("user/assistant 交替产出 **角色**＋正文块，空行分隔", () => {
    const md = conversationToMarkdown([
      { role: "user", content: "帮我铺卷" },
      { role: "assistant", content: "铺好了。" },
    ]);
    expect(md).toBe("**我**\n\n帮我铺卷\n\n**助手**\n\n铺好了。");
  });

  it("跳过空文本行（trace 卡/空回执）与非对话角色（system）", () => {
    const md = conversationToMarkdown([
      { role: "assistant", content: "" },
      { role: "assistant", content: "   \n  " },
      { role: "system", content: "内部标记" },
      { role: "tool", content: "draft_volume_expand ✓" },
      { role: "user", content: "继续" },
    ]);
    expect(md).toBe("**我**\n\n继续");
  });

  it("跳过页面切换分隔标记（role 是 assistant 但非助手发言）", () => {
    const md = conversationToMarkdown([
      { role: "user", content: "帮我铺卷" },
      { role: "assistant", content: "铺好了。" },
      { role: "assistant", content: "—— 切换到章节 ——" },
      { role: "user", content: "继续" },
    ]);
    expect(md).toBe("**我**\n\n帮我铺卷\n\n**助手**\n\n铺好了。\n\n**我**\n\n继续");
  });

  it("正文首尾空白裁边；content 缺省/null 视为空", () => {
    const md = conversationToMarkdown([
      { role: "user", content: "\n  两端空白  \n" },
      { role: "assistant" },
      { role: "assistant", content: null },
    ]);
    expect(md).toBe("**我**\n\n两端空白");
  });

  it("全空输入（无可用行）产出空串——按钮侧据此不写剪贴板", () => {
    expect(conversationToMarkdown([])).toBe("");
    expect(conversationToMarkdown([{ role: "assistant", content: "" }])).toBe("");
  });
});
