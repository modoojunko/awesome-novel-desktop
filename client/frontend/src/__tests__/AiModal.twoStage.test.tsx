// ai-prompt-crafting 7.1 — AiModal 两段式交互：
// 粗组稿标「未润色」+ AI 润色按钮；润色成功换稿换标；失败可重试；
// 存量（polished）无润色按钮；编辑后确认透传提示词。
// c-prompt-tab-retire：新增「存为本章提示词」（PUT prompts/write）与 onPromptSaved。
// 「刷新提示词」：fresh=1 绕过存量行重新组装（换稿＋转未润色），失败不动当前稿。
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AiModal } from "@/components/novel/workbench/modals";

const reqState = vi.hoisted(() => ({ request: vi.fn(), put: vi.fn() }));
const polishState = vi.hoisted(() => ({ polishWritePrompt: vi.fn() }));
const toastState = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  info: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ request: reqState.request, api: { put: reqState.put } }));
vi.mock("@/lib/ai", () => ({ polishWritePrompt: polishState.polishWritePrompt }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

function renderModal(onConfirm = vi.fn(), onPromptSaved = vi.fn()) {
  render(
    <AiModal
      open
      onClose={vi.fn()}
      projectId="p1"
      chapterRef="vol-1-ch-1"
      onConfirm={onConfirm}
      onPromptSaved={onPromptSaved}
    />,
  );
  return { onConfirm, onPromptSaved };
}

beforeEach(() => {
  vi.clearAllMocks();
  reqState.put.mockResolvedValue({});
  reqState.request.mockResolvedValue({
    prompt: "## 角色定位\n粗组稿",
    has_outline: true,
    polished: false,
  });
});

describe("AiModal 两段式", () => {
  it("粗组稿：标「未润色」+ 出现「AI 润色」按钮", async () => {
    renderModal();
    const ta = await screen.findByTestId("ai-prompt");
    expect((ta as HTMLTextAreaElement).value).toContain("粗组稿");
    expect(screen.getByTestId("ai-raw-tag").textContent).toBe("未润色");
    expect(screen.getByTestId("ai-polish")).toBeTruthy();
  });

  it("存量提示词：标「已润色」且不出现润色按钮", async () => {
    reqState.request.mockResolvedValue({
      prompt: "## 任务指示\n润色过的存量稿",
      has_outline: true,
      polished: true,
    });
    renderModal();
    await screen.findByTestId("ai-polished-tag");
    expect(screen.queryByTestId("ai-polish")).toBeNull();
  });

  it("刷新提示词：fresh=1 重新组装 + 换稿转未润色 + 润色按钮回归", async () => {
    reqState.request
      .mockResolvedValueOnce({
        prompt: "## 任务指示\n润色过的存量稿",
        has_outline: true,
        polished: true,
      })
      .mockResolvedValueOnce({
        prompt: "## 角色定位\n按新章纲重组稿",
        has_outline: true,
        polished: false,
      });
    renderModal();
    await screen.findByTestId("ai-polished-tag");
    fireEvent.click(screen.getByTestId("ai-prompt-refresh"));
    await waitFor(() =>
      expect((screen.getByTestId("ai-prompt") as HTMLTextAreaElement).value).toContain(
        "按新章纲重组稿",
      ),
    );
    // 第二次请求带 fresh=1（绕过存量行组装）
    expect(reqState.request).toHaveBeenLastCalledWith(
      "/novels/p1/chapters/vol-1-ch-1/write/prompt?fresh=1",
      { quiet: true },
    );
    expect(screen.getByTestId("ai-raw-tag").textContent).toBe("未润色");
    expect(screen.getByTestId("ai-polish")).toBeTruthy();
  });

  it("刷新失败：报错 toast 且既有稿不清空", async () => {
    reqState.request
      .mockResolvedValueOnce({
        prompt: "## 任务指示\n存量稿",
        has_outline: true,
        polished: true,
      })
      .mockRejectedValueOnce(new Error("组装失败"));
    renderModal();
    await screen.findByTestId("ai-polished-tag");
    fireEvent.click(screen.getByTestId("ai-prompt-refresh"));
    await waitFor(() => expect(toastState.error).toHaveBeenCalledWith("组装失败"));
    expect((screen.getByTestId("ai-prompt") as HTMLTextAreaElement).value).toContain(
      "存量稿",
    );
  });

  it("点击「AI 润色」→ 换稿 + 标记已润色 + 成功 toast", async () => {
    polishState.polishWritePrompt.mockResolvedValue("## 任务指示\n润色新稿");
    renderModal();
    await screen.findByTestId("ai-prompt");
    fireEvent.click(screen.getByTestId("ai-polish"));
    await waitFor(() =>
      expect((screen.getByTestId("ai-prompt") as HTMLTextAreaElement).value).toContain(
        "润色新稿",
      ),
    );
    expect(polishState.polishWritePrompt).toHaveBeenCalledWith("p1", "vol-1-ch-1");
    expect(screen.getByTestId("ai-polished-tag")).toBeTruthy();
    expect(screen.queryByTestId("ai-polish")).toBeNull();
    expect(toastState.success).toHaveBeenCalled();
  });

  it("润色失败：就地报错可重试；既有稿不清空", async () => {
    polishState.polishWritePrompt
      .mockRejectedValueOnce(new Error("润色产物未覆盖必备段，可重试"))
      .mockResolvedValueOnce("## 任务指示\n重试成功稿");
    renderModal();
    await screen.findByTestId("ai-prompt");
    fireEvent.click(screen.getByTestId("ai-polish"));
    await waitFor(() =>
      expect(screen.getByText(/润色产物未覆盖必备段/)).toBeTruthy(),
    );
    // 失败不清空粗组稿
    expect((screen.getByTestId("ai-prompt") as HTMLTextAreaElement).value).toContain(
      "粗组稿",
    );
    fireEvent.click(screen.getByText("重试润色"));
    await waitFor(() =>
      expect((screen.getByTestId("ai-prompt") as HTMLTextAreaElement).value).toContain(
        "重试成功稿",
      ),
    );
  });

  it("存为本章提示词：PUT prompts/write + 转存量标 + onPromptSaved", async () => {
    reqState.put.mockResolvedValue({});
    const { onPromptSaved } = renderModal();
    await screen.findByTestId("ai-prompt");
    fireEvent.change(screen.getByTestId("ai-prompt"), {
      target: { value: "## 任务指示\n作家存稿" },
    });
    fireEvent.click(screen.getByTestId("ai-prompt-save"));
    await waitFor(() =>
      expect(reqState.put).toHaveBeenCalledWith(
        "/novels/p1/chapters/vol-1-ch-1/prompts/write",
        { content: "## 任务指示\n作家存稿" },
      ),
    );
    await screen.findByTestId("ai-polished-tag");
    expect(toastState.success).toHaveBeenCalledWith("已存为本章提示词");
    expect(onPromptSaved).toHaveBeenCalled();
  });

  it("编辑后「生成正文」透传当前提示词", async () => {
    const { onConfirm } = renderModal();
    await screen.findByTestId("ai-prompt");
    fireEvent.change(screen.getByTestId("ai-prompt"), {
      target: { value: "## 任务指示\n作家手改稿" },
    });
    fireEvent.click(screen.getByTestId("ai-confirm"));
    expect(onConfirm).toHaveBeenCalledWith("## 任务指示\n作家手改稿");
  });
});
