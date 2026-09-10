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

describe("SettingsView · 重复提交与竞态（tasks 9.4.14/9.4.15）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.updateStory.mockReset();
    apiState.fetchStory.mockReset();
    apiState.get.mockResolvedValue({});
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
  });

  it("双击「确认完成」只保存+确认一次（busy 守卫）", async () => {
    let resolveSave!: (v: { ok: boolean; synopsis: string }) => void;
    apiState.updateStory.mockImplementation(
      () =>
        new Promise((r) => {
          resolveSave = r;
        }),
    );
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

    const btn = await waitFor(() => screen.getByRole("button", { name: "确认完成" }));
    fireEvent.click(btn);
    fireEvent.click(btn);
    fireEvent.click(btn);
    expect(apiState.updateStory).toHaveBeenCalledTimes(1);

    resolveSave({ ok: true, synopsis: "" });
    await waitFor(() => expect(confirmSetting).toHaveBeenCalledTimes(1));
  });

  it("AI 请求在途时切面板：晚到结果不写入已切走的面板（无残留）", async () => {
    let resolveAi!: (v: unknown) => void;
    aiState.introAi.mockImplementation(
      () =>
        new Promise((r) => {
          resolveAi = r;
        }),
    );
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
    // 体检有「先写两句」前置守卫 → 先填内容
    fireEvent.change(container.querySelector("textarea")!, {
      target: { value: "主角是个凡人。" },
    });
    fireEvent.click(container.querySelector('[data-aiact="check"]')!);
    await waitFor(() => expect(aiState.introAi).toHaveBeenCalled());

    // 在途时切到题材面板（简介面板卸载）；面板 dirty → 切面板守卫放行
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(
      [...container.querySelectorAll(".col-tree .s-item")].find((el) =>
        el.textContent?.includes("题材"),
      )!,
    );
    await waitFor(() =>
      expect(container.querySelector(".settings-v main h2")?.textContent).toContain("题材"),
    );

    resolveAi({ six_segments: [], taboo: { hits: [] }, verdict: "ok" });
    // 结果区不出现（面板已卸载，无残留、无报错）
    await new Promise((r) => setTimeout(r, 20));
    expect(container.querySelector('[data-od-id="intro-ai-sink"]')).toBeNull();
  });
});

describe("SettingsView · 存草稿（简介面板）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.updateStory.mockReset();
    apiState.fetchStory.mockReset();
    apiState.get.mockResolvedValue({});
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
    apiState.updateStory.mockResolvedValue({ ok: true, synopsis: "草稿内容" });
  });

  it("未确认面板有「存草稿」：只落库、不确认、不前进", async () => {
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

    fireEvent.change(await waitFor(() => screen.getByRole("textbox")), {
      target: { value: "草稿内容" },
    });
    fireEvent.click(screen.getByRole("button", { name: "存草稿" }));

    await waitFor(() => expect(apiState.updateStory).toHaveBeenCalledWith("p1", "草稿内容"));
    expect(confirmSetting).not.toHaveBeenCalled();
    // 仍停在简介面板（未前进到题材）
    expect(screen.getByRole("heading", { name: "简介" })).toBeTruthy();
  });

  it("已确认面板不再显示「存草稿」（保存修改即草稿语义）", async () => {
    render(
      <SettingsView
        projectId="p1"
        initialPanel="intro"
        settingsStatus={{ synopsis: true }}
        confirmedStatus={{ synopsis: true }}
        confirmSetting={vi.fn().mockResolvedValue(true)}
        novelName="测试小说"
      />,
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "保存修改" })).toBeTruthy());
    expect(screen.queryByRole("button", { name: "存草稿" })).toBeNull();
  });
});

describe("简介 AI · 最近 5 次历史 + 采纳整段替换（用户要求）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.updateStory.mockReset();
    apiState.fetchStory.mockReset();
    aiState.introAi.mockReset();
    apiState.get.mockResolvedValue({});
    apiState.fetchStory.mockResolvedValue({ synopsis: "" });
  });

  const introAiReturn = (n: number) => ({
    six_segments: [],
    taboo: { hits: [] },
    verdict: "ok",
    missing: [{ name: "突发状况", candidate: `候选第${n}版` }],
  });

  it("重试 6 次只保留最近 5 次，且可切回第 1 次采纳", async () => {
    const { container } = render(
      <SettingsView projectId="p1" initialPanel="intro" settingsStatus={{}} confirmedStatus={{}}
        confirmSetting={vi.fn().mockResolvedValue(true)} novelName="测试小说" />,
    );
    await waitFor(() => expect(container.querySelector('[data-aiact="fill"]')).toBeTruthy());
    // 体检有「先写两句」前置 + 补缺失有「先体检」前置
    fireEvent.change(container.querySelector("textarea")!, {
      target: { value: "我手写的开头" },
    });
    aiState.introAi.mockResolvedValueOnce({ six_segments: [], taboo: { hits: [] }, verdict: "ok" });
    fireEvent.click(container.querySelector('[data-aiact="check"]')!);
    // 前置＝体检结果已到手（introspectedRef 在结果到达时置位）
    await waitFor(() => expect(container.textContent).toContain("AI 体检"));

    for (let i = 1; i <= 6; i++) {
      aiState.introAi.mockResolvedValueOnce(introAiReturn(i));
      fireEvent.click(container.querySelector('[data-aiact="fill"]')!);
      await waitFor(() =>
        expect(container.textContent).toContain(`候选第${i}版`),
      );
    }
    const chips = [...container.querySelectorAll('[data-od-id="ai-sink-history"] [data-hist]')];
    expect(chips).toHaveLength(5); // 只保留最近 5 次
    expect(screen.getByText(/只保留最近 5 次/)).toBeTruthy();
    // 保留的是第 2..6 次（丢最旧）
    fireEvent.click(chips[0]);
    expect(container.textContent).toContain("候选第2版");
  });

  it("采纳＝清空原输入、用「原文 + 本次候选」整段替换；换一次采纳不叠加", async () => {
    const { container } = render(
      <SettingsView projectId="p1" initialPanel="intro" settingsStatus={{}} confirmedStatus={{}}
        confirmSetting={vi.fn().mockResolvedValue(true)} novelName="测试小说" />,
    );
    const ta = (await waitFor(() => container.querySelector("textarea"))) as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "我手写的开头" } });

    aiState.introAi.mockResolvedValueOnce({ six_segments: [], taboo: { hits: [] }, verdict: "ok" });
    fireEvent.click(await waitFor(() => container.querySelector('[data-aiact="check"]')!));
    await waitFor(() => expect(container.textContent).toContain("AI 体检"));

    aiState.introAi.mockResolvedValueOnce(introAiReturn(1));
    fireEvent.click(container.querySelector('[data-aiact="fill"]')!);
    await waitFor(() => expect(container.textContent).toContain("候选第1版"));
    fireEvent.click(screen.getByRole("button", { name: /采纳 · 替换为补全后的简介/ }));
    await waitFor(() => expect(ta.value).toBe("我手写的开头。候选第1版"));

    // 再生成一版并采纳 → 整段替换（不叠加第 1 版）
    aiState.introAi.mockResolvedValueOnce(introAiReturn(2));
    fireEvent.click(container.querySelector('[data-aiact="fill"]')!);
    await waitFor(() => expect(container.textContent).toContain("候选第2版"));
    fireEvent.click(screen.getByRole("button", { name: /采纳 · 替换为补全后的简介/ }));
    await waitFor(() => expect(ta.value).toBe("我手写的开头。候选第2版"));
    expect(ta.value).not.toContain("候选第1版");
  });
});
