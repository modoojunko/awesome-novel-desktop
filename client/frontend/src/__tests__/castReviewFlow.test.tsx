// 人物精盘全链（c-character-intro 3.2/3.4 验证项）：11 态流转含两形态/多缺人回程/
// suggest 预填三态+defaulted/延后零请求/降档恢复无卡面/error 两 kind 三出口/双击互斥/
// 落账双同步+PUT 载荷/409 回落+created 重试/warnings 上屏/refreshCharacterNames/黑话清零。
// 打桩层＝`@/lib/api`＋`@/lib/toast`（章纲保存链走 outline 桩，与 chapterWorkspace.plotFlow 同款）。
import { createRef } from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() },
  request: vi.fn(),
  errMessage: (e: unknown, fallback: string) => {
    const err = e as { status?: number; message?: string } | null;
    return err?.status && err.status >= 400 && err.status < 500 && err.message
      ? err.message
      : fallback;
  },
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

import { api, request } from "@/lib/api";
import { toast } from "@/lib/toast";
import ChapterWorkspace from "@/components/novel/workbench/ChapterWorkspace";
import { INITIAL_PROSE_AI_STATE } from "@/components/novel/workbench/ProsePane";

const mockApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};
const mockReq = request as unknown as ReturnType<typeof vi.fn>;
const mockToast = toast as unknown as Record<string, ReturnType<typeof vi.fn>>;

const REF = "vol-1-ch-2";

/** 盘点响应：老角色能演/不起名也行/缺一个新角色（suggest 三值各一）＋软提示 */
const REVIEW = {
  rows: [
    { idx: 0, echo: "巷口又见袭击", verdict: "老角色能演", who: ["林野", "陈叔"], as: "", why: "师徒夜巡接得住", gap: null, defaulted: false },
    { idx: 1, echo: "老药铺取止血散", verdict: "不起名也行", who: [], as: "守夜伙计", why: "过场戏不用起名", gap: null, defaulted: false },
    {
      idx: 2, echo: "城墙根收到血记号", verdict: "缺一个新角色", who: [], as: "",
      why: "林野不该未卜先知",
      gap: { need: "认得城南水路的线人", why_not_old: "陈叔的消息网到不了城南", suggest: "加人" },
      defaulted: false,
    },
    {
      idx: 3, echo: "码头夜渡", verdict: "缺一个新角色", who: [], as: "",
      why: "缺一个船家",
      gap: { need: "肯半夜开船的船家", why_not_old: "守夜人不出城", suggest: "延后" },
      defaulted: true,
    },
  ],
  quota: { named_count: 3, regime: "open" },
  hints: [{ name: "秦伯", text: "无卡名字「秦伯」已出现在 2 章的出场名单里" }],
  warnings: ["剧情 2「老角色能演」列出的名字都不在已知名单里，这一行先留着，请自己核对"],
};

const CARD = (name: string, axis: string, grade: string, duty: string) => ({
  axis,
  name,
  persona: `${name}的一句人设`,
  entrance: `${name}的出场`,
  exit_kind: "本卷退场",
  exit_note: `${name}的退场`,
  grade,
  ranks: { 合不合适: 1, 差别在哪: 2, 好不好落地: 3 },
  reasons: { 合不合适: "对口", 差别在哪: "不压", 好不好落地: "好收" },
  duty,
  why_not_old: "陈叔的消息网到不了城南",
});

const DRAW = {
  cards: [
    CARD("魏七", "功能", "S", "城南消息贩子"),
    CARD("灯伯", "关系", "A", "水关的老更夫"),
    CARD("祝九娘", "身份", "B", "渡口船娘"),
  ],
  note: "",
};

const FULL = {
  volume: 1,
  chapter: 2,
  title: "锚点",
  status: "draft",
  outline: { summary: "林野夜巡撞见第二起袭击", characters: ["林野", "陈叔", "秦伯"] },
  challenge: "旧档堆不对活人开放",
  ladder_exit: "拿到半张地图",
  plot_items: ["巷口又见袭击", "老药铺取止血散", "城墙根收到血记号", "码头夜渡"],
  prose: "",
};

function makeOutline(server: Record<string, unknown>) {
  const map = new Map<string, any>([[REF, server]]);
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
    saveChapter: vi.fn(async (ref: string, data: Record<string, any>) => {
      const cur = map.get(ref) ?? { volume: 1, chapter: 2, title: "锚点", status: "draft" };
      map.set(ref, {
        ...cur,
        ...data,
        outline: { ...(cur.outline ?? {}), ...(data.outline ?? {}) },
      });
      return {};
    }),
    confirmChapter: vi.fn(async () => {}),
    refetchTree: vi.fn(async () => {}),
    transitionToPrompt: vi.fn(async () => {}),
  };
}

const wb = {
  volumes: [{ name: "vol-1", chapters: [{ chapter: 2, title: "锚点", archived: false }] }],
  refresh: vi.fn(async () => {}),
};

