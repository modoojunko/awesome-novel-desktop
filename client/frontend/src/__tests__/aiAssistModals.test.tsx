// AI 检测/提示词精修弹窗（AiCheckModal / RefinePromptModal）行为测试：
// 打开即跑、finding 列表与空态、失败就地重试；精修采纳走提示词保存链并通知刷新。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AiCheckModal from "@/components/novel/workbench/AiCheckModal";
import RefinePromptModal from "@/components/novel/workbench/RefinePromptModal";

const libState = vi.hoisted(() => ({
  runAiCheck: vi.fn(),
  refinePrompt: vi.fn(),
  saveWritePrompt: vi.fn(),
}));
vi.mock("@/lib/aiCheck", async () => {
  const actual = await vi.importActual<typeof import("@/lib/aiCheck")>("@/lib/aiCheck");
  return {
    ...actual,
    runAiCheck: libState.runAiCheck,
    refinePrompt: libState.refinePrompt,
    saveWritePrompt: libState.saveWritePrompt,
  };
});

const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

beforeEach(() => {
  libState.runAiCheck.mockReset();
  libState.refinePrompt.mockReset();
  libState.saveWritePrompt.mockReset();
  toastState.success.mockReset();
  toastState.error.mockReset();
});

describe("AiCheckModal（检测结果弹窗）", () => {
  // 每个用例独立 spy（onClose 断言不能吃到上一个用例的调用）
  const base = () => ({
    open: true,
    onClose: vi.fn(),
    projectId: "p1",
    chapterRef: "vol-1-ch-2",
    chapterLabel: "第2章 · 渡口",
  });

  it("打开即跑检查：标题取类别名，finding 逐条展示", async () => {
    libState.runAiCheck.mockResolvedValue([
      { title: "第3段", detail: "人称从第三人称滑到第一人称" },
    ]);
    render(<AiCheckModal {...base()} kind="style_consistency" />);
    expect(screen.getByText("文风一致性检查")).toBeTruthy();
    expect(libState.runAiCheck).toHaveBeenCalledWith("p1", "vol-1-ch-2", "style_consistency");
    const list = await screen.findByTestId("ai-check-list");
    expect(list.textContent).toContain("第3段");
    expect(list.textContent).toContain("人称从第三人称滑到第一人称");
  });

  it("空结果 → 「没有发现明显问题」", async () => {
    libState.runAiCheck.mockResolvedValue([]);
    render(<AiCheckModal {...base()} kind="volume_conflict" />);
    expect(await screen.findByTestId("ai-check-empty")).toBeTruthy();
  });

  it("失败就地提示，可重新检查", async () => {
    libState.runAiCheck.mockRejectedValueOnce(new Error("AI 服务响应超时，请稍后重试"));
    render(<AiCheckModal {...base()} kind="hooks_conflict" />);
    expect(await screen.findByText("AI 服务响应超时，请稍后重试")).toBeTruthy();
    libState.runAiCheck.mockResolvedValueOnce([]);
    fireEvent.click(screen.getByRole("button", { name: /重新检查/ }));
    expect(await screen.findByTestId("ai-check-empty")).toBeTruthy();
    expect(libState.runAiCheck).toHaveBeenCalledTimes(2);
  });

  it("kind 为 null（关闭态）不触发请求", () => {
    render(<AiCheckModal {...base()} kind={null} open={false} />);
    expect(libState.runAiCheck).not.toHaveBeenCalled();
  });
});

describe("RefinePromptModal（提示词精修弹窗）", () => {
  const base = () => ({
    open: true,
    onClose: vi.fn(),
    projectId: "p1",
    chapterRef: "vol-1-ch-2",
    chapterLabel: "第2章 · 渡口",
    onAdopted: vi.fn(),
  });

  it("打开即跑精修：预览只读展示，采纳后保存并通知刷新", async () => {
    libState.refinePrompt.mockResolvedValue("## 任务指示\n精简后的提示词");
    libState.saveWritePrompt.mockResolvedValue(undefined);
    const props = base();
    render(<RefinePromptModal {...props} mode="concise" />);
    expect(screen.getByText("精简提示词")).toBeTruthy();
    expect(libState.refinePrompt).toHaveBeenCalledWith("p1", "vol-1-ch-2", "concise");
    const pre = await screen.findByTestId("refine-preview");
    expect(pre.textContent).toContain("精简后的提示词");

    fireEvent.click(screen.getByTestId("refine-adopt"));
    await waitFor(() => {
      expect(libState.saveWritePrompt).toHaveBeenCalledWith(
        "p1",
        "vol-1-ch-2",
        "## 任务指示\n精简后的提示词",
      );
    });
    expect(toastState.success).toHaveBeenCalledWith("已采纳并保存为本章提示词");
    expect(props.onAdopted).toHaveBeenCalled();
    expect(props.onClose).toHaveBeenCalled();
  });

  it("精修失败：不出预览，采纳保持禁用", async () => {
    libState.refinePrompt.mockRejectedValue(new Error("AI 调用失败，可重试"));
    render(<RefinePromptModal {...base()} mode="negative" />);
    expect(await screen.findByText("AI 调用失败，可重试")).toBeTruthy();
    expect((screen.getByTestId("refine-adopt") as HTMLButtonElement).disabled).toBe(true);
  });

  it("保存失败：toast 报错且不关闭（可再试）", async () => {
    libState.refinePrompt.mockResolvedValue("改后稿");
    libState.saveWritePrompt.mockRejectedValue(new Error("保存失败"));
    const props = base();
    render(<RefinePromptModal {...props} mode="concise" />);
    await screen.findByTestId("refine-preview");
    fireEvent.click(screen.getByTestId("refine-adopt"));
    await waitFor(() => {
      expect(toastState.error).toHaveBeenCalledWith("保存失败");
    });
    expect(props.onClose).not.toHaveBeenCalled();
  });
});
