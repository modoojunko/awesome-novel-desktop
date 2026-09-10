import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import SettingsView from "@/components/novel/workbench/SettingsView";
import { INTRO_SEGMENTS, INTRO_FORMULA, DONT_DO, INTRO_MAX_LEN } from "@/lib/introTemplate";

// tasks 9.1.1：简介面板「怎么写」六段模板——默认收起、点开齐全、计数同步
const apiState = vi.hoisted(() => ({ get: vi.fn(), fetchStory: vi.fn(), updateStory: vi.fn() }));

vi.mock("@/lib/api", () => ({ api: apiState, request: vi.fn() }));
vi.mock("@/lib/ai", () => ({
  introAi: vi.fn(),
  genreAi: vi.fn(),
  aiBlockReason: () => null,
}));
vi.mock("@/hooks/useTier", () => ({
  useFeature: () => true,
  useTier: () => ({ isPro: true, isFree: false, tier: "pro" }),
}));
vi.mock("@/hooks/useModelStatus", () => ({
  useModelStatus: () => ({ aiState: "ready", status: "configured", hasKeys: true, loading: false }),
}));

function renderIntro(synopsis = "") {
  apiState.get.mockResolvedValue({});
  apiState.fetchStory.mockResolvedValue({ synopsis });
  return render(
    <SettingsView
      projectId="p1"
      initialPanel="intro"
      settingsStatus={{}}
      confirmedStatus={{}}
      confirmSetting={vi.fn().mockResolvedValue(true)}
      novelName="测试小说"
    />,
  );
}

describe("简介面板「怎么写」引导（tasks 9.1.1）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.fetchStory.mockReset();
  });

  it("默认收起（aria-expanded=false），点开后才渲染六段内容", async () => {
    const { container } = renderIntro();
    const toggle = await waitFor(() =>
      container.querySelector('[data-od-id="intro-guide"] .guide-toggle'),
    );
    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText(INTRO_SEGMENTS[0].example)).toBeNull();

    fireEvent.click(toggle!);
    expect(toggle?.getAttribute("aria-expanded")).toBe("true");
    for (const seg of INTRO_SEGMENTS) {
      expect(screen.getByText(seg.name)).toBeTruthy();
    }
    expect(screen.getByText(INTRO_FORMULA)).toBeTruthy();
    for (const d of DONT_DO) {
      expect(screen.getByText(new RegExp(d.slice(0, 6)))).toBeTruthy();
    }
  });

  it("六段名与共享常量逐字一致（禁复制字面量）", async () => {
    const { container } = renderIntro();
    const toggle = await waitFor(() =>
      container.querySelector('[data-od-id="intro-guide"] .guide-toggle'),
    );
    fireEvent.click(toggle!);
    const names = [...container.querySelectorAll(".guide-body .g-name")].map(
      (n) => n.textContent,
    );
    expect(names).toEqual(INTRO_SEGMENTS.map((s) => s.name));
  });

  it("计数随输入实时同步并受 500 上限约束", async () => {
    const { container } = renderIntro();
    const ta = (await waitFor(() =>
      container.querySelector("textarea"),
    )) as HTMLTextAreaElement;
    expect(ta.maxLength).toBe(INTRO_MAX_LEN);

    fireEvent.change(ta, { target: { value: "十二个字的一句话简介" } });
    expect(screen.getByText(`10/${INTRO_MAX_LEN}`)).toBeTruthy();
  });
});
