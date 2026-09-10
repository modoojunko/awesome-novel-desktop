import { beforeEach, describe, expect, it, vi } from "vitest";
import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import GenreSettingForm, {
  type GenreHandle,
} from "@/components/novel/settings/GenreSettingForm";

// 题材六格面板（genre-signup-redesign tasks 4.1 / D18 新契约）
const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState, request: vi.fn() }));

const aiState = vi.hoisted(() => ({ genreAi: vi.fn() }));

vi.mock("@/lib/ai", () => ({
  genreAi: aiState.genreAi,
  aiBlockReason: (e: { reason?: string }) => e?.reason ?? null,
}));

function renderPanel(initial: unknown = {}) {
  apiState.get.mockImplementation((path: string) => {
    if (path === "/genres/candidates") return Promise.resolve({});
    return Promise.resolve(initial);
  });
  const ref = createRef<GenreHandle>();
  const utils = render(
    <GenreSettingForm ref={ref} projectId="p1" settingKey="genre" />,
  );
  return { ref, ...utils };
}

describe("GenreSettingForm · 六格", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    apiState.put.mockResolvedValue({ ok: true });
  });

  it("渲染六格（编号 01-06 + 名称 + 怎么填 + 成书去处）", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    for (const name of [
      "题材",
      "主要看什么",
      "绝对禁止",
      "吃苦指数",
      "主线战场",
      "剧情轨道",
    ]) {
      expect(screen.getByText(name)).toBeTruthy();
    }
    expect(screen.getByText("01")).toBeTruthy();
    expect(screen.getByText("06")).toBeTruthy();
    expect(container.querySelectorAll(".m-use").length).toBe(6);
    expect(container.querySelectorAll(".m-why").length).toBe(6);
  });

  it("01 口味胶囊＝预置联动：点「逆袭打脸」预填 02/03/04/05，不落 track", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    fireEvent.click(container.querySelector('[data-g="comeback"]')!);

    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("以弱破强的痛快");
    expect(container.querySelector('[data-forbid="forbidden:no-deus-ex-machina"]')?.className)
      .toContain("on");
    expect(container.querySelector('[data-bf="battlefield:resources"]')?.className).toContain("on");
    expect(container.querySelector('[data-od-id="cost-slider"]')).toBeTruthy();
    expect(screen.getByText("8")).toBeTruthy();
    expect((container.querySelector('[data-od-id="track-input"]') as HTMLTextAreaElement).value)
      .toBe("");
  });

  it("03 回车自定义禁区 → 生成可移除的自定义胶囊", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    const input = container.querySelector('[data-od-id="forbid-input"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "禁穿越" } });
    fireEvent.keyDown(input, { key: "Enter" });

    const chip = screen.getByText("禁穿越 ×");
    expect(chip).toBeTruthy();
    fireEvent.click(chip);
    expect(screen.queryByText("禁穿越 ×")).toBeNull();
  });

  it("04 未设置时不出浮例句；拖动后出「N 分 → …」", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    expect(container.querySelector('[data-od-id="cost-sentence"]')).toBeNull();
    fireEvent.change(container.querySelector('[data-od-id="cost-slider"]')!, {
      target: { value: "9" },
    });
    expect(screen.getByText("9 分 → 以命作祭，才封得住那扇门")).toBeTruthy();
  });

  it("05 战场第 3 个出软提示（不禁止）", async () => {
    const { container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    expect(container.querySelector('[data-od-id="bf-note"]')).toBeNull();
    for (const id of ["resources", "status", "truth"]) {
      fireEvent.click(container.querySelector(`[data-bf="battlefield:${id}"]`)!);
    }
    expect(container.querySelector('[data-od-id="bf-note"]')).toBeTruthy();
  });

  it("save 落五字段契约（含自定义项与空值形态）", async () => {
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    fireEvent.change(container.querySelector('[data-od-id="m1-input"]')!, {
      target: { value: "以弱破强的痛快" },
    });
    fireEvent.click(container.querySelector('[data-forbid="forbidden:no-villain-idiot"]')!);
    const input = container.querySelector('[data-od-id="forbid-input"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: "禁穿越" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.change(container.querySelector('[data-od-id="cost-slider"]')!, {
      target: { value: "6" },
    });
    fireEvent.click(container.querySelector('[data-bf="battlefield:truth"]')!);
    fireEvent.change(container.querySelector('[data-od-id="track-input"]')!, {
      target: { value: "从练气到飞升" },
    });

    await ref.current!.save();

    expect(apiState.put).toHaveBeenCalledWith("/novels/p1/settings/genre", {
      core_promise: "以弱破强的痛快",
      promise_note: "",
      forbidden_list: [{ tagId: "forbidden:no-villain-idiot" }, { text: "禁穿越" }],
      cost_ratio: 6,
      battlefield: ["battlefield:truth"],
      track: "从练气到飞升",
    });
  });

  it("回读：已有契约渲染到对应控件（含未知战场项原样展示）", async () => {
    const { container } = renderPanel({
      core_promise: "算无遗策的掌控感",
      promise_note: "读者要看布局收网",
      forbidden_list: [{ tagId: "forbidden:no-foresight" }],
      cost_ratio: 4,
      battlefield: ["battlefield:status", "街口那条巷子"],
      track: "每卷一个对手",
    });
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("算无遗策的掌控感");
    expect(screen.getByText(/读者要看布局收网/)).toBeTruthy();
    expect(container.querySelector('[data-forbid="forbidden:no-foresight"]')?.className)
      .toContain("on");
    expect(screen.getByText("4 分 → 当众断骨毁名，才拿到入场券")).toBeTruthy();
    expect(container.querySelector('[data-bf="battlefield:status"]')?.className).toContain("on");
    expect(screen.getByText("街口那条巷子 ×")).toBeTruthy();
    expect((container.querySelector('[data-od-id="track-input"]') as HTMLTextAreaElement).value)
      .toBe("每卷一个对手");
  });
});

