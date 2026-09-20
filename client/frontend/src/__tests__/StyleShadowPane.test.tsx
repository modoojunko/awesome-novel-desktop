import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StyleShadowPane } from "@/components/novel/workbench/StyleShadowPane";

// ---------------------------------------------------------------------------
// 文风页签·本章影子（2026-09-20 AI 入口收口右栏）：
//   手动覆盖行（增/改/还原）免费可用；AI 建议由右栏信号触发拉取，
//   页签内只渲染结果与逐项采纳（PRO 门控在右栏动作上）。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiState }));

const BASELINE = {
  baseline: [
    { row: "syntax", label: "句子与段落", value: "中长句为主", tolerance: 10, locked: false },
    { row: "narrative", label: "镜头与人称", value: "第三人称限知", tolerance: 10, locked: false },
  ],
  confidence: 88,
  portrait: "",
  shadow: {},
};

beforeEach(() => {
  apiState.get.mockReset().mockResolvedValue(BASELINE);
  apiState.put.mockReset().mockResolvedValue({ ok: true });
  apiState.post.mockReset();
});

describe("StyleShadowPane 手动面（免费可用）", () => {
  it("可手工添加覆盖行（PUT 落影子）；无信号不渲染 AI 建议区", async () => {
    render(
      <StyleShadowPane projectId="p1" chapterRef="vol-1-ch-1" archived={false} />,
    );
    // 基线只读可见
    expect(await screen.findByText("中长句为主")).toBeTruthy();
    // 无信号 → 无 AI 建议区、无锁定提示（门控已随入口迁去右栏）
    expect(screen.queryByText("AI 建议本章调整")).toBeNull();
    expect(screen.queryByText(/手动覆盖行不限档位/)).toBeNull();
    // 手工添加一行
    fireEvent.change(screen.getByDisplayValue("选择参数行"), { target: { value: "syntax" } });
    fireEvent.change(screen.getByTestId("shadow-add-value"), { target: { value: "短句为主" } });
    fireEvent.change(screen.getByTestId("shadow-add-reason"), { target: { value: "打斗章节奏" } });
    fireEvent.click(screen.getByTestId("shadow-add-btn"));
    await waitFor(() =>
      expect(apiState.put).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/style-shadow",
        { rows: { syntax: { value: "短句为主", reason: "打斗章节奏" } } },
      ),
    );
    // 新行以可编辑输入呈现（value 输入框存在）
    expect(await screen.findByTestId("shadow-value-syntax")).toBeTruthy();
  });

  it("归档章只读呈现：行输入与添加按钮均禁用", async () => {
    apiState.get.mockResolvedValue({
      ...BASELINE,
      shadow: { syntax: { value: "短句为主", reason: "r" } },
    });
    render(
      <StyleShadowPane projectId="p1" chapterRef="vol-1-ch-1" archived />,
    );
    const input = await screen.findByTestId("shadow-value-syntax");
    expect((input as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByTestId("shadow-add-btn") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("StyleShadowPane AI 建议（右栏信号触发）", () => {
  it("信号递增触发拉取；建议逐项采纳写影子", async () => {
    apiState.post.mockResolvedValue({
      suggestions: [{ row: "rhythm", value: "对话占比压低", reason: "对峙章" }],
    });
    const view = render(
      <StyleShadowPane projectId="p1" chapterRef="vol-1-ch-1" archived={false} suggestSignal={0} />,
    );
    await screen.findByText("中长句为主");
    expect(apiState.post).not.toHaveBeenCalled();
    // 右栏触发（信号 0→1）
    view.rerender(
      <StyleShadowPane projectId="p1" chapterRef="vol-1-ch-1" archived={false} suggestSignal={1} />,
    );
    await waitFor(() => expect(apiState.post).toHaveBeenCalled());
    const adopt = await screen.findByText("采纳");
    fireEvent.click(adopt);
    await waitFor(() =>
      expect(apiState.put).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/style-shadow",
        { rows: { rhythm: { value: "对话占比压低", reason: "对峙章" } } },
      ),
    );
  });
});
