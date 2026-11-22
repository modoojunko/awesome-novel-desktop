// 右栏页面态·脏标记同步（真机 2026-11-23）：状态栏已经是「已自动保存」，助手仍收到
// 「正文未保存」并劝作者先保存——dirty 里的保存态由 store.saveState 派生，而自动保存
// 翻转（unsaved → autosaving → saved）时字数不变；这份右栏数据的上抛依赖里漏了
// saveState / ogEditing，旧快照就会一直挂在 page_state.unsaved 上进提示词。
// 回归口径：保存落定后 / 退出章纲编辑后，dirty 必须重新上抛为空。
import { createRef } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  api: apiState,
  request: vi.fn(async () => ({ polished: false })),
}));
vi.mock("@/lib/toast", () => ({
  toast: {
    success: vi.fn(() => 101),
    error: vi.fn(() => 102),
    info: vi.fn(() => 103),
    dismiss: vi.fn(),
  },
  useToasts: () => [],
  Toaster: () => null,
}));

import ChapterWorkspace from "@/components/novel/workbench/ChapterWorkspace";
import { INITIAL_PROSE_AI_STATE } from "@/components/novel/workbench/ProsePane";
import { resetChapterStoresForTest, useChapterData } from "@/hooks/useChapterData";

const REF = "vol-1-ch-2";

const CHAPTER = {
  volume: 1,
  chapter: 2,
  title: "锚点",
  status: "draft",
  outline: { summary: "陆沉查舱段结构" },
  prose: "",
};

/** 章纲/卷树/章数据最小桩（同 chapterWorkspace.plotFlow 口径） */
function makeOutline() {
  const map = new Map<string, any>([[REF, { ...CHAPTER }]]);
  return {
    volumes: [
      {
        ref: "vol-1",
        title: "第一卷",
        chapters: [{ chapter: 2, title: "锚点", archived: false, has_prose: true, word_count: 10 }],
      },
    ],
    chaptersMap: map,
    loadChapterData: vi.fn(async (ref: string) => map.get(ref)),
    saveChapter: vi.fn(async () => ({})),
    confirmChapter: vi.fn(async () => {}),
    unconfirmChapter: vi.fn(async () => {}),
    refetchTree: vi.fn(async () => {}),
  };
}

const wb = {
  volumes: [{ name: "vol-1", chapters: [{ chapter: 2, title: "锚点", archived: false }] }],
  refresh: vi.fn(async () => {}),
};

/** 测试驱动臂：与 ChapterWorkspace 共享同章单例 store，直接灌正文 */
let hook: ReturnType<typeof useChapterData> | null = null;
function StoreDriver() {
  hook = useChapterData("p1", REF);
  return null;
}

function mount() {
  const outline = makeOutline();
  let rail: { dirty?: string[] } | null = null;
  render(
    <MemoryRouter>
      <ChapterWorkspace
        projectId="p1"
        chapterRef={REF}
        outline={outline as never}
        wb={wb as never}
        isPro
        proseRef={createRef()}
        aiState={INITIAL_PROSE_AI_STATE}
        onAIStateChange={() => {}}
        bookWords={10}
        onRailData={(d) => {
          rail = d;
        }}
        aiWriteSignal={0}
        onRevert={() => {}}
        onTreeRefresh={async () => {}}
      />
      <StoreDriver />
    </MemoryRouter>,
  );
  return { railData: () => rail };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  resetChapterStoresForTest();
  hook = null;
  apiState.get.mockImplementation(async (url: string) => {
    if (url.includes("/characters")) return [];
    return { ...CHAPTER };
  });
  apiState.put.mockResolvedValue({});
});

afterEach(() => {
  vi.useRealTimers();
});

describe("右栏 dirty 随保存态重新上抛（page_state 真值）", () => {
  it("自动保存落定后 dirty 清空——不再把「正文未保存」带进提示词", async () => {
    const { railData } = mount();
    await act(async () => {}); // flush 初始 load + 首次上抛
    expect(railData()).not.toBeNull();
    expect(railData()!.dirty).toEqual([]);

    vi.useFakeTimers();
    act(() => hook!.setProse("他把枪口转向门口。"));
    // 编辑中：真实态就该报未保存
    expect(railData()!.dirty).toContain("正文未保存");

    // 1.5s 防抖到期 → PUT /prose → saveState 回 saved（字数不变）
    await act(async () => {
      vi.advanceTimersByTime(1500);
    });
    await act(async () => {});

    expect(apiState.put).toHaveBeenCalledWith(`/novels/p1/chapters/${REF}/prose`, {
      prose: "他把枪口转向门口。",
    });
    expect(hook!.saveState).toBe("saved");
    // 状态栏同源显示「已自动保存」；右栏真值必须同步清掉旧快照
    expect(railData()!.dirty).toEqual([]);
  });

  it("退出章纲编辑后「章纲编辑中」退场", async () => {
    const { railData } = mount();
    await act(async () => {});
    expect(railData()).not.toBeNull();

    fireEvent.click(await screen.findByTestId("og-edit"));
    expect(railData()!.dirty).toContain("章纲编辑中");

    fireEvent.click(screen.getByText("取消"));
    expect(railData()!.dirty).toEqual([]);
  });
});
