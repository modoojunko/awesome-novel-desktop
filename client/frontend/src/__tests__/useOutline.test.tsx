import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

// ---------------------------------------------------------------------------
// useOutline — confirmChapter / transitionToPrompt 失败时 toast.error
// （入口是 onToggle 非 await 调用，必须吞错不能 rethrow）。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
const toastState = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  info: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));

const TREE = {
  volumes: [
    {
      ref: "vol-1",
      title: "卷一",
      summary: "",
      chapter_count: 1,
      chapters: [
        { ref: "vol-1-ch-1", volume: 1, chapter: 1, title: "第一章", status: "outline", word_count: 0 },
      ],
    },
  ],
};

beforeEach(() => {
  apiState.get.mockReset();
  apiState.post.mockReset();
  toastState.error.mockReset();
  apiState.get.mockResolvedValue(TREE);
});

async function mountHook(projectId = "p1") {
  const { useOutline } = await import("@/hooks/useOutline");
  const utils = renderHook(() => useOutline(projectId));
  await waitFor(() => expect(utils.result.current.loading).toBe(false));
  return utils;
}

describe("confirmChapter", () => {
  it("确认失败 → toast.error 透传后端具体缺失项，吞错不 rethrow", async () => {
    apiState.post.mockRejectedValue(new Error("章纲确认失败，请先填写：预期策略、段落规划"));
    const { result } = await mountHook();

    let resolved = false;
    await act(async () => {
      await result.current.confirmChapter("vol-1-ch-1");
      resolved = true;
    });
    expect(resolved).toBe(true);
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-1/confirm");
    expect(toastState.error).toHaveBeenCalledWith("章纲确认失败，请先填写：预期策略、段落规划");
  });

  it("确认失败且无错误详情 → 兜底文案", async () => {
    apiState.post.mockRejectedValue(new Error(""));
    const { result } = await mountHook();

    await act(async () => {
      await result.current.confirmChapter("vol-1-ch-1");
    });
    expect(toastState.error).toHaveBeenCalledWith("确认失败，请检查章节内容是否完整");
  });

  it("确认成功 → 不弹错，状态置 confirmed", async () => {
    apiState.post.mockResolvedValue({});
    const { result } = await mountHook();

    await act(async () => {
      await result.current.confirmChapter("vol-1-ch-1");
    });
    expect(toastState.error).not.toHaveBeenCalled();
    expect(result.current.chapterStatuses.get("vol-1-ch-1")).toBe("confirmed");
  });
});

describe("transitionToPrompt", () => {
  it("流转失败 → toast.error，吞错不 rethrow", async () => {
    apiState.post.mockRejectedValue(new Error("还有未完成章节"));
    const { result } = await mountHook();

    let resolved = false;
    await act(async () => {
      await result.current.transitionToPrompt();
      resolved = true;
    });
    expect(resolved).toBe(true);
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/workflow/transition", {
      target: "prompt",
    });
    expect(toastState.error).toHaveBeenCalledWith(
      "确认全部章纲失败，请检查是否还有未完成的章节",
    );
  });

  it("流转成功 → 不弹错", async () => {
    apiState.post.mockResolvedValue({});
    const { result } = await mountHook();

    await act(async () => {
      await result.current.transitionToPrompt();
    });
    expect(toastState.error).not.toHaveBeenCalled();
  });
});
