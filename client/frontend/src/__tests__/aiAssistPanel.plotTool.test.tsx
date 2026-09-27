// 右栏「AI 帮写剧情」卡（c-plot-split 5.4）：三态＝可用（PRO）／归档禁用／
// 免费态 rail-locked 置灰禁点不隐藏＋升级出口。
import { act, render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn().mockResolvedValue([]), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

import { AiAssistPanel } from "@/components/novel/workbench/AiAssistPanel";

function renderPanel(opts: {
  isPro: boolean;
  archived?: boolean;
  onPlotDraw?: () => void;
  onUpgrade?: () => void;
}) {
  return render(
    <AiAssistPanel
      projectId="p1"
      chapterRef="vol-1-ch-2"
      tab="og"
      isPro={opts.isPro}
      ogStats={{ reqOk: 6, planWords: 2500, plotCount: 1, castCount: 1 }}
      wordCount={10}
      planWords={2500}
      archived={!!opts.archived}
      canAiDraft={opts.isPro && !opts.archived}
      aiDrafting={false}
      onAiDraft={() => {}}
      onSimulate={() => {}}
      onPlotDraw={opts.onPlotDraw ?? (() => {})}
      onUpgrade={opts.onUpgrade ?? (() => {})}
    />,
  );
}

describe("右栏 AI 帮写剧情卡（三态）", () => {
  it("PRO 可用：按钮可点，点击开三版弹层", () => {
    const onPlotDraw = vi.fn();
    renderPanel({ isPro: true, onPlotDraw });
    const btn = screen.getByTestId("og-plot-draw");
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(onPlotDraw).toHaveBeenCalledTimes(1);
  });

  it("免费态：行级门控（c-character-intro 3.3 起 og 页签不整卡锁）——剧情行 ra-off「需 PRO」，升级走统一出口", async () => {
    const onPlotDraw = vi.fn();
    const onUpgrade = vi.fn();
    renderPanel({ isPro: false, onPlotDraw, onUpgrade });
    // og 页签免费＝行级门控（盘点行免费连坐不到）：整卡不再 locked
    expect(document.querySelector(".rail-assist.locked")).toBeNull();
    const btn = screen.getByTestId("og-plot-draw") as HTMLButtonElement;
    expect(btn).toBeVisible();
    expect(btn.disabled).toBe(true); // 生成类行置灰禁点
    expect(btn.className).toContain("ra-off");
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(onPlotDraw).not.toHaveBeenCalled();
    // 统一升级出口（children 块）
    fireEvent.click(screen.getByTestId("og-upgrade-btn"));
    expect(onUpgrade).toHaveBeenCalledTimes(1);
    // 「手写全免费」口径写在行描述里
    expect(screen.getByText(/手写剧情全免费/)).toBeTruthy();
  });

  it("归档章禁用", () => {
    const onPlotDraw = vi.fn();
    renderPanel({ isPro: true, archived: true, onPlotDraw });
    expect(screen.getByTestId("og-plot-draw")).toBeDisabled();
  });
});