function mount(opts: { server?: Record<string, unknown>; isPro?: boolean } = {}) {
  const outline = makeOutline(opts.server ?? FULL);
  let rail: any = null;
  const { unmount } = render(
    <MemoryRouter>
      <ChapterWorkspace
        projectId="p1"
        chapterRef={REF}
        outline={outline as never}
        wb={wb as never}
        isPro={opts.isPro ?? true}
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
    </MemoryRouter>,
  );
  return { outline, railData: () => rail, unmount };
}

/** 开弹窗（右栏入口＝railData 的 onCastReview；openCastReview 只 flush+setOpen） */
async function openReview(railData: () => any) {
  await waitFor(() => expect(railData()).not.toBeNull());
  await act(async () => {
    await railData().onCastReview();
  });
  await waitFor(() => expect(screen.getByTestId("cast-review-modal")).toBeInTheDocument());
}

async function openResult() {
  await waitFor(() => expect(screen.getByTestId("gap-active")).toBeInTheDocument(), {
    timeout: 5000,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mockToast.success.mockReturnValue(101);
  mockReq.mockResolvedValue({ polished: false });
  mockApi.get.mockImplementation(async (url: string) => {
    if (url.includes("/characters")) {
      return {
        data: {
          count: 3,
          protagonist_id: null,
          gate: { ok: true, no_protagonist: false },
          confirmed: true,
          items: [
            { id: "c1", name: "林野", aliases: ["小野"], role: "主角" },
            { id: "c2", name: "陈叔", aliases: [], role: "配角" },
            { id: "c3", name: "秦伯", aliases: [], role: "配角" },
          ],
        },
      };
    }
    return { ...FULL };
  });
  mockApi.post.mockImplementation(async (url: string) => {
    if (url.includes("/cast/ai-review")) return REVIEW;
    if (url.includes("/cast/ai-draw")) return DRAW;
    if (url.endsWith("/characters")) return { data: { id: "c9", name: "新卡", aliases: [], role: "配角" } };
    throw new Error("unexpected post " + url);
  });
});

describe("11 态流转（盘点→结果→抽卡→确认两形态）", () => {
  it("② 盘点中 → ③ 结果：逐段三分类＋软提示＋quota 软话术；⑧ 写入回程回结果页", async () => {
    // 盘点响应挂起：② 盘点中可观察
    let resolveReview: (v: unknown) => void = () => {};
    mockApi.post.mockImplementation(async (url: string) => {
      if (url.includes("/cast/ai-review")) return new Promise((r) => (resolveReview = r));
      throw new Error("unexpected " + url);
    });
    const { railData } = mount();
    await openReview(railData);
    // ② 盘点中（reviewing）
    expect(screen.getByTestId("cr-reviewing")).toBeInTheDocument();
    await act(async () => resolveReview(REVIEW));
    await openResult();
    // ③ 逐段盘点行 + 缺口卡
    expect(screen.getByText("老角色能演")).toBeInTheDocument();
    expect(screen.getByText("不起名也行")).toBeInTheDocument();
    expect(screen.getAllByTestId("gap-active").length).toBe(1); // 剧情3 待处理
    expect(screen.getByTestId("gap-deferred")).toBeInTheDocument(); // 剧情4 预填延后
    // 软提示（服务端派生）＋丢行/滤名警示（warnings 不重抽）
    expect(screen.getByText(/无卡名字「秦伯」/)).toBeInTheDocument();
    expect(screen.getByTestId("cr-warnings").textContent).toContain("请自己核对");
    // 黑话清零（design-language §13）
    const text = screen.getByTestId("cast-review-modal").textContent ?? "";
    for (const bad of ["落库", "申报", "可扛", "功能位", "聚合", "人物精盘", "不落库"]) {
      expect(text).not.toContain(bad);
    }
  });

  it("suggest 预填三态：加人打「AI 建议」、defaulted 打「默认」、改选后消失", async () => {
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    // 剧情3（suggest=加人，defaulted=false）→ 「AI 建议」标在预填上
    const active = screen.getByTestId("gap-active");
    expect(active.querySelector('[data-testid="cr-sug"]')?.textContent).toBe("AI 建议");
    // 剧情4（suggest=延后，defaulted=true）→ 「默认」标
    const deferred = screen.getByTestId("gap-deferred");
    expect(deferred.querySelector('[data-testid="cr-sug"]')?.textContent).toBe("默认");
    // 改选 → 标随改选消失（touched）（多缺口时同名锚按卡内取）
    fireEvent.click(within(active).getByTestId("cr-opt-edit"));
    const edited = screen.getByTestId("gap-edited");
    expect(edited.querySelector('[data-testid="cr-sug"]')).toBeNull();
  });

  it("延后/改段零请求零落库（不发任何 AI/保存请求，选中即处理观感）", async () => {
    const { railData, outline } = mount();
    await openReview(railData);
    await openResult();
    const posts = mockApi.post.mock.calls.length;
    const active = screen.getByTestId("gap-active"); // 剧情3 卡（DOM 节点随改选不变）
    fireEvent.click(within(active).getByTestId("cr-opt-defer"));
    expect(mockApi.post.mock.calls.length).toBe(posts); // 零请求
    expect(within(active).getByTestId("cr-done-note").textContent).toContain("不做记录");
    // 改段 → 补救出口
    fireEvent.click(within(active).getByTestId("cr-opt-edit"));
    expect(within(active).getByTestId("cr-go-edit")).toBeInTheDocument();
    // 零落库：没碰保存链（openReview 的 flush 之后无新增保存）
    const saves = outline.saveChapter.mock.calls.length;
    fireEvent.click(within(active).getByTestId("cr-opt-add"));
    expect(outline.saveChapter.mock.calls.length).toBe(saves);
  });

  it("⑤ 抽卡三方向 → ⑦ 选卡进＝预填＋返回换一张；返回换一张回同批卡", async () => {
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    fireEvent.click(screen.getByTestId("cr-draw"));
    // ⑩ 抽卡中
    expect(screen.getByTestId("cr-drawing")).toBeInTheDocument();
    // ⑤ 三卡（S/A/B 角标＋小字）
    await waitFor(() => expect(screen.getByTestId("cr-pick-card-1")).toBeInTheDocument());
    const card1 = screen.getByTestId("cr-pick-card-1");
    expect(card1.textContent).toContain("S");
    expect(card1.textContent).toContain("最合适");
    expect(screen.getByTestId("cr-pick-card-2").textContent).toContain("也行");
    expect(screen.getByTestId("cr-pick-card-3").textContent).toContain("备选");
    expect(card1.textContent).toContain("他是干什么的");
    expect(card1.textContent).toContain("老角色为什么不行");
    // 选卡 → ⑦ 预填＋返回换一张
    fireEvent.click(card1);
    expect(screen.getByTestId("claim-name")).toHaveValue("魏七");
    expect(screen.getByLabelText("他是干什么的")).toHaveValue("城南消息贩子");
    expect(screen.getByTestId("cr-back-cards")).toBeInTheDocument();
    expect(screen.getByText("写入前最后改一遍 · 每个格子都能改")).toBeInTheDocument();
    // 返回换一张：回抽卡态，同批卡保留
    fireEvent.click(screen.getByTestId("cr-back-cards"));
    expect(screen.getByTestId("cr-pick-card-1")).toBeInTheDocument();
  });

  it("⑦ 手填进＝空格表单、无返回、不露任何 AI 预填（免费分割命门）", async () => {
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    fireEvent.click(screen.getByTestId("cr-fill-manual"));
    expect(screen.getByText("自己填——每个格子都可以自己写（不用 AI）")).toBeInTheDocument();
    expect(screen.getByTestId("claim-name")).toHaveValue("");
    expect(screen.getByLabelText("他是干什么的")).toHaveValue("");
    expect(screen.getByLabelText("一句人设")).toHaveValue("");
    expect(screen.queryByTestId("cr-back-cards")).toBeNull(); // 手填进无「返回换一张」
  });

  it("换一批带 exclude（轴＋称呼＋人设组合禁令）、从头再来清记录；判不出来行不静默少行", async () => {
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    fireEvent.click(screen.getByTestId("cr-draw"));
    await waitFor(() => expect(screen.getByTestId("cr-pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("cr-redraw"));
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith(
        `/novels/p1/chapters/${REF}/cast/ai-draw`,
        expect.objectContaining({
          gap: expect.objectContaining({ idx: 2 }),
          characters: ["林野", "陈叔", "秦伯"],
          // 换一批＝整批进 exclude（轴＋称呼＋一句人设组合禁令）
          exclude: [
            expect.objectContaining({ axis: "功能", name: "魏七", persona: "魏七的一句人设" }),
            expect.objectContaining({ axis: "关系", name: "灯伯", persona: "灯伯的一句人设" }),
            expect.objectContaining({ axis: "身份", name: "祝九娘", persona: "祝九娘的一句人设" }),
          ],
        }),
      ),
    );
    await waitFor(() => expect(screen.getByTestId("cr-pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("cr-fresh"));
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenLastCalledWith(
        `/novels/p1/chapters/${REF}/cast/ai-draw`,
        expect.objectContaining({ exclude: [] }),
      ),
    );
    // 返回盘点结果
    await waitFor(() => expect(screen.getByTestId("cr-pick-card-1")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("cr-back-review"));
    expect(screen.getByTestId("gap-active")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("cr-recheck")); // 重新盘点（全量重跑＋对回）
    await waitFor(() =>
      expect(
        mockApi.post.mock.calls.filter((c: string[]) => c[0].includes("ai-review")).length,
      ).toBe(2),
    );
    await openResult();
    // 对回合并：未改条目处理记录沿用（剧情4 仍延后）
    expect(screen.getByTestId("gap-deferred")).toBeInTheDocument();
  });

  it("判不出来行：verdict 出界/缺行呈现「这一段没判出来」＋重试，不静默少行", async () => {
    mockApi.post.mockImplementation(async (url: string) => {
      if (url.includes("/cast/ai-review")) {
        return {
          ...REVIEW,
          rows: [
            REVIEW.rows[0],
            { ...REVIEW.rows[1], verdict: "???" }, // 出界
            REVIEW.rows[2],
            REVIEW.rows[3],
            // idx 1 的行还在但出界；另把 idx 3 的行去掉模拟缺行
          ].filter((r) => r.idx !== 3),
        };
      }
      throw new Error("unexpected " + url);
    });
    const { railData } = mount();
    await openReview(railData);
    await waitFor(() => expect(screen.getAllByTestId("cr-row-unknown").length).toBeGreaterThan(0));
    expect(screen.getAllByTestId("cr-row-unknown").length).toBe(2); // 出界行＋缺行
    expect(screen.getAllByText("这一段没判出来").length).toBe(2);
    expect(screen.getAllByTestId("cr-row-retry").length).toBe(2);
  });

  it("零新增一行收场（常态输出不是出错）", async () => {
    mockApi.post.mockImplementation(async (url: string) => {
      if (url.includes("/cast/ai-review")) {
        return {
          rows: REVIEW.rows.slice(0, 2),
          quota: { named_count: 3, regime: "open" },
          hints: [],
        };
      }
      throw new Error("unexpected " + url);
    });
    const { railData } = mount();
    await openReview(railData);
    await waitFor(() => expect(screen.getByText(/这一章不用加人/)).toBeInTheDocument());
    expect(screen.getByText(/5–8 个就够讲/)).toBeInTheDocument();
    expect(screen.getByText(/你自己填名单永远不受限/)).toBeInTheDocument();
    expect(screen.queryByTestId("gap-active")).toBeNull();
    expect(screen.getByText("知道了")).toBeInTheDocument();
  });
});

describe("写入两出口落账（3.4）", () => {
  /** 走到确认页（手填进，格子自己填） */
  async function toPickForm(fillName = "魏七") {
    const ctx = mount();
    await openReview(ctx.railData);
    await openResult();
    fireEvent.click(screen.getByTestId("cr-fill-manual"));
    fireEvent.change(screen.getByTestId("claim-name"), { target: { value: fillName } });
    fireEvent.change(screen.getByLabelText("一句人设"), { target: { value: "改过的人设" } });
    return ctx;
  }

  it("只加名单：chars 按行去重并入＋立即保存＋ogSnapRef 双同步；预填不保存", async () => {
    const { outline } = await toPickForm();
    fireEvent.click(screen.getByTestId("cr-list-only"));
    await waitFor(() =>
      expect(outline.saveChapter).toHaveBeenCalledWith(
        REF,
        expect.objectContaining({
          outline: expect.objectContaining({
            characters: ["林野", "陈叔", "秦伯", "魏七"],
          }),
        }),
      ),
    );
    // 角色表零变化（不建卡）
    expect(mockApi.post.mock.calls.filter((c: string[]) => c[0].endsWith("/characters"))).toHaveLength(0);
    // 回结果页＋缺口转已处理＋回执
    await waitFor(() => expect(screen.getByTestId("gap-written")).toBeInTheDocument());
    expect(mockToast.success).toHaveBeenCalledWith(
      expect.stringContaining("已写入名单"),
      expect.objectContaining({ sticky: true }),
    );
    expect(mockToast.success).toHaveBeenCalledWith(
      expect.stringContaining("还有 1 个缺的人"),
      expect.anything(),
    );
  });

  it("建卡并写入：先建卡（persona/prefill 拼句）→保存→双同步→refreshCharacterNames", async () => {
    const { outline } = await toPickForm();
    fireEvent.change(screen.getByLabelText("他是干什么的"), { target: { value: "城南消息贩子" } });
    fireEvent.change(screen.getByLabelText("怎么出场"), { target: { value: "巷口拦人" } });
    fireEvent.change(screen.getByLabelText("怎么退场"), { target: { value: "本卷退场" } });
    fireEvent.change(screen.getByLabelText("退场说明"), { target: { value: "卖错主顾" } });
    fireEvent.click(screen.getByTestId("cr-write"));
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith("/novels/p1/characters", {
        name: "魏七",
        role: "配角",
        persona: "改过的人设",
        prefill: {
          plot: "城南消息贩子",
          background: "怎么出场：巷口拦人；怎么退场（本卷退场）：卖错主顾",
        },
      }),
    );
    await waitFor(() =>
      expect(outline.saveChapter).toHaveBeenCalledWith(
        REF,
        expect.objectContaining({
          outline: expect.objectContaining({ characters: ["林野", "陈叔", "秦伯", "魏七"] }),
        }),
      ),
    );
    // 建卡成功 → 名单候选刷新（含新名）
    await waitFor(() =>
      expect(mockApi.get.mock.calls.filter((c: string[]) => c[0].includes("/characters")).length).toBeGreaterThan(1),
    );
    // 回执两分支（全清）
    await waitFor(() =>
      expect(mockToast.success).toHaveBeenCalledWith(
        expect.stringContaining("角色表多一卡「魏七」"),
        expect.anything(),
      ),
    );
  });

  it("409 撞名回落只加名单＋提示「已有同名卡，名单会自动挂上」，不阻断写入", async () => {
    mockApi.post.mockImplementation(async (url: string) => {
      if (url.includes("/cast/ai-review")) return REVIEW;
      if (url.endsWith("/characters")) {
        const e = new Error("name taken") as Error & { status: number; code: string };
        e.status = 409;
        e.code = "name_taken";
        throw e;
      }
      throw new Error("unexpected " + url);
    });
    const { outline } = await toPickForm();
    fireEvent.click(screen.getByTestId("cr-write"));
    await waitFor(() =>
      expect(outline.saveChapter).toHaveBeenCalledWith(
        REF,
        expect.objectContaining({
          outline: expect.objectContaining({
            characters: expect.arrayContaining(["魏七"]),
          }),
        }),
      ),
    );
    await waitFor(() =>
      expect(mockToast.success).toHaveBeenCalledWith(
        expect.stringContaining("已有同名卡，名单会自动挂上"),
        expect.anything(),
      ),
    );
    // 名单仍写入、回结果页
    await waitFor(() => expect(screen.getByTestId("gap-written")).toBeInTheDocument());
  });

  it("建卡成功但名单保存失败：重试只走名单写入（不重复建卡）＋「卡已建好」提示", async () => {
    const { outline } = await toPickForm();
    outline.saveChapter.mockRejectedValueOnce(new Error("boom"));
    fireEvent.click(screen.getByTestId("cr-write"));
    // 建卡成功、保存失败 → 停在确认页带错误
    await waitFor(() => expect(screen.getByTestId("cr-write-error")).toBeInTheDocument());
    expect(screen.getByTestId("cr-write-error").textContent).toContain("卡已建好");
    expect(screen.getByTestId("cr-write")).toHaveTextContent("再写入一次名单");
    const creates = mockApi.post.mock.calls.filter((c: string[]) => c[0].endsWith("/characters")).length;
    // 重试
    fireEvent.click(screen.getByTestId("cr-write"));
    await waitFor(() => expect(screen.getByTestId("gap-written")).toBeInTheDocument());
    const creates2 = mockApi.post.mock.calls.filter((c: string[]) => c[0].endsWith("/characters")).length;
    expect(creates2).toBe(creates); // 不重复建卡
    await waitFor(() =>
      expect(mockToast.success).toHaveBeenCalledWith(
        expect.stringContaining("卡已建好，这就把名字写进名单"),
        expect.anything(),
      ),
    );
  });

  it("建卡失败（非撞名）：重试出口＋可改走只加名单，格内改动保留", async () => {
    mockApi.post.mockImplementation(async (url: string) => {
      if (url.includes("/cast/ai-review")) return REVIEW;
      if (url.endsWith("/characters")) throw new Error("network down");
      throw new Error("unexpected " + url);
    });
    const { outline } = await toPickForm();
    fireEvent.click(screen.getByTestId("cr-write"));
    await waitFor(() => expect(screen.getByTestId("cr-write-error")).toBeInTheDocument());
    expect(screen.getByTestId("cr-write-error").textContent).toContain("建卡失败");
    // 格内改动保留
    expect(screen.getByTestId("claim-name")).toHaveValue("魏七");
    expect(screen.getByLabelText("一句人设")).toHaveValue("改过的人设");
    // 改走只加名单
    fireEvent.click(screen.getByTestId("cr-list-only"));
    await waitFor(() => expect(screen.getByTestId("gap-written")).toBeInTheDocument());
    expect(outline.saveChapter).toHaveBeenCalled();
  });

  it("warnings 上屏（写入路径消费；保存/自动保存同口径）", async () => {
    const { outline } = await toPickForm();
    outline.saveChapter.mockResolvedValueOnce({ warnings: ["「秦伯」暂无角色卡，按原文保留"] });
    fireEvent.click(screen.getByTestId("cr-list-only"));
    await waitFor(() =>
      expect(mockToast.info).toHaveBeenCalledWith("「秦伯」暂无角色卡，按原文保留"),
    );
  });
});

describe("多缺人回程（spec R5）", () => {
  it("写入第一条回结果页＋「还有 1 个」；处理完第二条全清收场", async () => {
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    // 两条缺人都选「加人」（spec R5 场景口径）
    const cardA = screen.getByTestId("gap-active"); // 剧情3
    const cardB = screen.getByTestId("gap-deferred"); // 剧情4（预填延后）
    fireEvent.click(within(cardB).getByTestId("cr-opt-add"));
    // 第一条：手填写入
    fireEvent.click(within(cardA).getByTestId("cr-fill-manual"));
    fireEvent.change(screen.getByTestId("claim-name"), { target: { value: "魏七" } });
    fireEvent.click(screen.getByTestId("cr-list-only"));
    await waitFor(() => expect(screen.getByTestId("done-notice")).toBeInTheDocument());
    const notice1 = screen.getByTestId("done-notice").textContent ?? "";
    expect(notice1).toContain("本章还有 1 个缺的人没处理");
    expect(screen.getByTestId("done-notice")).toHaveAttribute("aria-live", "polite");
    // 缺口转已处理，剩余缺口继续（回程后 result 重挂，节点重取）
    expect(screen.getByTestId("gap-written")).toBeInTheDocument();
    const cardB2 = screen
      .getAllByTestId("gap-active")
      .find((el) => el.textContent?.includes("剧情 4"))!;
    expect(within(cardB2).getByTestId("cr-fill-manual")).toBeInTheDocument();
    // 第二条：手填写入 → 全清收场
    fireEvent.click(within(cardB2).getByTestId("cr-fill-manual"));
    fireEvent.change(screen.getByTestId("claim-name"), { target: { value: "灯伯" } });
    fireEvent.click(screen.getByTestId("cr-list-only"));
    await waitFor(() =>
      expect(screen.getByTestId("done-notice").textContent).toContain(
        "本章的缺的人都处理完了",
      ),
    );
  });
});

describe("免费态（⑥ 按钮级锁定）与降档恢复", () => {
  it("免费：抽卡按钮锁定＋升级出口＋无假卡面；自己填全免费", async () => {
    const { railData } = mount({ isPro: false });
    await openReview(railData);
    await openResult();
    expect(screen.getByTestId("cr-draw-locked")).toBeDisabled();
    expect(screen.getByTestId("cr-upgrade")).toBeInTheDocument();
    expect(screen.getAllByTestId("cr-fill-manual").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".pick-card")).toHaveLength(0); // 无假卡面
  });

  it("降档恢复不漏卡面：PRO 抽过卡后免费档重开只恢复盘点结果与三选一", async () => {
    // PRO 抽卡落会话
    const first = mount();
    await openReview(first.railData);
    await openResult();
    fireEvent.click(screen.getByTestId("cr-draw"));
    await waitFor(() => expect(screen.getByTestId("cr-pick-card-1")).toBeInTheDocument());
    // 会话里带着批次
    const raw = JSON.parse(localStorage.getItem("cs-draw:p1:vol-1-ch-2")!);
    expect(raw.gaps["gap-2"].batches).toHaveLength(1);

    // 免费档重开：恢复结果，卡面不恢复
    first.unmount();
    const second = mount({ isPro: false });
    await openReview(second.railData);
    await openResult();
    expect(screen.getByTestId("gap-active")).toBeInTheDocument(); // 盘点结果与三选一恢复
    expect(document.querySelectorAll(".pick-card")).toHaveLength(0);
    expect(screen.getByTestId("cr-draw-locked")).toBeDisabled();
  });
});

describe("失败态（error.kind 两分流）与互斥", () => {
  it("⑨ 盘点失败：重试/去模型配置/先不盘点（无「自己填」）", async () => {
    let fail = true;
    mockApi.post.mockImplementation(async (url: string) => {
      if (url.includes("/cast/ai-review")) {
        if (fail) {
          const e = new Error("no key") as Error & { status: number; reason: string };
          e.status = 503;
          e.reason = "no_key";
          throw e;
        }
        return REVIEW;
      }
      throw new Error("unexpected " + url);
    });
    const { railData } = mount();
    await openReview(railData);
    await waitFor(() => expect(screen.getByTestId("cr-error")).toBeInTheDocument());
    expect(screen.getByTestId("cr-error").textContent).toContain("先在模型配置里接一个");
    expect(screen.getByTestId("cr-error-retry")).toBeInTheDocument();
    expect(screen.getByTestId("cr-error-config")).toBeInTheDocument();
    expect(screen.getByTestId("cr-error-close")).toBeInTheDocument();
    expect(screen.queryByTestId("cr-fill-manual")).toBeNull(); // 盘点失败无「自己填」
    // 重试恢复
    fail = false;
    fireEvent.click(screen.getByTestId("cr-error-retry"));
    await openResult();
  });

  it("⑪ 抽卡失败：重试/自己填一个/先不抽了；并发双击在途互斥", async () => {
    let fail = true;
    mockApi.post.mockImplementation(async (url: string) => {
      if (url.includes("/cast/ai-review")) return REVIEW;
      if (url.includes("/cast/ai-draw")) {
        if (fail) throw new Error("boom");
        return DRAW;
      }
      throw new Error("unexpected " + url);
    });
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    const before = mockApi.post.mock.calls.length;
    const drawBtn = screen.getByTestId("cr-draw");
    fireEvent.click(drawBtn);
    fireEvent.click(drawBtn); // 双击：在途互斥
    await waitFor(() => expect(screen.getByTestId("cr-draw-error")).toBeInTheDocument());
    const draws = mockApi.post.mock.calls
      .slice(before)
      .filter((c: string[]) => c[0].includes("ai-draw"));
    expect(draws).toHaveLength(1); // 只发一次
    expect(screen.getByTestId("cr-draw-retry")).toBeInTheDocument();
    expect(screen.getByTestId("cr-draw-fill")).toBeInTheDocument();
    expect(screen.getByTestId("cr-draw-close")).toBeInTheDocument();
    fail = false;
    fireEvent.click(screen.getByTestId("cr-draw-retry"));
    await waitFor(() => expect(screen.getByTestId("cr-pick-card-1")).toBeInTheDocument());
  });

  it("双击开弹窗互斥（只跑一次盘点）", async () => {
    const { railData } = mount();
    await waitFor(() => expect(railData()).not.toBeNull());
    await act(async () => {
      void railData().onCastReview();
      void railData().onCastReview();
    });
    await openResult();
    const reviews = mockApi.post.mock.calls.filter((c: string[]) => c[0].includes("ai-review"));
    expect(reviews).toHaveLength(1);
  });
});

describe("aria 三件与文案（5.4 断言集）", () => {
  it("cr-pick radiogroup/radio/aria-checked＋done-notice aria-live；回执两分支文案", async () => {
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    const active = screen.getByTestId("gap-active");
    const group = active.querySelector(".cr-pick");
    expect(group).toHaveAttribute("role", "radiogroup");
    const opts = within(active).getAllByRole("radio");
    expect(opts.length).toBe(3);
    expect(opts[0]).toHaveAttribute("aria-checked", "true"); // 预填加人
    fireEvent.click(within(active).getByTestId("cr-opt-defer"));
    expect(within(active).getByTestId("cr-opt-defer")).toHaveAttribute("aria-checked", "true");
  });
});

describe("选已有角色（缺口复用书里已有的卡；零 AI 全免费）", () => {
  /** 角色表多一张「魏七」（不在本章名单）——候选可点；林野/陈叔/秦伯已在名单置灰 */
  function stubCardsWithExtra() {
    mockApi.get.mockImplementation(async (url: string) => {
      if (url.includes("/characters")) {
        return {
          data: {
            count: 4,
            protagonist_id: null,
            gate: { ok: true, no_protagonist: false },
            confirmed: true,
            items: [
              { id: "c1", name: "林野", aliases: ["小野"], role: "主角" },
              { id: "c2", name: "陈叔", aliases: [], role: "配角" },
              { id: "c3", name: "秦伯", aliases: [], role: "配角" },
              { id: "c4", name: "魏七", aliases: [], role: "配角" },
            ],
          },
        };
      }
      return { ...FULL };
    });
  }

  it("入口→候选 chips（只列卡名不含别名）；已在本章名单的置灰标「已在名单」", async () => {
    stubCardsWithExtra();
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    const active = screen.getByTestId("gap-active");
    fireEvent.click(within(active).getByTestId("cr-pick-existing"));
    const picker = within(active).getByTestId("cr-existing");
    // 只列卡名（别名「小野」不进候选）
    expect(within(picker).queryByTestId("cr-exist-小野")).toBeNull();
    // 已在名单（林野/陈叔/秦伯）置灰带标；魏七可点
    const lin = within(picker).getByTestId("cr-exist-林野");
    expect(lin).toBeDisabled();
    expect(lin.textContent).toContain("已在名单");
    expect(within(picker).getByTestId("cr-exist-陈叔")).toBeDisabled();
    expect(within(picker).getByTestId("cr-exist-魏七")).toBeEnabled();
    // 再点入口收起
    fireEvent.click(within(active).getByTestId("cr-pick-existing"));
    expect(within(active).queryByTestId("cr-existing")).toBeNull();
  });

  it("点已有角色→名单写入零建卡＋「已有角色」回执三分支文案；缺口收账", async () => {
    stubCardsWithExtra();
    const { railData, outline } = mount();
    await openReview(railData);
    await openResult();
    const active = screen.getByTestId("gap-active");
    fireEvent.click(within(active).getByTestId("cr-pick-existing"));
    fireEvent.click(within(active).getByTestId("cr-exist-魏七"));
    // 走 list-only 写入链：chars 追加魏七、立即保存
    await waitFor(() =>
      expect(outline.saveChapter).toHaveBeenCalledWith(
        REF,
        expect.objectContaining({
          outline: expect.objectContaining({ characters: ["林野", "陈叔", "秦伯", "魏七"] }),
        }),
      ),
    );
    // 零建卡
    expect(mockApi.post.mock.calls.filter((c: string[]) => c[0].endsWith("/characters"))).toHaveLength(0);
    // 缺口收账＋三分支文案（已有角色形）
    await waitFor(() => expect(screen.getByTestId("gap-written")).toBeInTheDocument());
    expect(screen.getByTestId("gap-written-line").textContent).toContain("选的已有角色卡");
    await waitFor(() =>
      expect(mockToast.success).toHaveBeenCalledWith(
        expect.stringContaining("用的是书里已有的角色卡"),
        expect.anything(),
      ),
    );
  });

  it("同一本书两个缺口都缺上司：第二段选刚建的同一张卡，不重复建卡", async () => {
    stubCardsWithExtra();
    const { railData } = mount();
    await openReview(railData);
    await openResult();
    // 第一条（剧情3）选已有角色魏七
    const cardA = screen.getByTestId("gap-active");
    fireEvent.click(within(cardA).getByTestId("cr-pick-existing"));
    fireEvent.click(within(cardA).getByTestId("cr-exist-魏七"));
    await waitFor(() => expect(screen.getByTestId("gap-written")).toBeInTheDocument());
    // 第二条（剧情4，预填延后→改回加人）再选同一张卡
    const cardB = screen
      .getAllByTestId("gap-deferred")
      .find((el) => el.textContent?.includes("剧情 4"))!;
    fireEvent.click(within(cardB).getByTestId("cr-opt-add"));
    fireEvent.click(within(cardB).getByTestId("cr-pick-existing"));
    // 魏七现在已在名单 → 置灰（第二段不需要再加，但流程仍可走别的卡）
    const picker = within(cardB).getByTestId("cr-existing");
    expect(within(picker).getByTestId("cr-exist-魏七")).toBeDisabled();
    expect(within(picker).getByTestId("cr-exist-魏七").textContent).toContain("已在名单");
  });

  it("写入失败：toast 报错、缺口保持待处理（不出格内错误条）", async () => {
    stubCardsWithExtra();
    const { railData, outline } = mount();
    outline.saveChapter.mockRejectedValue(new Error("boom"));
    await openReview(railData);
    await openResult();
    const active = screen.getByTestId("gap-active");
    fireEvent.click(within(active).getByTestId("cr-pick-existing"));
    fireEvent.click(within(active).getByTestId("cr-exist-魏七"));
    await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith("名单保存失败，请重试"));
    expect(screen.getByTestId("gap-active")).toBeInTheDocument();
    expect(screen.queryByTestId("gap-written")).toBeNull();
  });

  it("本会话先建过卡（半态）再选同一张：回执 MUST NOT 谎报「角色表多一卡」", async () => {
    stubCardsWithExtra();
    const { railData, outline } = mount();
    await openReview(railData);
    await openResult();
    // 剧情3：建卡并写入——建卡成功、名单保存失败（半态：卡已在书里、名单没进去）
    fireEvent.click(screen.getByTestId("cr-fill-manual"));
    fireEvent.change(screen.getByTestId("claim-name"), { target: { value: "魏七" } });
    outline.saveChapter.mockRejectedValueOnce(new Error("boom"));
    fireEvent.click(screen.getByTestId("cr-write"));
    await waitFor(() => expect(screen.getByTestId("cr-write-error")).toBeInTheDocument());
    expect(screen.getByTestId("cr-write-error").textContent).toContain("卡已建好");
    // 先不写入，重开（会话恢复，缺口仍待处理；名单里没有魏七）
    fireEvent.click(screen.getByTestId("cr-cancel"));
    await act(async () => {
      await railData().onCastReview();
    });
    await openResult();
    // 剧情3 改走「选已有角色」选同一张魏七（本次零建卡）
    const active = screen.getByTestId("gap-active");
    fireEvent.click(within(active).getByTestId("cr-pick-existing"));
    fireEvent.click(within(active).getByTestId("cr-exist-魏七"));
    await waitFor(() => expect(screen.getByTestId("gap-written")).toBeInTheDocument());
    // 回执走「已有角色卡」形，不谎报建卡
    const okToast = mockToast.success.mock.calls.map((c) => String(c[0])).join("\n");
    expect(okToast).toContain("用的是书里已有的角色卡");
    expect(okToast).not.toContain("角色表多一卡");
    expect(screen.getByTestId("gap-written-line").textContent).toContain("选的已有角色卡");
    // 全程只建过一张卡（半态那次），选已有角色零建卡
    expect(mockApi.post.mock.calls.filter((c: string[]) => c[0].endsWith("/characters"))).toHaveLength(1);
  });
});
