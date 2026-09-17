import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AiAssistPanel } from "@/components/novel/workbench/AiAssistPanel";

// ---------------------------------------------------------------------------
// B 组（storyline col-ai）：右栏 AI 辅助随页签切换——引导语＋统计卡＋动作清单；
// 未实现动作=「规划中」占位（禁用）；已实现动作=真按钮。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));

const OG_STATS = { reqOk: 4, planWords: 1800, keyCount: 2, castCount: 1 };

function renderPanel(tab: string, extra: Partial<Parameters<typeof AiAssistPanel>[0]> = {}) {
  const cb = { onAiDraft: vi.fn(), onSimulate: vi.fn() };
  render(
    <AiAssistPanel
      projectId="p1"
      chapterRef="vol-1-ch-2"
      tab={tab}
      isPro
      ogStats={OG_STATS}
      wordCount={500}
      planWords={1800}
      archived={false}
      canAiDraft
      aiDrafting={false}
      {...cb}
      {...extra}
    />,
  );
  return cb;
}

beforeEach(() => {
  apiState.get.mockReset().mockRejectedValue(new Error("no stubs"));
});

describe("AiAssistPanel（随页签）", () => {
  it("章纲页签：统计卡＋已实现动作（AI 起草/剧情推演）真按钮、未实现动作占位禁用", () => {
    const cb = renderPanel("og");
    expect(screen.getByText("AI 辅助 · 章纲")).toBeTruthy();
    const stats = document.querySelector(".rail-stats")?.textContent ?? "";
    expect(stats).toContain("4/6");
    expect(stats).toContain("1,800 字");
    expect(stats).toContain("2 条");
    fireEvent.click(screen.getByRole("button", { name: /AI 起草/ }));
    expect(cb.onAiDraft).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /剧情推演/ }));
    expect(cb.onSimulate).toHaveBeenCalled();
    // 未实现动作：禁用 + 规划中
    const ph = screen.getByRole("button", { name: /补全缺失字段/ }) as HTMLButtonElement;
    expect(ph.disabled).toBe(true);
    expect(ph.textContent).toContain("规划中");
    expect(screen.getByRole("button", { name: /与卷纲冲突检测/ })).toBeDisabled();
  });

  it("正文页签：统计卡＋压缩动作占位；免费态已实现动作锁定", () => {
    renderPanel("prose");
    const stats = document.querySelector(".rail-stats")?.textContent ?? "";
    expect(stats).toContain("500 字");
    expect(stats).toContain("28%"); // 500/1800
    expect(screen.getByRole("button", { name: /压缩啰嗦段落/ })).toBeDisabled();
  });

  it("提示词页签：拉取组装来源统计（懒加载仅在激活页签）", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/prompt-sources")) return { total_chars: 1234, cast_count: 3 };
      throw new Error("unexpected " + p);
    });
    renderPanel("prompt");
    expect(screen.getByText("AI 辅助 · 提示词")).toBeTruthy();
    await screen.findByText("1,234 字");
    expect(screen.getByText("3 人")).toBeTruthy();
    // 提示词页签动作全占位
    expect(screen.getByRole("button", { name: /重新组装提示词/ })).toBeDisabled();
    // 只请求 prompt-sources（页签感知）
    expect(apiState.get).toHaveBeenCalledTimes(1);
  });

  it("伏笔页签：悬置/本章埋下统计与占位动作", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/hooks")) {
        return {
          data: {
            items: [
              { status: "active", introduced_chapter_id: "c2", resolved_chapter_id: null },
              { status: "resolved", introduced_chapter_id: "c1", resolved_chapter_id: "c2" },
            ],
          },
        };
      }
      if (p.endsWith("/volumes")) {
        return [
          {
            name: "vol-1",
            chapters: [
              { id: "c1", chapter: 1, ref: "vol-1-ch-1" },
              { id: "c2", chapter: 2, ref: "vol-1-ch-2" },
            ],
          },
        ];
      }
      throw new Error("unexpected " + p);
    });
    renderPanel("hooks", { chapterRef: "vol-1-ch-2" });
    expect(screen.getByText("AI 辅助 · 伏笔")).toBeTruthy();
    await screen.findByText("2 条"); // 台账总数
    expect(screen.getByRole("button", { name: /建议本章回收/ })).toBeDisabled();
  });
});
