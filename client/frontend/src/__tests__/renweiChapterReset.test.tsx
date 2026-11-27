/** 人味标注切章清账·集成钉（c-renwei-chapter-reset）：真 ChapterWorkspace＋ProsePane
 *  挂载（harness 口径同 chapterRailDirtySync / chapterWorkspace.plotFlow——jsdom 里
 *  TipTap 可跑，不 mock ProsePane）。钉两根接线，防未来重构把 hook 拆掉测试不红：
 *  1) 标记到正文后同章改稿：700ms 重扫 diff 消卡（干净段注退场＋「过关」toast）；
 *  2) 重扫在途时切章：标注随章清账，旧章结果回来不复活、不 toast——
 *     没有重扫链里的 staleResult 拦截行这根钉必红。
 *  驱动方式：弹窗走 ProseHandle.openRenweiCheck；docChanged 走 store.setProse
 *  外部替换（→ replaceDocNoHistory 事务，与切章/归档恢复同路径）。
 */
import { createRef, type RefObject } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

const mockCheck = vi.fn();
vi.mock("@/lib/renwei", () => ({
  renweiCheck: (...args: unknown[]) => mockCheck(...args),
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

vi.mock("@/lib/panelAnchor", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/panelAnchor")>();
  return { ...actual, htmlZoom: () => 1 };
});

import { toast } from "@/lib/toast";
import ChapterWorkspace from "@/components/novel/workbench/ChapterWorkspace";
import { INITIAL_PROSE_AI_STATE, type ProseHandle } from "@/components/novel/workbench/ProsePane";
import { resetChapterStoresForTest, useChapterData } from "@/hooks/useChapterData";
import type { RenweiFinding, RenweiReport } from "@/lib/renwei";

const REF_A = "vol-1-ch-2";
const REF_B = "vol-1-ch-3";

// 四个非空段：findings 的 para 1/3 都有落点；B 章同段数——若在途判弃失守，
// 旧章结果落回 B 会重新长出注，断言才有区分力。
const PROSE = "晨光从百叶缝里切进来。\n他把杯子往桌上一放。\n她没抬头，笔尖还在走。\n窗外有人喊了一嗓子。";

function chapter(ref: string) {
  return {
    volume: 1,
    chapter: Number(ref.slice(-1)),
    title: "锚点",
    status: "draft",
    outline: { summary: "陆沉查舱段结构" },
    prose: PROSE,
  };
}

/** 章纲/卷树最小桩（同 chapterRailDirtySync 口径），A/B 两章都在场 */
function makeOutline() {
  const map = new Map<string, any>([
    [REF_A, chapter(REF_A)],
    [REF_B, chapter(REF_B)],
  ]);
  return {
    volumes: [
      {
        ref: "vol-1",
        title: "第一卷",
        chapters: [
          { chapter: 2, title: "锚点", archived: false, has_prose: true, word_count: 40 },
          { chapter: 3, title: "锚点", archived: false, has_prose: true, word_count: 40 },
        ],
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
  volumes: [
    {
      name: "vol-1",
      chapters: [
        { chapter: 2, title: "锚点", archived: false },
        { chapter: 3, title: "锚点", archived: false },
      ],
    },
  ],
  refresh: vi.fn(async () => {}),
};

const FINDING_DASH: RenweiFinding = {
  rule_id: "dash", rule: "破折号", sev: "err", para: 1,
  before: "他把杯子往桌上一放", hit: "——", after: "她没抬头",
  why: "破折号是典型的机器味。", fix: "改逗号或句号断开。",
};
const FINDING_RUN: RenweiFinding = {
  rule_id: "run_len", rule: "句长趋同连串", sev: "warn", para: 3,
  before: "", hit: "连续 3 句句长 12/13/11 字", after: "",
  why: "连续 3 句长度几乎一样——真人句子忽长忽短，趋同是批量感指纹。",
  fix: "拆一句、并两句或删一个子句——不加字；不要全砍短句。",
};

function report(findings: RenweiFinding[]): RenweiReport {
  return {
    ok: true,
    chars: 40,
    paras: 4,
    score: { rate: 53.9, band: "偏机器", cls: "warn" },
    priorities: [],
    metrics: [],
    findings,
    short_chapter: false,
    mtld_unconverged: false,
  };
}
const REPORT_A = report([FINDING_DASH, FINDING_RUN]);
const REPORT_A_CLEANED = report([FINDING_RUN]); // 段 1 改干净：只剩段 3

/** 测试驱动臂：与 ProsePane 共享同章单例 store，setProse 触发外部整文档替换 */
let storeA: ReturnType<typeof useChapterData> | null = null;
function StoreDriver() {
  storeA = useChapterData("p1", REF_A);
  return null;
}

describe("人味标注切章清账（ChapterWorkspace 集成）", () => {
  let proseRef: RefObject<ProseHandle | null>;

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    resetChapterStoresForTest();
    storeA = null;
    proseRef = createRef();
    apiState.get.mockImplementation(async () => chapter(REF_A));
    apiState.put.mockResolvedValue({});
  });

  /** 挂 A 章 → 开人味弹窗 → 检测 → 标记到正文（注在场）；返回按 ref 重挂的 rerenderAt */
  async function markToBody(outline: ReturnType<typeof makeOutline>) {
    const view = render(
      <MemoryRouter>
        <ChapterWorkspace
          projectId="p1"
          chapterRef={REF_A}
          outline={outline as never}
          wb={wb as never}
          isPro
          proseRef={proseRef}
          aiState={INITIAL_PROSE_AI_STATE}
          onAIStateChange={() => {}}
          bookWords={40}
          onRailData={() => {}}
          aiWriteSignal={0}
          onRevert={() => {}}
          onTreeRefresh={async () => {}}
        />
        <StoreDriver />
      </MemoryRouter>,
    );
    const rerenderAt = (ref: string) =>
      view.rerender(
        <MemoryRouter>
          <ChapterWorkspace
            projectId="p1"
            chapterRef={ref}
            outline={outline as never}
            wb={wb as never}
            isPro
            proseRef={proseRef}
            aiState={INITIAL_PROSE_AI_STATE}
            onAIStateChange={() => {}}
            bookWords={40}
            onRailData={() => {}}
            aiWriteSignal={0}
            onRevert={() => {}}
            onTreeRefresh={async () => {}}
          />
          <StoreDriver />
        </MemoryRouter>,
      );

    act(() => proseRef.current?.openRenweiCheck?.());
    fireEvent.click(screen.getByTestId("renwei-start"));
    await waitFor(() => expect(screen.getByTestId("rw-score")).toBeTruthy());
    fireEvent.click(screen.getByTestId("renwei-mark"));
    await waitFor(() => expect(screen.getByTestId("rw-note-1")).toBeTruthy());
    expect(screen.getByTestId("rw-note-3")).toBeTruthy();
    expect(document.querySelectorAll(".rw-mark")).toHaveLength(2);
    return { view, rerenderAt };
  }

  it("同章改稿：700ms 重扫 diff 消卡——干净段注退场＋过关 toast，未干净段保留", async () => {
    const outline = makeOutline();
    mockCheck.mockResolvedValueOnce(REPORT_A).mockResolvedValueOnce(REPORT_A_CLEANED);
    await markToBody(outline);

    // 外部整文档替换＝docChanged 事务 → 防抖重扫（与切章/归档恢复同路径）
    act(() => storeA?.setProse(PROSE.replace("晨光从百叶缝里切进来。", "晨光从百叶缝里漏进来。")));
    await waitFor(() => expect(mockCheck).toHaveBeenCalledTimes(2));
    // 第二轮按改后正文算：段 1 干净 → 自动记「已改」，注退场＋toast；段 3 未动保留
    await waitFor(() => expect(screen.queryByTestId("rw-note-1")).toBeNull());
    expect(screen.getByTestId("rw-note-3")).toBeTruthy();
    expect(vi.mocked(toast.success)).toHaveBeenCalled();
  });

  it("重扫在途切章：标注随章清账，旧章结果回来不复活、不 toast", async () => {
    const outline = makeOutline();
    let resolveChain: (r: RenweiReport) => void = () => {};
    mockCheck
      .mockResolvedValueOnce(REPORT_A)
      .mockImplementationOnce(
        () => new Promise<RenweiReport>((resolve) => { resolveChain = resolve; }),
      );
    const { rerenderAt } = await markToBody(outline);

    // 在途：重扫已发出、结果悬着（对应 flush→check 半路）
    act(() => storeA?.setProse(PROSE.replace("晨光从百叶缝里切进来。", "晨光从百叶缝里漏进来。")));
    await waitFor(() => expect(mockCheck).toHaveBeenCalledTimes(2));

    // 切章：清账先行——注与标记全退场
    rerenderAt(REF_B);
    expect(screen.queryByTestId("rw-note-1")).toBeNull();
    expect(screen.queryByTestId("rw-note-3")).toBeNull();
    expect(document.querySelectorAll(".rw-mark")).toHaveLength(0);

    // 旧章结果此刻才回来：staleResult 拦截——不消卡、不 toast、不复活注
    await act(async () => {
      resolveChain(REPORT_A);
    });
    expect(screen.queryByTestId("rw-note-1")).toBeNull();
    expect(screen.queryByTestId("rw-note-3")).toBeNull();
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled();
  });
});