// ── 五行 AI（tasks 4.2）：反馈落各格下方，采纳才写回 ──────────────────────
describe("GenreSettingForm · 五行 AI", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    apiState.put.mockResolvedValue({ ok: true });
    aiState.genreAi.mockReset();
  });

  it("core_promise：sink 落在 02 格下方，采纳写回 value + note", async () => {
    aiState.genreAi.mockResolvedValue({
      value: { value: "以弱破强的痛快", note: "读者要看到弱者翻盘" },
    });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    await act(async () => ref.current!.runAi("core_promise"));

    const sink = container.querySelector('[data-od-id="genre-ai-sink-core_promise"]');
    expect(sink).toBeTruthy();
    expect(screen.getByText("AI 填 · 主要看什么")).toBeTruthy();
    expect(aiState.genreAi).toHaveBeenCalledWith(
      "core_promise",
      expect.objectContaining({ title: "" }),
      "p1",
    );

    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));
    expect((container.querySelector('[data-od-id="m1-input"]') as HTMLTextAreaElement).value)
      .toBe("以弱破强的痛快");
    expect(screen.getAllByText(/读者要看到弱者翻盘/).length).toBeGreaterThan(0);
  });

  it("cost_ratio：采纳后滑块与浮例句同步", async () => {
    aiState.genreAi.mockResolvedValue({ value: 9 });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    await act(async () => ref.current!.runAi("cost_ratio"));
    expect(screen.getByText(/建议 9 分/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));
    expect(screen.getByText("9 分 → 以命作祭，才封得住那扇门")).toBeTruthy();
  });

  it("battlefield：候选 tagId 采纳后落成已选胶囊", async () => {
    aiState.genreAi.mockResolvedValue({
      value: [{ tagId: "battlefield:resources" }, { text: "街口那条巷子" }],
    });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    await act(async () => ref.current!.runAi("battlefield"));
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));

    expect(container.querySelector('[data-bf="battlefield:resources"]')?.className).toContain("on");
    expect(screen.getByText("街口那条巷子 ×")).toBeTruthy();
  });

  it("track：采纳写回 06 文本框", async () => {
    aiState.genreAi.mockResolvedValue({ value: "凡人流——每卷突破一个大境界" });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    await act(async () => ref.current!.runAi("track"));
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));

    expect((container.querySelector('[data-od-id="track-input"]') as HTMLTextAreaElement).value)
      .toBe("凡人流——每卷突破一个大境界");
  });

  it("失败不落 sink（按 reason 分派提示）", async () => {
    aiState.genreAi.mockRejectedValue({ reason: "missing_model" });
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    await act(async () => ref.current!.runAi("track"));
    expect(container.querySelector('[data-od-id="genre-ai-sink-track"]')).toBeNull();
  });
});

// 题材五行：最近 5 次历史 + 切回旧版采纳覆盖本格
describe("GenreSettingForm · 生成历史（最近 5 次）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.put.mockReset();
    apiState.put.mockResolvedValue({ ok: true });
    aiState.genreAi.mockReset();
  });

  it("连生成 6 次只保留最近 5 次；切回旧版采纳覆盖本格", async () => {
    const { ref, container } = renderPanel();
    await waitFor(() => expect(container.querySelectorAll(".mod")).toHaveLength(6));

    for (let i = 1; i <= 6; i++) {
      aiState.genreAi.mockResolvedValueOnce({ value: `第${i}版轨道` });
      await act(async () => ref.current!.runAi("track"));
      await waitFor(() => expect(container.textContent).toContain(`第${i}版轨道`));
    }
    const chips = [...container.querySelectorAll('[data-od-id="ai-sink-history"] [data-hist]')];
    expect(chips).toHaveLength(5); // 丢最旧
    expect(container.textContent).toContain("只保留最近 5 次");

    // 切回第 1 条（＝第 2 次生成）并采纳 → 覆盖 06 文本框
    fireEvent.click(chips[0]);
    expect(container.textContent).toContain("第2版轨道");
    fireEvent.click(screen.getByRole("button", { name: "采纳 · 覆盖" }));
    expect((container.querySelector('[data-od-id="track-input"]') as HTMLTextAreaElement).value).toBe(
      "第2版轨道",
    );
  });
});
