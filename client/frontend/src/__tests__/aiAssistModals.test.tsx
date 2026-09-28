// AI 检测弹窗（AiCheckModal）行为测试：
// 打开即跑、finding 列表与空态、失败就地重试。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import AiCheckModal from "@/components/novel/workbench/AiCheckModal";

const libState = vi.hoisted(() => ({
  runAiCheck: vi.fn(),
}));
vi.mock("@/lib/aiCheck", async () => {
  const actual = await vi.importActual<typeof import("@/lib/aiCheck")>("@/lib/aiCheck");
  return {
    ...actual,
    runAiCheck: libState.runAiCheck,
  };
});

const toastState = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

beforeEach(() => {
  libState.runAiCheck.mockReset();
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
