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

describe("unconfirmChapter（c-og-draft-no-autconfirm）", () => {
  it("撤回失败 → toast.error 透传，吞错不 rethrow", async () => {
    apiState.post.mockRejectedValue(new Error("本章已归档，请先恢复编辑"));
    const { result } = await mountHook();

    let resolved = false;
    await act(async () => {
      await result.current.unconfirmChapter("vol-1-ch-1");
      resolved = true;
    });
    expect(resolved).toBe(true);
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/chapters/vol-1-ch-1/unconfirm");
    expect(toastState.error).toHaveBeenCalledWith("本章已归档，请先恢复编辑");
  });

  it("撤回成功 → 不弹错，状态置 in_progress（确认过的章必填已齐）", async () => {
    apiState.post.mockResolvedValue({});
    const { result } = await mountHook();

    await act(async () => {
      await result.current.unconfirmChapter("vol-1-ch-1");
    });
    expect(toastState.error).not.toHaveBeenCalled();
    expect(result.current.chapterStatuses.get("vol-1-ch-1")).toBe("in_progress");
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

// ---------------------------------------------------------------------------
// deriveOutlineStatus 归档投影（c-og-badge-archived-confirm）：归档章计入确认
// 计数——后端 status 单列生命周期，归档收口覆写 confirmed，展示层由归档态蕴含。
// ---------------------------------------------------------------------------

// over 放宽为 Record：负钉需要塞 outline_status（树契约有吐、前端故意不读）
const chMeta = (over: Record<string, unknown> = {}) => ({
  ref: "vol-1-ch-1",
  volume: 1,
  chapter: 1,
  title: "第一章",
  word_count: 0,
  ...over,
});
const treeWith = (...chapters: Record<string, unknown>[]) => ({
  volumes: [
    { ref: "vol-1", title: "卷一", summary: "", chapter_count: chapters.length, chapters },
  ],
});

describe("deriveOutlineStatus 归档投影（c-og-badge-archived-confirm）", () => {
  it("树含归档章 → chapterStatuses=confirmed，confirmedCount 计入；全归档时 allConfirmed", async () => {
    apiState.get.mockResolvedValue(
      treeWith(chMeta({ status: "archived", archived: true }), chMeta({ ref: "vol-1-ch-2", status: "outline" })),
    );
    const { result } = await mountHook();
    expect(result.current.chapterStatuses.get("vol-1-ch-1")).toBe("confirmed");
    expect(result.current.confirmedCount).toBe(1);
    expect(result.current.totalChapters).toBe(2);
    expect(result.current.allConfirmed).toBe(false);

    apiState.get.mockResolvedValue(treeWith(chMeta({ status: "archived", archived: true })));
    const full = await mountHook();
    expect(full.result.current.confirmedCount).toBe(1);
    expect(full.result.current.allConfirmed).toBe(true);
  });

  it("分支顺序钉：loadChapterData 后（chapterData 带 summary）归档章仍 confirmed", async () => {
    apiState.get.mockImplementation((url: string) => {
      if (String(url).endsWith("/chapters/vol-1-ch-1")) {
        return Promise.resolve({
          outline: { summary: "归档前的章纲概要" },
        });
      }
      return Promise.resolve(treeWith(chMeta({ status: "archived", archived: true })));
    });
    const { result } = await mountHook();
    expect(result.current.chapterStatuses.get("vol-1-ch-1")).toBe("confirmed");
    await act(async () => {
      await result.current.loadChapterData("vol-1-ch-1");
    });
    // 判据在 chapterData 判定之前：真归档章 chapterData 带 summary，放后面会回落 in_progress
    expect(result.current.chapterStatuses.get("vol-1-ch-1")).toBe("confirmed");
  });

  it("unarchive 回落钉：树回 draft＋chaptersMap 仍持概要 → in_progress（徽标回落）", async () => {
    apiState.get.mockResolvedValue(treeWith(chMeta({ status: "archived", archived: true })));
    const { result } = await mountHook();
    expect(result.current.confirmedCount).toBe(1);

    apiState.get.mockImplementation((url: string) => {
      if (String(url).endsWith("/chapters/vol-1-ch-1")) {
        return Promise.resolve({ outline: { summary: "归档前的章纲概要" } });
      }
      return Promise.resolve(treeWith(chMeta({ status: "draft" })));
    });
    await act(async () => {
      await result.current.loadChapterData("vol-1-ch-1");
      await result.current.refetchTree();
    });
    expect(result.current.chapterStatuses.get("vol-1-ch-1")).toBe("in_progress");
    expect(result.current.confirmedCount).toBe(0);
  });

  it("负钉：不看 outline_status——draft 章（桩带 outline_status:confirmed）仍 in_progress", async () => {
    apiState.get.mockResolvedValue(
      treeWith({ ...chMeta({ status: "draft" }), outline_status: "confirmed" }),
    );
    const { result } = await mountHook();
    expect(result.current.chapterStatuses.get("vol-1-ch-1")).toBe("in_progress");
  });
});
