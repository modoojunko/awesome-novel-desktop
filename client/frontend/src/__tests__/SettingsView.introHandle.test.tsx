import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import SettingsView from "@/components/novel/workbench/SettingsView";

// 回归：IntroPanel 的 useImperativeHandle 必须注册在组件体（曾误贴进 adopt 闭包，
// 导致 introRef.current 恒 null —— 简介面板「确认完成」静默失效、右栏 AI 三能力
// 点击无反应，且采纳时触发 hook 违规）。
// 这里用「点确认完成 → 触发 save → updateStory」与「点体检行 → 触发 runAi」
// 两条真实路径把句柄可达性钉住。

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  fetchStory: vi.fn(),
  updateStory: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState, request: vi.fn() }));

const aiState = vi.hoisted(() => ({ introAi: vi.fn(), genreAi: vi.fn() }));

vi.mock("@/lib/ai", () => ({
  introAi: aiState.introAi,
  genreAi: aiState.genreAi,
  aiBlockReason: () => null,
}));

vi.mock("@/hooks/useTier", () => ({
  useFeature: () => true,
  useTier: () => ({ isPro: true, isFree: false, tier: "pro" }),
}));

// AI 行门控只读后端 ai_state（D13）——测试里直接给就绪态，避免真实网络
vi.mock("@/hooks/useModelStatus", () => ({
  useModelStatus: () => ({
    status: "configured",
    aiState: "ready",
    aiMessage: "",
    modelOptions: [],
    currentModel: "gpt-4o",
    currentConfigId: "c1",
    currentConfigName: "cfg",
    hasKeys: true,
    loading: false,
    error: null,
    selectModel: vi.fn(),
    refresh: vi.fn(),
  }),
}));

describe("SettingsView · 简介面板句柄（回归）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.updateStory.mockReset();
    aiState.introAi.mockReset();
    apiState.get.mockResolvedValue({});
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
    apiState.updateStory.mockResolvedValue({ ok: true, synopsis: "一个故事" });
    aiState.introAi.mockResolvedValue({ six_segments: [], taboo: { hits: [] }, verdict: "" });
  });

  it("确认完成走 introRef.save → updateStory 被调用", async () => {
    const confirmSetting = vi.fn().mockResolvedValue(true);
    render(
      <SettingsView
        projectId="p1"
        initialPanel="intro"
        settingsStatus={{}}
        confirmedStatus={{}}
        confirmSetting={confirmSetting}
        novelName="测试小说"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "确认完成" }));

    await waitFor(() => expect(apiState.updateStory).toHaveBeenCalledWith("p1", ""));
    await waitFor(() => expect(confirmSetting).toHaveBeenCalledWith("synopsis"));
  });

  it("右栏「体检」行经 introRef.runAi 调 introAi", async () => {
    render(
      <SettingsView
        projectId="p1"
        initialPanel="intro"
        settingsStatus={{}}
        confirmedStatus={{}}
        confirmSetting={vi.fn().mockResolvedValue(true)}
        novelName="测试小说"
      />,
    );

    // 简介为空时体检会被前置守卫拦下（提示先写两句）——先填入内容
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "主角是个凡人。" } });
    fireEvent.click(screen.getByText("体检"));

    await waitFor(() =>
      expect(aiState.introAi).toHaveBeenCalledWith(
        "introspect",
        expect.objectContaining({ title: "测试小说", content: "主角是个凡人。" }),
        "p1",
      ),
    );
  });
});

describe("SettingsView · 题材右栏五行", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    aiState.genreAi.mockReset();
    apiState.get.mockResolvedValue({});
    aiState.genreAi.mockResolvedValue({ value: "x" });
  });

  it("五行行存在，点「主线战场」经 genreRef.runAi 调 genreAi", async () => {
    const { container } = render(
      <SettingsView
        projectId="p1"
        initialPanel="genre"
        settingsStatus={{}}
        confirmedStatus={{}}
        confirmSetting={vi.fn().mockResolvedValue(true)}
        novelName="测试小说"
      />,
    );

    await waitFor(() => expect(container.querySelector('[data-aiact="m4"]')).toBeTruthy());
    for (const key of ["m1", "m2", "m3", "m4", "m5"]) {
      expect(container.querySelector(`[data-aiact="${key}"]`)).toBeTruthy();
    }
    fireEvent.click(container.querySelector('[data-aiact="m4"]')!);

    await waitFor(() =>
      expect(aiState.genreAi).toHaveBeenCalledWith(
        "battlefield",
        expect.objectContaining({ title: "测试小说" }),
        "p1",
      ),
    );
  });
});

describe("SettingsView · D14 交互状态机", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.updateStory.mockReset();
    aiState.introAi.mockReset();
    apiState.get.mockResolvedValue({});
    apiState.fetchStory.mockResolvedValue({ synopsis: "主角是个凡人。" });
    apiState.updateStory.mockResolvedValue({ ok: true, synopsis: "主角是个凡人。" });
  });

  it("补缺失未体检 → 置灰「先体检」且点击不调 AI（O-3）", async () => {
    const { container } = render(
      <SettingsView
        projectId="p1"
        initialPanel="intro"
        settingsStatus={{}}
        confirmedStatus={{}}
        confirmSetting={vi.fn().mockResolvedValue(true)}
        novelName="测试小说"
      />,
    );

    const fill = (await waitFor(() =>
      container.querySelector('[data-aiact="fill"]'),
    )) as HTMLButtonElement;
    expect(fill.disabled).toBe(true);
    expect(screen.getByText("先体检")).toBeTruthy();

    fireEvent.click(fill);
    expect(aiState.introAi).not.toHaveBeenCalled();

    // 体检一次后解禁
    aiState.introAi.mockResolvedValue({
      six_segments: [],
      taboo: { hits: [] },
      verdict: "ok",
    });
    fireEvent.click(container.querySelector('[data-aiact="check"]')!);
    await waitFor(() =>
      expect((container.querySelector('[data-aiact="fill"]') as HTMLButtonElement).disabled).toBe(
        false,
      ),
    );
  });

  it("确认成功后清空结果区（O-5）", async () => {
    aiState.introAi.mockResolvedValue({
      six_segments: [],
      taboo: { hits: [] },
      verdict: "strong",
    });
    const { container } = render(
      <SettingsView
        projectId="p1"
        initialPanel="intro"
        settingsStatus={{}}
        confirmedStatus={{}}
        confirmSetting={vi.fn().mockResolvedValue(true)}
        novelName="测试小说"
      />,
    );

    await waitFor(() => expect(container.querySelector('[data-aiact="check"]')).toBeTruthy());
    fireEvent.click(container.querySelector('[data-aiact="check"]')!);
    await waitFor(() =>
      expect(container.querySelector('[data-od-id="intro-ai-sink"]')).toBeTruthy(),
    );

    fireEvent.click(screen.getByRole("button", { name: "确认完成" }));
    await waitFor(() =>
      expect(container.querySelector('[data-od-id="intro-ai-sink"]')).toBeNull(),
    );
  });
});
