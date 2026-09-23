import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { AiAssistPanel } from "@/components/novel/workbench/AiAssistPanel";

// ---------------------------------------------------------------------------
// B 组（storyline col-ai）：右栏 AI 辅助随页签切换——引导语＋统计卡＋动作清单；
// 未实现动作=「规划中」占位（禁用）；已实现动作=真按钮。
// 2026-09-17：检测族（onAiCheck）/精修族（onPromptRefine）/缺项补全（onFillGaps）
// 全部接线；三个重复动作（重新组装提示词/本章关系变化检测/建议本章回收）撤除。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));

const OG_STATS = {
  reqOk: 4,
  planWords: 1800,
  keyCount: 2,
  castCount: 1,
  missingLabels: ["预期策略", "主情绪"],
};

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
  it("章纲页签：统计卡＋还缺清单＋已实现动作全真按钮", () => {
    const onFillGaps = vi.fn();
    const onAiCheck = vi.fn();
    const cb = renderPanel("og", { onFillGaps, onAiCheck });
    expect(screen.getByText("AI 辅助 · 章纲")).toBeTruthy();
    const stats = document.querySelector(".rail-stats")?.textContent ?? "";
    expect(stats).toContain("4/6");
    expect(stats).toContain("1,800 字");
    expect(stats).toContain("2 条");
    // 还缺清单（原型 aiList('还缺')）
    const list = document.querySelector(".rail-list")?.textContent ?? "";
    expect(list).toContain("还缺");
    expect(list).toContain("预期策略");
    expect(list).toContain("主情绪");

    fireEvent.click(screen.getByRole("button", { name: /AI 起草/ }));
    expect(cb.onAiDraft).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /剧情推演/ }));
    expect(cb.onSimulate).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /补全缺失字段/ }));
    expect(onFillGaps).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /与卷纲冲突检测/ }));
    expect(onAiCheck).toHaveBeenCalledWith("volume_conflict");
  });

  it("章纲页签：无缺项/补全中时「补全缺失字段」禁用", () => {
    renderPanel("og", {
      onFillGaps: vi.fn(),
      ogStats: { ...OG_STATS, missingLabels: [] },
    });
    expect(screen.getByRole("button", { name: /补全缺失字段/ })).toBeDisabled();

    renderPanel("og", { onFillGaps: vi.fn(), gapsLoading: true });
    const all = screen.getAllByRole("button", { name: /补全缺失字段|补全中/ });
    const last = all[all.length - 1] as HTMLButtonElement;
    expect(last.disabled).toBe(true);
    expect(last.textContent).toContain("补全中");
  });

  it("正文页签：统计卡＋压缩动作占位；免费态已实现动作锁定", () => {
    renderPanel("prose");
    const stats = document.querySelector(".rail-stats")?.textContent ?? "";
    expect(stats).toContain("500 字");
    expect(stats).toContain("28%"); // 500/1800
    expect(screen.getByRole("button", { name: /压缩啰嗦段落/ })).toBeDisabled();
  });

  it("提示词页签：拉取组装来源统计；精修两动作接线（「重新组装」已撤）", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/prompt-sources")) return { total_chars: 1234, cast_count: 3 };
      throw new Error("unexpected " + p);
    });
    const onPromptRefine = vi.fn();
    renderPanel("prompt", { onPromptRefine });
    expect(screen.getByText("AI 辅助 · 提示词")).toBeTruthy();
    await screen.findByText("1,234 字");
    expect(screen.getByText("3 人")).toBeTruthy();
    // 与提示词页签内「AI 润色」同动作 → 不设入口（ADJUSTMENTS #27 ⑫）
    expect(screen.queryByRole("button", { name: /重新组装提示词/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /补全负向约束/ }));
    expect(onPromptRefine).toHaveBeenCalledWith("negative");
    fireEvent.click(screen.getByRole("button", { name: /精简提示词/ }));
    expect(onPromptRefine).toHaveBeenCalledWith("concise");
    // 只请求 prompt-sources（页签感知）
    expect(apiState.get).toHaveBeenCalledTimes(1);
  });

  it("正文页签：压缩啰嗦段落为真按钮（选中才可点，走 onAiSelection）", () => {
    const onAiSelection = vi.fn();
    renderPanel("prose", {
      onAiSelection,
      aiState: { hasSelection: true, compressLoading: false } as never,
      proseRef: { current: { captureNow: () => ({ text: "选中的一段" }) } } as never,
    });
    const btn = screen.getByRole("button", { name: /压缩啰嗦段落/ });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(btn);
    expect(onAiSelection).toHaveBeenCalledWith("compress", { text: "选中的一段" });
    // 无选中 → 禁用（不降级为占位）
    renderPanel("prose", {
      onAiSelection,
      aiState: { hasSelection: false, compressLoading: false } as never,
      proseRef: { current: { captureNow: () => null } } as never,
    });
    const all = screen.getAllByRole("button", { name: /压缩啰嗦段落/ });
    expect((all[all.length - 1] as HTMLButtonElement).disabled).toBe(true);
  });

  it("设定/关系/伏笔三入口按类触发收尾（未归档禁用）", () => {
    const onRunReconcile = vi.fn();
    const { unmount } = render(
      (() => {
        const cb = { onAiDraft: vi.fn(), onSimulate: vi.fn() };
        return (
          <AiAssistPanel
            projectId="p1"
            chapterRef="vol-1-ch-2"
            tab="settings"
            isPro
            ogStats={OG_STATS}
            wordCount={0}
            planWords={null}
            archived
            canAiDraft={false}
            aiDrafting={false}
            onRunReconcile={onRunReconcile}
            {...cb}
          />
        );
      })(),
    );
    fireEvent.click(screen.getByRole("button", { name: /提取本章变化/ }));
    expect(onRunReconcile).toHaveBeenCalledWith("set_changes");
    unmount();

    renderPanel("relations", { archived: true, onRunReconcile });
    fireEvent.click(screen.getByRole("button", { name: /识别角色与物品变化/ }));
    expect(onRunReconcile).toHaveBeenCalledWith("relations");

    renderPanel("hooks", { archived: true, onRunReconcile });
    fireEvent.click(screen.getByRole("button", { name: /登记新伏笔/ }));
    expect(onRunReconcile).toHaveBeenCalledWith("hooks");

    // 未归档：三入口禁用
    renderPanel("settings", { archived: false, onRunReconcile });
    const all = screen.getAllByRole("button", { name: /提取本章变化/ });
    expect((all[all.length - 1] as HTMLButtonElement).disabled).toBe(true);
  });

  it("文风/关系/伏笔页签：检测动作接线（走 onAiCheck，撤重复项）", () => {
    const onAiCheck = vi.fn();

    renderPanel("style", { onAiCheck });
    fireEvent.click(screen.getByRole("button", { name: /文风一致性检查/ }));
    expect(onAiCheck).toHaveBeenCalledWith("style_consistency");
    fireEvent.click(screen.getByRole("button", { name: /标记偏离段落/ }));
    expect(onAiCheck).toHaveBeenCalledWith("style_deviations");

    renderPanel("relations", { onAiCheck });
    // 与 reconcile 关系收尾同产出 → 不设入口（ADJUSTMENTS #27 ⑫）
    expect(screen.queryByRole("button", { name: /本章关系变化检测/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /关系冲突检测/ }));
    expect(onAiCheck).toHaveBeenCalledWith("relations_conflict");
    fireEvent.click(screen.getByRole("button", { name: /建议补边/ }));
    expect(onAiCheck).toHaveBeenCalledWith("relation_suggest");

    renderPanel("hooks", { onAiCheck });
    // 与 reconcile 伏笔收尾的「收束」提案同产出 → 不设入口
    expect(screen.queryByRole("button", { name: /建议本章回收/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /伏笔冲突检测/ }));
    expect(onAiCheck).toHaveBeenCalledWith("hooks_conflict");
  });

  it("免费态：检测/精修动作整体锁定（rail-locked 禁点）", () => {
    renderPanel("style", { isPro: false, onAiCheck: vi.fn() });
    const acts = document.querySelector(".rail-acts");
    expect(acts?.className).toContain("rail-locked");
    expect(screen.getByRole("button", { name: /文风一致性检查/ })).toBeDisabled();
  });

  it("伏笔页签：悬置/本章埋下统计与检测动作", async () => {
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
    const onAiCheck = vi.fn();
    renderPanel("hooks", { chapterRef: "vol-1-ch-2", onAiCheck });
    expect(screen.getByText("AI 辅助 · 伏笔")).toBeTruthy();
    await screen.findByText("2 条"); // 台账总数
    fireEvent.click(screen.getByRole("button", { name: /伏笔冲突检测/ }));
    expect(onAiCheck).toHaveBeenCalledWith("hooks_conflict");
  });
});
