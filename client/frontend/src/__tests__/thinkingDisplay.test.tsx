// c-thinking-display 前端四态（真 ChapterWorkspace 挂载＋可控 SSE 流）：
// ① 思考面板让位占位行 ② 首字转收起条＋回看抽屉 ③ 账目行完成补齐 ④ 守卫判死转超时卡；
// 无思考增量的生成维持既有阶段行（不出现空白思考区）。
// 打桩层＝`@/lib/api`＋`@/lib/toast`（沿 chapterWorkspace.plotFlow 同款）；
// SSE 走全局 fetch 桩的 ReadableStream——事件逐段投放，状态断言在流中途进行。
import { createRef } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

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

/** 可控 SSE：事件逐段投放（面板态能在流中途断言） */
function stubSseFetch() {
  let send!: (s: string) => void;
  let close!: () => void;
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      const enc = new TextEncoder();
      send = (s: string) => c.enqueue(enc.encode(s));
      close = () => c.close();
    },
  });
  const ev = (obj: unknown) => send(`data: ${JSON.stringify(obj)}\n\n`);
  const fetchMock = vi.fn(async (url: string) => {
    if (String(url).includes("/ai-model")) {
      return new Response(JSON.stringify({ effective_model: "MiniMax-M3.1-Flash" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(stream, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { ev, close };
}

function mountWorkspace() {
  const chaptersMap = new Map<string, any>([[REF, { ...FULL }]]);
  const outline = {
    volumes: [
      { ref: "vol-1", title: "第一卷", chapters: [
        { chapter: 2, title: "锚点", archived: false, has_prose: false, word_count: 0 },
      ] },
    ],
    chaptersMap,
    loadChapterData: vi.fn(async (ref: string) => chaptersMap.get(ref)),
    saveChapter: vi.fn(async () => ({})),
    confirmChapter: vi.fn(async () => {}),
    unconfirmChapter: vi.fn(async () => {}),
    refetchTree: vi.fn(async () => {}),
  };
  render(
    <MemoryRouter>
      <ChapterWorkspace
        projectId="p1"
        chapterRef={REF}
        outline={outline as never}
        wb={{
          volumes: [{ name: "vol-1", chapters: [{ chapter: 2, title: "锚点", archived: false }] }],
          refresh: vi.fn(async () => {}),
        } as never}
        isPro
        proseRef={createRef()}
        aiState={INITIAL_PROSE_AI_STATE}
        onAIStateChange={() => {}}
        bookWords={10}
        onRailData={() => {}}
        aiWriteSignal={0}
        onRevert={() => {}}
        onTreeRefresh={async () => {}}
      />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("c-thinking-display 四态（真组件＋可控 SSE）", () => {
  it("①→②→③ 思考面板让位占位行，首字转收起条，完成后账目行补齐", async () => {
    mockApi.get.mockImplementation(async (url: string) => {
      if (url.includes("/characters")) return [];
      return { ...FULL };
    });
    const sse = stubSseFetch();
    const proseRef = createRef<any>();
    render(
      <MemoryRouter>
        <ChapterWorkspace
          projectId="p1"
          chapterRef={REF}
          outline={{
            volumes: [
              { ref: "vol-1", title: "第一卷", chapters: [
                { chapter: 2, title: "锚点", archived: false, has_prose: false, word_count: 0 },
              ] },
            ],
            chaptersMap: new Map([[REF, { ...FULL }]]),
            loadChapterData: vi.fn(async () => ({ ...FULL })),
            saveChapter: vi.fn(async () => ({})),
            confirmChapter: vi.fn(async () => {}),
            unconfirmChapter: vi.fn(async () => {}),
            refetchTree: vi.fn(async () => {}),
          } as never}
          wb={{
            volumes: [{ name: "vol-1", chapters: [{ chapter: 2, title: "锚点", archived: false }] }],
            refresh: vi.fn(async () => {}),
          } as never}
          isPro
          proseRef={proseRef}
          aiState={INITIAL_PROSE_AI_STATE}
          onAIStateChange={() => {}}
          bookWords={10}
          onRailData={() => {}}
          aiWriteSignal={0}
          onRevert={() => {}}
          onTreeRefresh={async () => {}}
        />
      </MemoryRouter>,
    );

    await switchToProse();
    // 开流：阶段行先行（assemble）
    actStart(proseRef);
    expect(await screen.findByTestId("gen-line")).toBeTruthy();
    expect(screen.getByTestId("gen-line").textContent).toContain("准备本章素材");

    // 首个思考增量：面板出现、占位行让位、模型名呈现
    sse.ev({ type: "phase", phase: "model" });
    sse.ev({ type: "thinking", text: "先谋篇" });
    const panel = await screen.findByTestId("think-panel");
    await waitFor(() => expect(screen.queryByTestId("gen-line")).toBeNull());
    // 节流渲染（~100ms 合批）与模型名懒取都是异步落定——逐项 waitFor
    await waitFor(() => expect(panel.textContent).toContain("先谋篇"));
    await waitFor(() => expect(panel.textContent).toContain("MiniMax-M3.1-Flash"));
    expect(panel.textContent).toContain("思考过程");
    expect(panel.textContent).toContain("已思考");
    expect(panel.textContent).toContain("不会写进正文");

    // 后续增量合入同一面板（全量保留）
    sse.ev({ type: "thinking", text: "后落笔" });
    await waitFor(() => expect(panel.textContent).toContain("后落笔"));

    // 首字到达：面板收起为收起条（可展开回看），呼吸期正文写入
    sse.ev({ type: "chunk", text: "夜雨落在青瓦上。" });
    await waitFor(() => expect(screen.queryByTestId("think-panel")).toBeNull());
    const bar = screen.getByTestId("think-bar");
    expect(bar.textContent).toContain("思考完成 · 0 秒");
    fireEvent.click(bar);
    const drawer = await screen.findByTestId("think-drawer");
    expect(drawer.textContent).toContain("先谋篇");
    expect(drawer.textContent).toContain("后落笔");

    // 完成：账目行补齐生成用时与正文字数；正文零思考混入
    sse.ev({
      type: "done",
      full_text: "夜雨落在青瓦上。",
      tokens: 10,
      word_check: { target: 1800, actual: 8, below_limit: true },
    });
    sse.close();
    await waitFor(() => expect(bar.textContent).toContain("本章生成完毕"));
    // 账目行在回看抽屉头（条上只留摘要）：抽屉此前已展开，随完成补齐
    const drawerAfter = screen.getByTestId("think-drawer");
    await waitFor(() => expect(drawerAfter.textContent).toMatch(/生成 \d+ 秒 · 正文 8 字/));
    expect(screen.queryByTestId("think-panel")).toBeNull();
  });

  it("④ 守卫判死转超时卡：正文保持原样、已到达思考保留可回看", async () => {
    mockApi.get.mockImplementation(async (url: string) => {
      if (url.includes("/characters")) return [];
      return { ...FULL };
    });
    const sse = stubSseFetch();
    const proseRef = createRef<any>();
    render(
      <MemoryRouter>
        <ChapterWorkspace
          projectId="p1"
          chapterRef={REF}
          outline={{
            volumes: [
              { ref: "vol-1", title: "第一卷", chapters: [
                { chapter: 2, title: "锚点", archived: false, has_prose: false, word_count: 0 },
              ] },
            ],
            chaptersMap: new Map([[REF, { ...FULL }]]),
            loadChapterData: vi.fn(async () => ({ ...FULL })),
            saveChapter: vi.fn(async () => ({})),
            confirmChapter: vi.fn(async () => {}),
            unconfirmChapter: vi.fn(async () => {}),
            refetchTree: vi.fn(async () => {}),
          } as never}
          wb={{
            volumes: [{ name: "vol-1", chapters: [{ chapter: 2, title: "锚点", archived: false }] }],
            refresh: vi.fn(async () => {}),
          } as never}
          isPro
          proseRef={proseRef}
          aiState={INITIAL_PROSE_AI_STATE}
          onAIStateChange={() => {}}
          bookWords={10}
          onRailData={() => {}}
          aiWriteSignal={0}
          onRevert={() => {}}
          onTreeRefresh={async () => {}}
        />
      </MemoryRouter>,
    );

    await switchToProse();
    actStart(proseRef);
    sse.ev({ type: "phase", phase: "model" });
    sse.ev({ type: "thinking", text: "想了很久" });
    await screen.findByTestId("think-panel");
    sse.ev({
      type: "error",
      error: "模型思考太久（601 秒未产出正文），已停止——可直接重试；反复出现时把思考强度调低",
      kind: "thinking_timeout",
      thinking: true,
    });
    sse.close();

    const card = await screen.findByTestId("think-timeout");
    expect(card.textContent).toContain("本次生成已停止");
    expect(card.textContent).toContain("601 秒");
    expect(card.textContent).toContain("已保留它的思考内容");
    // 展开回看：已到达思考保留
    fireEvent.click(screen.getByTestId("think-see"));
    expect(screen.getByTestId("think-drawer").textContent).toContain("想了很久");
    // 重新生成入口在场；「知道了」收卡（思考收起条保留可回看）
    expect(screen.getByTestId("think-regen")).toBeTruthy();
    fireEvent.click(screen.getByTestId("think-dismiss"));
    await waitFor(() => expect(screen.queryByTestId("think-timeout")).toBeNull());
    expect(screen.getByTestId("think-bar")).toBeTruthy();
  });

  it("无思考增量维持既有阶段行，不出现空白思考区", async () => {
    mockApi.get.mockImplementation(async (url: string) => {
      if (url.includes("/characters")) return [];
      return { ...FULL };
    });
    const sse = stubSseFetch();
    const proseRef = createRef<any>();
    render(
      <MemoryRouter>
        <ChapterWorkspace
          projectId="p1"
          chapterRef={REF}
          outline={{
            volumes: [
              { ref: "vol-1", title: "第一卷", chapters: [
                { chapter: 2, title: "锚点", archived: false, has_prose: false, word_count: 0 },
              ] },
            ],
            chaptersMap: new Map([[REF, { ...FULL }]]),
            loadChapterData: vi.fn(async () => ({ ...FULL })),
            saveChapter: vi.fn(async () => ({})),
            confirmChapter: vi.fn(async () => {}),
            unconfirmChapter: vi.fn(async () => {}),
            refetchTree: vi.fn(async () => {}),
          } as never}
          wb={{
            volumes: [{ name: "vol-1", chapters: [{ chapter: 2, title: "锚点", archived: false }] }],
            refresh: vi.fn(async () => {}),
          } as never}
          isPro
          proseRef={proseRef}
          aiState={INITIAL_PROSE_AI_STATE}
          onAIStateChange={() => {}}
          bookWords={10}
          onRailData={() => {}}
          aiWriteSignal={0}
          onRevert={() => {}}
          onTreeRefresh={async () => {}}
        />
      </MemoryRouter>,
    );

    await switchToProse();
    actStart(proseRef);
    sse.ev({ type: "phase", phase: "prompt" });
    sse.ev({ type: "phase", phase: "model" });
    expect(await screen.findByTestId("gen-line")).toBeTruthy();
    expect(screen.getByTestId("gen-line").textContent).toContain("模型思考中");
    expect(screen.queryByTestId("think-panel")).toBeNull();

    // 无思考直出正文：首字即退场，不残留任何思考呈现
    sse.ev({ type: "chunk", text: "直出正文。" });
    await waitFor(() => expect(screen.queryByTestId("gen-line")).toBeNull());
    expect(screen.queryByTestId("think-panel")).toBeNull();
    expect(screen.queryByTestId("think-bar")).toBeNull();
    sse.ev({ type: "done", full_text: "直出正文。", tokens: 5 });
    sse.close();
  });
});

/** 切到正文页签（工作区默认章纲页签——ProsePane 挂载但 hidden） */
async function switchToProse() {
  fireEvent.click(await screen.findByRole("tab", { name: /^正文/ }));
}

/** 开流（绕过弹窗链：组件级钉走 startWriting 指令口） */
function actStart(proseRef: { current: { startWriting: (p?: string) => void } | null }) {
  // 等挂载稳定后触发；ProsePane.startStream 自带 streaming 守卫
  setTimeout(() => {
    proseRef.current?.startWriting("测试提示词");
  }, 0);
}
