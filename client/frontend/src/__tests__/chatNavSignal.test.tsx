// 助手导航信号钉（c-agent-nav）：ChapterWorkspace 收到 chatNavSeq/chatNavTab
// → 真实切页签（与手点页签同语义）；坏 tab 忽略；seq 不动不切。
// 打桩层同 chapterWorkspace.plotFlow（@/lib/api＋@/lib/toast 最小桩）。
import { createRef } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  request: vi.fn(),
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

import { api } from "@/lib/api";
import ChapterWorkspace from "@/components/novel/workbench/ChapterWorkspace";
import { INITIAL_PROSE_AI_STATE } from "@/components/novel/workbench/ProsePane";

const mockApi = api as unknown as { get: ReturnType<typeof vi.fn> };

const REF = "vol-1-ch-2";

function mount(nav: { seq: number; tab: string }) {
  render(
    <MemoryRouter>
      <ChapterWorkspace
        projectId="p1"
        chapterRef={REF}
        outline={
          {
            volumes: [{ ref: "vol-1", title: "第一卷", chapters: [{ chapter: 2, title: "锚点", archived: false }] }],
            chaptersMap: new Map(),
            loadChapterData: vi.fn(async () => ({})),
            saveChapter: vi.fn(async () => ({})),
            confirmChapter: vi.fn(async () => {}),
            unconfirmChapter: vi.fn(async () => {}),
            refetchTree: vi.fn(async () => {}),
          } as never
        }
        wb={
          {
            volumes: [{ name: "vol-1", chapters: [{ chapter: 2, title: "锚点", archived: false }] }],
            refresh: vi.fn(async () => {}),
          } as never
        }
        isPro
        proseRef={createRef()}
        aiState={INITIAL_PROSE_AI_STATE}
        onAIStateChange={() => {}}
        bookWords={10}
        onRailData={() => {}}
        aiWriteSignal={0}
        chatNavSeq={nav.seq}
        chatNavTab={nav.tab}
        onRevert={() => {}}
        onTreeRefresh={async () => {}}
      />
    </MemoryRouter>,
  );
}

/** 当前激活页签文本（tablist 内 aria-selected=true 的页签） */
function activeTab(): string {
  const tabs = screen.getAllByRole("tab");
  const on = tabs.find((el) => el.getAttribute("aria-selected") === "true");
  return on?.textContent ?? "";
}

const FULL = {
  volume: 1,
  chapter: 2,
  title: "锚点",
  status: "draft",
  outline: { summary: "陆沉查舱段结构" },
  challenge: "旧档堆不对活人开放",
  ladder_exit: "拿到半张地图，连夜出门",
  plot_items: [],
  prose: "",
};

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.get.mockImplementation(async (url: string) => {
    if (url.includes("/characters")) return [];
    return { ...FULL };
  });
});

describe("助手导航信号（c-agent-nav）", () => {
  it("默认落在章纲页签（无信号不切）", async () => {
    mount({ seq: 0, tab: "" });
    await waitFor(() => expect(activeTab()).toContain("章纲"));
  });

  it("seq+tab=prose → 切到正文页签", async () => {
    mount({ seq: 1, tab: "prose" });
    await waitFor(() => expect(activeTab()).toContain("正文"));
  });

  it("切到伏笔页签（七值白名单内任意页签）", async () => {
    mount({ seq: 1, tab: "hooks" });
    await waitFor(() => expect(activeTab()).toContain("伏笔"));
  });

  it("坏 tab 值忽略——停在章纲", async () => {
    mount({ seq: 1, tab: "nope" });
    await waitFor(() => expect(screen.getAllByRole("tab").length).toBeGreaterThan(0));
    expect(activeTab()).toContain("章纲");
  });
});
