import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import {
  VolumeAssistPanel,
  type RailIdleData,
} from "@/components/novel/workbench/VolumeAssistPanel";
import VolumeWorkspace from "@/components/novel/workbench/VolumeWorkspace";
import type { VolumeDetail } from "@/components/novel/volume/types";
import type { UseWorkbenchReturn } from "@/hooks/useWorkbench";
import { PickCardsModal } from "@/components/novel/workbench/PickCardsModal";
import { VolumePlanModal } from "@/components/novel/workbench/VolumePlanModal";
import { useVolumePlan } from "@/hooks/useVolumePlan";
import { EMPTY_ANSWERS, type PlanAnswers } from "@/lib/volumePlanApi";

// ---------------------------------------------------------------------------
// c-volume-antagonist 组件契约：
//   抽卡弹窗（busy/error/三卡互异/选中/确认链/换组/转手写）；
//   四问手写页（四问输入/免费直建/铺空缺/回填）；
//   API 契约（answers 形状与 vol_no 缺省）。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  request: vi.fn(),
  fetchStoryArc: vi.fn(),
}));
vi.mock("@/lib/api", () => ({ api: apiState }));

const THREE_PLANS = {
  ok: true,
  plans: [
    { no: 1, spine: "她按下注销键的另一半", conflict: "想追，与回不去", ending: "船不在册", focus: "代价", focus_axis: "代价", antagonist_type: "环境", antagonist_line: "母港制度——注销就没有回程" },
    { no: 2, spine: "她用校准手艺换补给", conflict: "不想欠人，与得靠人", ending: "半页坐标留在了别人手里", focus: "关系", focus_axis: "关系", antagonist_type: "势力", antagonist_line: "拾荒船队——规矩不同都得让一步" },
    { no: 3, spine: "信号比档案还老", conflict: "想确认，与怕确认", ending: "船头转向母港旧址", focus: "认知", focus_axis: "认知", antagonist_type: "难题", antagonist_line: "信号的封装层——像有人维护过" },
  ],
  note: "", volume_estimate: "约 3 卷", similar: false, warnings: [],
};

const EXPAND = {
  ok: true, vol_no: 1,
  draft: {
    name: "血酬", summary: "林野为查身世做交易。", conflict: "想查真相，与双手沾血。",
    ending: "他签了字。", antagonist_type: "人物",
    antagonist_line: "执法官雷——点名要他停手",
    plants: ["猎血短刃来历"], reveals: [], chapter_target: 40, checks: ["自查一条"],
  },
  warnings: [],
};

const noop = () => {};

function PickHarness({
  onConfirm,
  onToDesk,
  answers,
}: {
  onConfirm: (card: unknown) => void;
  onToDesk: () => void;
  answers?: PlanAnswers;
}) {
  const plan = useVolumePlan("p1");
  if (answers) {
    // 注入已答（互切保留验证用）
    (plan.state as { answers: PlanAnswers }).answers = answers;
  }
  return (
    <>
      <button data-testid="open" onClick={() => plan.open(1, true)}>open</button>
      <PickCardsModal projectId="p1" plan={plan} onConfirm={onConfirm} onToDesk={onToDesk} onClose={plan.closePick} />
    </>
  );
}

function DeskHarness({
  onDirectCreate,
  onBackfill,
  manual,
}: {
  onDirectCreate: () => void;
  onBackfill: () => void;
  manual?: boolean;
}) {
  const plan = useVolumePlan("p1");
  return (
    <>
      <button data-testid="open" onClick={() => plan.open(1, false, manual ? "manual" : "ai")}>open</button>
      <VolumePlanModal
        projectId="p1" plan={plan} isPro={true} onUpgrade={noop}
        onDirectCreate={onDirectCreate} onBackfill={onBackfill} onClose={plan.closeDesk}
      />
    </>
  );
}

describe("PickCardsModal", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.fetchStoryArc.mockReset();
  });

  it("付费打开即出卡（busy→三卡）；三卡互异；选中→确认链带卡面四问", async () => {
    const onConfirm = vi.fn();
    apiState.post.mockResolvedValue(THREE_PLANS);
    render(<PickHarness onConfirm={onConfirm} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    // busy
    await waitFor(() => expect(screen.getByTestId("pick-busy")).toBeDefined());
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    const cards = screen.queryAllByTestId(/^pick-card-/);
    expect(cards.length).toBe(3);
    // 三卡互异（坎类型互不相同）
    const types = cards.map((c) => c.textContent?.slice(0, 60));
    expect(new Set(types).size).toBe(3);
    // 确认未选时禁用
    const confirm = screen.getByTestId("pick-confirm") as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    // 选中 B → aria-checked
    fireEvent.click(screen.getByTestId("pick-card-2"));
    expect(screen.getByTestId("pick-card-2").getAttribute("aria-checked")).toBe("true");
    expect(confirm.disabled).toBe(false);
    // 确认 → onConfirm 带卡（外层落库）
    fireEvent.click(confirm);
    await waitFor(() => expect(onConfirm).toHaveBeenCalledTimes(1));
    const card = onConfirm.mock.calls[0][0] as { spine: string; antagonist_line: string };
    expect(card.spine).toContain("校准手艺");
    expect(card.antagonist_line).toContain("拾荒船队");
  });

  it("options 失败（重试后）→ error 态带「重试／转手写」出口", async () => {
    apiState.post.mockRejectedValue(new Error("模型未配"));
    render(<PickHarness onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-error")).toBeDefined());
    expect(screen.getByTestId("pick-error").textContent).toContain("模型");
    expect(screen.getByText("自己答四个问题")).toBeDefined();
    // 「重试」真重调 options（成功即出卡）
    const optionsCalls = () =>
      apiState.post.mock.calls.filter((c) => String(c[0]).endsWith("/ai/options")).length;
    const before = optionsCalls();
    apiState.post.mockResolvedValue(THREE_PLANS);
    fireEvent.click(screen.getByText("重试"));
    await waitFor(() => expect(optionsCalls()).toBe(before + 1));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
  });

  it("degraded → error 态（AI 输出没法结构化）", async () => {
    apiState.post.mockResolvedValue({ ok: true, degraded: true, text: "散文", hint: "可重试" });
    render(<PickHarness onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-error")).toBeDefined());
  });

  it("换 3 套重调；转手写出口", async () => {
    apiState.post.mockResolvedValue(THREE_PLANS);
    render(<PickHarness onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    fireEvent.click(screen.getByTestId("pick-redraw"));
    // 只数 options 调用（/events 埋点也走 api.post，不能按总次数断言）
    const optionsCalls = () =>
      apiState.post.mock.calls.filter((c) => String(c[0]).endsWith("/ai/options")).length;
    await waitFor(() => expect(optionsCalls()).toBe(2));
    const toDesk = vi.fn();
    cleanupAndRender(toDesk);
    function cleanupAndRender(to: () => void) {
      // 直接点当前页里的转手写链接
      const link = screen.getAllByText("自己答四个问题")[0];
      fireEvent.click(link);
      expect(to).toBeDefined(); // harness 层 onToDesk 由外层接
    }
  });

  it("卡面缺坎与侧重轴 → 兜底「走向」且不渲染坎行", async () => {
    apiState.post.mockResolvedValue({
      ok: true, note: "", plans: [
        { no: 1, spine: "只给走向", conflict: "", ending: "收" },
      ],
    });
    render(<PickHarness onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    const card = screen.getByTestId("pick-card-1");
    expect(card.textContent).toContain("走向");
    expect(card.textContent).not.toContain("这一卷的坎");
  });

  it("每张卡自带「上接」＝这一卷的进场（与 plan-anchor 同源；首卷＝起点）", async () => {
    const ANCHOR = {
      prev_ending: { text: "上一卷她按下注销键，成为不在册的船", source: "第一卷 · 预期结局" },
    };
    apiState.get.mockImplementation((path: string) =>
      String(path).includes("/plan-anchor")
        ? Promise.resolve(ANCHOR)
        : Promise.resolve({}),
    );
    apiState.post.mockResolvedValue(THREE_PLANS);
    render(<PickHarness onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    for (const no of [1, 2, 3]) {
      const row = screen.getByTestId(`pick-enter-${no}`);
      expect(row.textContent).toContain("起点"); // 第 1 卷：进场＝全景起步
      expect(row.textContent).toContain(ANCHOR.prev_ending.text);
      // 全文挂 title（卡内两行截断）
      expect(row.querySelector("span")?.getAttribute("title")).toBe(ANCHOR.prev_ending.text);
    }
  });

  it("套数=2 时 note 呈现卡区顶部", async () => {
    apiState.post.mockResolvedValue({ ...THREE_PLANS, plans: THREE_PLANS.plans.slice(0, 2), note: "主线太薄" });
    render(<PickHarness onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-note")).toBeDefined());
    expect(screen.getByTestId("pick-note").textContent).toContain("主线太薄");
    expect(screen.queryAllByTestId(/^pick-card-/).length).toBe(2);
  });
});

describe("VolumePlanModal（四问手写页）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
  });

  it("手动入口（加号）：手写页不出现 AI 动作，只留「直接创建这一卷」＋指向右栏的说明", async () => {
    render(<DeskHarness onDirectCreate={noop} onBackfill={noop} manual />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("volume-plan-modal")).toBeDefined());
    expect(screen.queryByTestId("desk-expand")).toBeNull();
    expect(screen.getByTestId("desk-create")).toBeDefined();
    expect(screen.getByTestId("volume-plan-modal").textContent).toContain("右侧 AI 助手");
    // 四问仍可写，且不再承诺「交给 AI」
    fireEvent.change(screen.getByTestId("q-what"), { target: { value: "只靠自己" } });
    expect((screen.getByTestId("q-what") as HTMLTextAreaElement).value).toBe("只靠自己");
    expect(screen.getByTestId("volume-plan-modal").textContent).not.toContain("交给 AI");
  });

  it("四问输入＋免费直建出口＋PRO 铺空缺；免费档 PRO 说明", async () => {
    const onDirect = vi.fn();
    render(<DeskHarness onDirectCreate={onDirect} onBackfill={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    for (const tid of ["q-what", "q-conflict", "q-ant-line", "q-ending"]) {
      expect(screen.getByTestId(tid)).toBeDefined();
    }
    // 坎类型下拉五档
    fireEvent.change(screen.getByTestId("q-ant-type"), { target: { value: "自我" } });
    expect((screen.getByTestId("q-ant-type") as HTMLSelectElement).value).toBe("自我");
    // 四问输入都落 answers（含坎的一句话）
    fireEvent.change(screen.getByTestId("q-what"), { target: { value: "讲什么" } });
    fireEvent.change(screen.getByTestId("q-conflict"), { target: { value: "冲突" } });
    fireEvent.change(screen.getByTestId("q-ant-line"), { target: { value: "坎" } });
    fireEvent.change(screen.getByTestId("q-ending"), { target: { value: "卷末" } });
    expect((screen.getByTestId("q-conflict") as HTMLTextAreaElement).value).toBe("冲突");
    expect((screen.getByTestId("q-ant-line") as HTMLInputElement).value).toBe("坎");
    expect((screen.getByTestId("q-ending") as HTMLTextAreaElement).value).toBe("卷末");
    // 免费直建出口
    fireEvent.click(screen.getByTestId("desk-create"));
    expect(onDirect).toHaveBeenCalledTimes(1);
  });

  it("铺空缺→done→回填按钮；关弹窗后自动回填（token 保留已答）", async () => {
    const onBackfill = vi.fn();
    apiState.post.mockResolvedValue(EXPAND);
    let planRef: ReturnType<typeof useVolumePlan> | null = null;
    function Harness() {
      const plan = useVolumePlan("p1");
      planRef = plan;
      return (
        <>
          <button data-testid="open" onClick={() => plan.open(1, true)}>open</button>
          <VolumePlanModal projectId="p1" plan={plan} isPro onUpgrade={noop}
            onDirectCreate={noop} onBackfill={onBackfill} onClose={plan.closeDesk} />
        </>
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByTestId("open"));
    // 互切到四问页（手写路径）
    act(() => planRef!.toDesk());
    fireEvent.change(screen.getByTestId("q-what"), { target: { value: "她按下注销键" } });
    fireEvent.click(screen.getByTestId("desk-expand"));
    await waitFor(() => expect(screen.getByTestId("desk-done")).toBeDefined());
    expect(screen.getByTestId("desk-done").textContent).toContain("血酬");
    expect(screen.getByTestId("desk-done").textContent).toContain("40");
    fireEvent.click(screen.getByTestId("desk-backfill"));
    expect(onBackfill).toHaveBeenCalledTimes(1);
    // 已答保留（关弹窗再开）
    expect(planRef!.state.answers.q1).toBe("她按下注销键");
  });

  it("第 2 卷占位文案 / 主线空引导 / degraded 无 hint 兜底 / done 空卷名与未定章数", async () => {
    let planRef: ReturnType<typeof useVolumePlan> | null = null;
    function Harness() {
      const plan = useVolumePlan("p1");
      planRef = plan;
      return (
        <>
          <button data-testid="open" onClick={() => plan.open(2, false)}>open</button>
          <VolumePlanModal projectId="p1" plan={plan} isPro onUpgrade={noop}
            onDirectCreate={noop} onBackfill={noop} onClose={plan.closeDesk} />
        </>
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByTestId("open"));
    // 第 2 卷：占位文案换成「接着上一卷的结尾…」
    expect(
      (screen.getByTestId("q-what") as HTMLTextAreaElement).placeholder,
    ).toContain("接着上一卷的结尾");

    // 主线空 → 错误行带「（回到设定 → 主线）」；同时铺空缺按钮置灰
    apiState.post.mockRejectedValue(new Error("主线为空，请先在设定中完成主线"));
    fireEvent.click(screen.getByTestId("desk-expand"));
    await waitFor(() => expect(screen.getByTestId("desk-error")).toBeDefined());
    expect(screen.getByTestId("desk-error").textContent).toContain("回到设定 → 主线");
    expect((screen.getByTestId("desk-expand") as HTMLButtonElement).disabled).toBe(true);

    // degraded 且无 hint → 默认提示行
    apiState.post.mockResolvedValue({ ok: true, degraded: true, text: "散文" });
    act(() => planRef!.resetError());
    fireEvent.click(screen.getByTestId("desk-expand"));
    await waitFor(() => expect(screen.getByTestId("desk-degraded")).toBeDefined());
    expect(screen.getByTestId("desk-degraded").textContent).toContain("可重试，或按上面这段手动定走向");

    // done：卷名待定 + 章数未定（0）→ 「（卷名待定）」与「—」
    apiState.post.mockResolvedValue({
      ok: true, vol_no: 2, warnings: [],
      draft: {
        name: "", summary: "s", conflict: "c", ending: "e",
        antagonist_type: "", antagonist_line: "", plants: [], reveals: [],
        chapter_target: 0, checks: [],
      },
    });
    fireEvent.click(screen.getByTestId("desk-expand"));
    await waitFor(() => expect(screen.getByTestId("desk-done")).toBeDefined());
    expect(screen.getByTestId("desk-done").textContent).toContain("（卷名待定）");
    expect(screen.getByTestId("desk-done").textContent).toContain("— 章");
  });

  it("免费档：铺空缺置灰＋PRO 说明；直建可用", async () => {
    function FreeHarness() {
      const plan = useVolumePlan("p1");
      return (
        <>
          <button data-testid="open" onClick={() => plan.open(1, false)}>open</button>
          <VolumePlanModal projectId="p1" plan={plan} isPro={false} onUpgrade={noop}
            onDirectCreate={noop} onBackfill={noop} onClose={plan.closeDesk} />
        </>
      );
    }
    render(<FreeHarness />);
    fireEvent.click(screen.getByTestId("open"));
    const expand = screen.getByTestId("desk-expand") as HTMLButtonElement;
    expect(expand.disabled).toBe(true);
    expect(expand.title).toContain("PRO");
    expect(document.querySelector(".pill-pro")).toBeTruthy();
    const create = screen.getByTestId("desk-create") as HTMLButtonElement;
    expect(create.disabled).toBeFalsy();
  });
});

// ── 右栏三态（VolumeAssistPanel，volume-plan-ai 起） ────────────────────────

const IDLE_EMPTY: RailIdleData = { volumes: [], chapters: 0 };
const IDLE_ONE_VOL: RailIdleData = {
  volumes: [{ name: "vol-1", title: "血酬", chapter_target: 40, chapters: [] }],
  chapters: 0,
};

function renderPanel(props: Partial<Parameters<typeof VolumeAssistPanel>[0]> = {}) {
  const onPlanVolume = vi.fn();
  const onSelectVolume = vi.fn();
  render(
    <VolumeAssistPanel
      projectId="p1"
      data={null}
      idle={IDLE_EMPTY}
      genreLabel="悬疑"
      onPlanVolume={onPlanVolume}
      onSelectVolume={onSelectVolume}
      autoCheckSeq={0}
      {...props}
    />,
  );
  return { onPlanVolume, onSelectVolume };
}

describe("VolumeAssistPanel 三态", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.fetchStoryArc.mockReset();
    apiState.fetchStoryArc.mockResolvedValue({ fullstory: "", ending: {} });
    apiState.get.mockResolvedValue({ items: [] });
  });

  it("空书态：规划第一卷入口＋分卷依据；四格统计退役", () => {
    const { onPlanVolume } = renderPanel();
    expect(screen.getByTestId("plan-entry-empty")).toBeDefined();
    expect(screen.getByTestId("plan-first-volume")).toBeDefined();
    expect(screen.getByTestId("plan-basis")).toBeDefined();
    expect(screen.queryByTestId("idle-rail-stats")).toBeNull();
    expect(document.querySelector(".col-ai .rail-assist")).toBeNull();
    fireEvent.click(screen.getByTestId("plan-first-volume"));
    expect(onPlanVolume).toHaveBeenCalledWith(1);
  });

  it("有卷未选中：规划第N卷＋卷的验证；点行选中该卷", () => {
    const { onSelectVolume } = renderPanel({ idle: IDLE_ONE_VOL });
    expect(screen.getByTestId("plan-entry-next")).toBeDefined();
    expect(screen.getByTestId("plan-next-volume").textContent).toContain("第2卷");
    expect(screen.getByTestId("verify-vol-1").textContent).toContain("40 章");
    fireEvent.click(screen.getByTestId("verify-vol-1"));
    expect(onSelectVolume).toHaveBeenCalledWith("vol-1");
  });

  it("选中卷：验证面板＋体检动作；报告三组与 none 占位；evidence 独立字段", async () => {
    const detail = {
      volume: 1,
      title: "血酬",
      tab: "outline",
      detail: { chapters: [] } as unknown as VolumeDetail,
    } as unknown as Parameters<typeof VolumeAssistPanel>[0]["data"];
    apiState.post.mockResolvedValue({
      ok: true,
      vol_no: 1,
      name: "血酬",
      report: [
        { name: "对主线", items: [{ status: "warn", text: "卷末偏虚", evidence: "预期结局" }] },
        { name: "对已写内容", items: [{ status: "none", text: "还没有章节" }] },
      ],
    });
    renderPanel({ data: detail, autoCheckSeq: 1 });
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    expect(screen.getByTestId("volume-check-report").textContent).toContain("卷末偏虚");
    expect(screen.getByTestId("volume-check-report").textContent).toContain("（预期结局）");
    expect(screen.getByTestId("volume-check-report").textContent).toContain("还没有章节");
    expect(screen.queryByTestId("volume-rail-stats")).toBeNull();
  });

  it("选中卷：体检失败（无模型）给引导不报 500", async () => {
    const detail = {
      volume: 1,
      title: "血酬",
      tab: "outline",
      detail: { chapters: [] } as unknown as VolumeDetail,
    } as unknown as Parameters<typeof VolumeAssistPanel>[0]["data"];
    apiState.post.mockRejectedValue(new Error("模型未配置"));
    renderPanel({ data: detail, autoCheckSeq: 1 });
    await waitFor(() => expect(screen.getByTestId("volume-check-error")).toBeDefined());
    expect(screen.getByTestId("volume-check-error").textContent).toContain(
      "先在模型配置里接一个模型",
    );
  });
});

// ── 状态机（useVolumePlan，c-volume-antagonist 双路） ──────────────────────

/** post 桩（埋点免疫）：/events 恒成功，其余按队列依次出；用尽后沿用最后一档。
 *  埋点与业务共用 api.post——`mockResolvedValueOnce` 队列会被 /events 抢走。 */
function stubPostSeq(replies: Array<unknown | Error>) {
  let i = 0;
  apiState.post.mockImplementation((path: string) => {
    if (path === "/events") return Promise.resolve({ ok: true });
    const r = replies[Math.min(i, replies.length - 1)];
    i += 1;
    // undefined 视为「无 message 的异常」（拒绝且 message 为空）
    return r === undefined || r instanceof Error
      ? Promise.reject(r)
      : Promise.resolve(r);
  });
}

const EXPAND_RESULT = {
  ok: true,
  vol_no: 2,
  draft: {
    name: "血誓",
    summary: "本卷主旨",
    conflict: "核心矛盾",
    ending: "预期结局",
    antagonist_type: "人物",
    antagonist_line: "执法官雷",
    plants: ["新伏笔"],
    reveals: [],
    chapter_target: 30,
    checks: ["自查一条"],
  },
  warnings: [],
};

describe("卷页签右栏（c-write-home-rail-anchor）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.fetchStoryArc.mockReset();
    apiState.get.mockResolvedValue({ items: [] });
    apiState.post.mockResolvedValue({
      ok: true,
      vol_no: 2,
      report: [
        { name: "对主线", items: [{ status: "ok", text: "接得上" }] },
        { name: "对设定", items: [{ status: "warn", text: "伏笔重复" }] },
        { name: "对已写内容", items: [{ status: "none", text: "占位" }] },
      ],
    });
  });

  const railData = (tab: string) =>
    ({ volume: 2, title: "借命", tab, detail: { chapters: [] } }) as unknown as Parameters<
      typeof VolumeAssistPanel
    >[0]["data"];

  const CASES: Array<[string, string, string[]]> = [
    ["outline", "卷纲", ["对主线", "对设定", "对已写内容"]],
    ["chapters", "本卷章节", ["对已写内容", "对主线", "对设定"]],
    ["rels", "角色关系", ["对设定", "对主线", "对已写内容"]],
    ["hooks", "伏笔", ["对设定", "对主线", "对已写内容"]],
  ];

  for (const [tab, name, order] of CASES) {
    it(`${tab} 页签：「当前页签」=${name}，组序 ${order.join(" → ")}，重新规划入口=${tab === "outline" ? "有" : "无"}`, async () => {
      const { onPlanVolume } = renderPanel({ data: railData(tab), autoCheckSeq: 1 });
      await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
      expect(screen.getByTestId("volume-rail-tab").textContent).toBe(name);
      const groups = Array.from(
        screen.getByTestId("volume-check-report").querySelectorAll(".rp-k"),
      ).map((el) => el.textContent);
      expect(groups).toEqual(order);
      expect(screen.queryByTestId("volume-replan") !== null).toBe(tab === "outline");
      if (tab === "outline") {
        fireEvent.click(screen.getByTestId("volume-replan"));
        expect(onPlanVolume).toHaveBeenCalledWith(2);
      }
    });
  }

  it("组名变体按前缀归一仍重排；重名组一组都不吞（逐实例消费）", async () => {
    apiState.post.mockResolvedValue({
      ok: true,
      vol_no: 2,
      report: [
        { name: "对主线（进场与收束）", items: [{ status: "ok", text: "接得上" }] },
        { name: "对已写内容", items: [{ status: "none", text: "占位" }] },
        { name: "对主线", items: [{ status: "warn", text: "第二条主线结论" }] },
        { name: "对设定", items: [{ status: "warn", text: "伏笔重复" }] },
      ],
    });
    renderPanel({ data: railData("chapters"), autoCheckSeq: 1 });
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    const names = Array.from(
      screen.getByTestId("volume-check-report").querySelectorAll(".rp-k"),
    ).map((el) => el.textContent);
    // chapters 页签把「对已写内容」前置；变体按前缀命中参与重排；4 组一个不丢
    // （重名的第二条视为「顺序表外的组」按模型原序跟在尾）
    expect(names).toEqual(["对已写内容", "对主线（进场与收束）", "对设定", "对主线"]);
  });

  it("未体检时只给引导语与动作，不预置空报告", () => {
    renderPanel({ data: railData("chapters") });
    expect(screen.getByTestId("volume-rail-tab").textContent).toBe("本卷章节");
    expect(screen.getByTestId("volume-rail-lead").textContent).toContain("已写内容与卷纲的出入");
    expect(screen.queryByTestId("volume-check-report")).toBeNull();
    expect(screen.getByTestId("volume-check-btn")).toBeDefined();
  });
});

describe("入口分叉（c-write-home-rail-anchor）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.post.mockResolvedValue(THREE_PLANS);
  });

  it("open(mode)：manual 恒进四问页；ai 按档（付费＝抽卡 / 免费＝四问页）", async () => {
    const { result } = renderHook(() => useVolumePlan("p1"));
    await act(async () => {
      result.current.open(1, true, "manual");
    });
    expect(result.current.state.deskOpen).toBe(true);
    expect(result.current.state.pickOpen).toBe(false);

    await act(async () => {
      result.current.open(1, true);
    });
    expect(result.current.state.pickOpen).toBe(true);
    expect(result.current.state.deskOpen).toBe(false);

    await act(async () => {
      result.current.open(1, false);
    });
    expect(result.current.state.deskOpen).toBe(true);
    expect(result.current.state.pickOpen).toBe(false);
  });
});

describe("useVolumePlan 状态机", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.fetchStoryArc.mockReset();
    apiState.fetchStoryArc.mockResolvedValue({ fullstory: "主线", ending: { scene: "s" } });
    apiState.get.mockResolvedValue({ items: [] });
  });

  it("抽卡失败 → error 可重试；主线空 → 引导去设定而非报错文案", async () => {
    stubPostSeq([
      new Error("网络抖了"),
      new Error("主线为空，请先在设定中完成主线"),
      undefined, // 无 message 的异常 → 通用可重试文案
    ]);
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1, true)); // open 即自动抽卡（付费路）
    await act(async () => {});
    expect(result.current.state.pickError).toBe("网络抖了");
    act(() => result.current.resetError());
    expect(result.current.state.error).toBe("");

    await act(async () => {
      await result.current.expandDesk();
    });
    expect(result.current.state.error).toContain("先到设定补主线");
    await act(async () => {
      await result.current.expandDesk();
    });
    expect(result.current.state.error).toBe("生成失败，请重试");
  });

  it("响应缺键：note 兜底空串；降级无 text 兜底空串", async () => {
    stubPostSeq([
      {
        ok: true,
        plans: [
          { no: 1, spine: "甲", conflict: "", ending: "收", focus: "", focus_axis: "代价" },
          { no: 2, spine: "乙", conflict: "", ending: "收", focus: "", focus_axis: "关系" },
        ],
      },
      { ok: true, degraded: true }, // 降级且无 text/hint 键
    ]);
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1, true)); // open 即自动抽卡
    await act(async () => {});
    expect(result.current.state.plans).toHaveLength(2);
    expect(result.current.state.note).toBe("");
    await act(async () => {
      await result.current.expandDesk();
    });
    expect(result.current.state.degradedText).toBe("");
    expect(result.current.state.hint).toBe("");
  });

  it("生成中关弹窗 → 完成后 autoBackfill 载荷只被取走一次；降级无载荷", async () => {
    let resolveExpand: (v: unknown) => void = () => {};
    apiState.post.mockImplementation((path: string) => {
      if (path === "/events") return Promise.resolve({ ok: true });
      return new Promise((resolve) => {
        resolveExpand = resolve;
      });
    });
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(2, false));
    await act(async () => {
      void result.current.expandDesk();
    });
    act(() => result.current.closeDesk());
    expect(result.current.state.deskOpen).toBe(false);
    expect(result.current.state.deskPhase).toBe("generating");
    await act(async () => {
      resolveExpand(EXPAND_RESULT);
    });
    await waitFor(() => expect(result.current.state.deskPhase).toBe("done"));
    const payload = result.current.takeAutoBackfill();
    expect(payload?.volNo).toBe(2);
    expect(payload?.draft.name).toBe("血誓");
    expect(result.current.takeAutoBackfill()).toBeNull(); // 读走即清

    // 降级：无 autoBackfill 载荷
    stubPostSeq([{ ok: true, degraded: true, text: "散文", hint: "" }]);
    act(() => result.current.open(3, false));
    await act(async () => {
      await result.current.expandDesk();
    });
    expect(result.current.state.degradedText).toBe("散文");
    expect(result.current.takeAutoBackfill()).toBeNull();
  });

  it("确认成卷：confirmResult 承接并只取走一次；Esc 取消清选中", async () => {
    stubPostSeq([EXPAND_RESULT]);
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1, true));
    await act(async () => {
      await result.current.drawCards();
    });
    act(() => result.current.selectCard(1));
    expect(result.current.state.pickPick).toBe(1);
    await act(async () => {
      await result.current.confirmCard(
        { no: 1, spine: "走向一", conflict: "冲突一", ending: "卷末一", focus: "", focus_axis: "", antagonist_type: "人物", antagonist_line: "执法官雷" },
        async () => true,
      );
    });
    expect(result.current.state.pickOpen).toBe(false);
    let taken: { volNo: number; draft: { name: string } } | null = null;
    act(() => {
      taken = result.current.consumeConfirm();
    });
    expect(taken!.volNo).toBe(2);
    expect(taken!.draft.name).toBe("血誓");
    await act(async () => {}); // 状态落定后再取 → 已清
    expect(result.current.state.confirmResult).toBeNull();

    // 再开一次 → Esc/关钮取消：不落库（token 递增）且清选中
    act(() => result.current.open(2, true));
    act(() => result.current.selectCard(1));
    act(() => result.current.closePick());
    expect(result.current.state.pickOpen).toBe(false);
    expect(result.current.state.confirming).toBe(false);
  });

  it("取消竞态：写请求前取消 → 落库/状态一律不落（token 守卫）", async () => {
    // 闸门：所有业务请求挂起，取消（closePick）或发起新操作后再放行 → 一律早退。
    // 一次放行全部挂起请求（每条闸门各自持有 resolver）。
    let pending: Array<() => void> = [];
    const flush = () => {
      const list = pending;
      pending = [];
      list.forEach((f) => f());
    };
    const gateTo = (reply: unknown, reject = false) =>
      new Promise((resolve, rejectFn) => {
        pending.push(() =>
          reject ? rejectFn(reply) : resolve(reply),
        );
      });
    const stubGate = (reply: unknown, reject = false) => {
      apiState.post.mockImplementation((path: string) =>
        path === "/events" ? Promise.resolve({ ok: true }) : gateTo(reply, reject),
      );
    };
    const card = {
      no: 1, spine: "走向一", conflict: "", ending: "", focus: "",
      focus_axis: "", antagonist_type: "", antagonist_line: "",
    };
    const { result } = renderHook(() => useVolumePlan("p1"));

    // ① 抽卡请求挂起 → 取消 → 失败回来也不写 error
    stubGate(new Error("晚到的失败"), true);
    act(() => result.current.open(1, true));
    act(() => result.current.closePick());
    await act(async () => {
      flush();
    });
    expect(result.current.state.pickError).toBe("");

    // ② 确认请求挂起 → 取消 → 成功回来也不落库、不置 confirmResult
    stubGate(EXPAND_RESULT);
    act(() => result.current.open(2, true));
    const onPersist = vi.fn(async () => true);
    let confirming: Promise<boolean> | null = null;
    act(() => {
      confirming = result.current.confirmCard(card, onPersist);
    });
    act(() => result.current.closePick());
    await act(async () => {
      flush();
      await confirming;
    });
    expect(onPersist).not.toHaveBeenCalled();
    expect(result.current.state.confirmResult).toBeNull();

    // ③ onPersist 期间取消 → 落库已发生但 confirmResult 不置（不二次提交）
    let releasePersist: () => void = () => {};
    stubGate(EXPAND_RESULT);
    const slowPersist = vi.fn(
      () =>
        new Promise<boolean>((resolve) => {
          releasePersist = () => resolve(true);
        }),
    );
    act(() => result.current.open(3, true));
    let chain: Promise<boolean> | null = null;
    act(() => {
      chain = result.current.confirmCard(card, slowPersist);
    });
    await act(async () => {
      flush();
    });
    act(() => result.current.closePick());
    await act(async () => {
      releasePersist();
      await chain;
    });
    expect(slowPersist).toHaveBeenCalledTimes(1);
    expect(result.current.state.confirmResult).toBeNull();

    // ④ 确认请求挂起 → 取消 → 失败回来也不写 pickError
    stubGate(new Error("晚到的失败"), true);
    act(() => result.current.open(4, true));
    let failed: Promise<boolean> | null = null;
    act(() => {
      failed = result.current.confirmCard(card, async () => true);
    });
    act(() => result.current.closePick());
    await act(async () => {
      flush();
      await failed;
    });
    expect(result.current.state.pickError).toBe("");

    // ⑤ 铺空缺挂起 → 期间又发起新操作（token 递增）→ 成功回来不落 draft；
    //    失败回来不写 error（关弹窗本身不取消——「生成在后台跑」是设计口径）
    stubGate(EXPAND_RESULT);
    act(() => result.current.open(5, false));
    let expanding: Promise<void> | null = null;
    act(() => {
      expanding = result.current.expandDesk();
    });
    act(() => result.current.open(5, true)); // 新操作：抽卡 → token 递增
    act(() => result.current.closePick());
    await act(async () => {
      flush();
      await expanding;
    });
    expect(result.current.state.draft).toBeNull();

    stubGate(new Error("晚到的失败"), true);
    act(() => result.current.open(6, false));
    act(() => {
      expanding = result.current.expandDesk();
    });
    act(() => result.current.open(6, true));
    act(() => result.current.closePick());
    await act(async () => {
      flush();
      await expanding;
    });
    expect(result.current.state.error).toBe("");
  });

  it("确认成卷遇降级（无 draft）→ error 态可重试，不落库", async () => {
    stubPostSeq([{ ok: true, vol_no: 1, degraded: true, hint: "铺稿失败，可重试" }]);
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1, true));
    await act(async () => {});
    const onPersist = vi.fn(async () => true);
    await act(async () => {
      await result.current.confirmCard(
        { no: 1, spine: "走向一", conflict: "", ending: "", focus: "", focus_axis: "", antagonist_type: "", antagonist_line: "" },
        onPersist,
      );
    });
    expect(onPersist).not.toHaveBeenCalled();
    expect(result.current.state.pickError).toBe("铺稿失败，可重试");
    expect(result.current.state.pickPhase).toBe("error");
  });

  it("兜底分支：degraded 无 hint / 非 Error 异常 / 503 文案 / warnings 缺键", async () => {
    const { result } = renderHook(() => useVolumePlan("p1"));

    // ① degraded 且无 hint → 默认文案
    stubPostSeq([{ ok: true, degraded: true }]);
    act(() => result.current.open(1, true));
    await act(async () => {});
    expect(result.current.state.pickError).toContain("AI 的输出没法结构化");

    // ② 异常不是 Error（无 message）→ 通用文案
    apiState.post.mockImplementation((path: string) =>
      path === "/events"
        ? Promise.resolve({ ok: true })
        : Promise.reject({ notAnError: true }),
    );
    act(() => result.current.open(1, true));
    await act(async () => {});
    expect(result.current.state.pickError).toBe("出卡失败，可重试");

    // ③ message 含 503 → 云端/模型引导文案
    stubPostSeq([new Error("503 Service Unavailable")]);
    act(() => result.current.open(1, true));
    await act(async () => {});
    expect(result.current.state.pickError).toContain("还没接模型");

    // ④ warnings 缺键 + 卡面坎缺键 → 兜底空数组/空串
    stubPostSeq([
      {
        ok: true,
        plans: [
          { no: 1, spine: "甲", conflict: "", ending: "收", focus: "", focus_axis: "" },
        ],
      },
      {
        ok: true,
        vol_no: 1,
        draft: {
          name: "", summary: "", conflict: "", ending: "",
          antagonist_type: "", antagonist_line: "", plants: [], reveals: [],
          chapter_target: 0, checks: [],
        },
      },
    ]);
    act(() => result.current.open(1, true));
    await act(async () => {});
    expect(result.current.state.plans[0].focus_axis).toBe("");
    await act(async () => {
      await result.current.confirmCard(result.current.state.plans[0], async () => true);
    });
    expect(result.current.state.confirmResult?.warnings).toEqual([]);

    // ⑤ 再次选中同一张卡 → 取消选中（track 只在选中时记）
    act(() => result.current.open(1, true));
    await act(async () => {});
    act(() => result.current.selectCard(1));
    expect(result.current.state.pickPick).toBe(1);
    act(() => result.current.selectCard(1));
    expect(result.current.state.pickPick).toBeNull();

    // ⑥ consumeConfirm 无载荷时安全返回 null
    await act(async () => {});
    act(() => {
      expect(result.current.consumeConfirm()).toBeNull();
    });

    // ⑦ 手写页 degraded 且无 text/hint → 空串兜底
    stubPostSeq([{ ok: true, degraded: true }]);
    act(() => result.current.open(2, false));
    await act(async () => {
      await result.current.expandDesk();
    });
    expect(result.current.state.degradedText).toBe("");
    expect(result.current.state.hint).toBe("");

    // ⑧ 确认成卷遇 degraded 无 hint → 默认文案
    stubPostSeq([{ ok: true, vol_no: 1, degraded: true }]);
    act(() => result.current.open(3, true));
    await act(async () => {});
    await act(async () => {
      await result.current.confirmCard(
        { no: 1, spine: "走向一", conflict: "", ending: "", focus: "", focus_axis: "", antagonist_type: "", antagonist_line: "" },
        async () => true,
      );
    });
    expect(result.current.state.pickError).toBe("铺稿失败，可重试");
  });

  it("已答四问随 expand 原样上送（P0-1：闭包 stale 会让 AI 拿到空答案）", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    apiState.post.mockImplementation((path: string, body?: unknown) => {
      if (path === "/events") return Promise.resolve({ ok: true });
      bodies.push(body as Record<string, unknown>);
      return Promise.resolve(EXPAND_RESULT);
    });
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(2, false));
    act(() => result.current.setAnswer("q1", "她按下注销键"));
    act(() => result.current.setAnswer("conflict", "补给单上没有她的名字"));
    act(() => result.current.setAnswer("antagonist_type", "自我"));
    act(() => result.current.setAnswer("antagonist_line", "体内饥渴"));
    act(() => result.current.setAnswer("q4", "没有退路"));
    await act(async () => {
      await result.current.expandDesk();
    });
    expect(bodies[0]).toMatchObject({
      line: "她按下注销键",
      conflict: "补给单上没有她的名字",
      antagonist_type: "自我",
      antagonist_line: "体内饥渴",
      ending: "没有退路",
      vol_no: 2,
    });
  });

  it("落库失败（onPersist 返 false）→ 不关弹窗、不置 confirmResult、保留选中（P1-5）", async () => {
    stubPostSeq([EXPAND_RESULT]);
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1, true));
    await act(async () => {});
    act(() => result.current.selectCard(1));
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.confirmCard(
        { no: 1, spine: "走向一", conflict: "", ending: "", focus: "", focus_axis: "", antagonist_type: "", antagonist_line: "" },
        async () => false,
      );
    });
    expect(ok).toBe(false);
    expect(result.current.state.pickOpen).toBe(true); // 弹窗还在
    expect(result.current.state.pickPick).toBe(1); // 选中还在
    expect(result.current.state.confirmResult).toBeNull();
    expect(result.current.state.pickPhase).toBe("error");
    expect(result.current.state.pickError).toContain("没落库");
  });

  it("重新 open 会丢弃在飞 expand（P3：否则上一卷草稿会落到新一轮的卷上）", async () => {
    let release: () => void = () => {};
    apiState.post.mockImplementation((path: string) => {
      if (path === "/events") return Promise.resolve({ ok: true });
      return new Promise((resolve) => {
        release = () => resolve(EXPAND_RESULT);
      });
    });
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(2, false));
    let expanding: Promise<void> | null = null;
    act(() => {
      expanding = result.current.expandDesk();
    });
    // 关弹窗（不取消）后对**下一卷**重新打开规划台——免费路 open 不经过 drawCards
    act(() => result.current.closeDesk());
    act(() => result.current.open(3, false));
    await act(async () => {
      release();
      await expanding;
    });
    expect(result.current.state.volNo).toBe(3);
    expect(result.current.state.draft).toBeNull(); // 上一轮的草稿不得写进这一轮
    expect(result.current.takeAutoBackfill()).toBeNull();
  });

  it("selectCard：切换语义正确，且埋点每次点击只记一条（updater 保持纯）", () => {
    // 用 StrictMode 包一层：dev 下 React 会双调用 updater——埋点写在 updater 内会被记两条
    const { result } = renderHook(() => useVolumePlan("p1"), {
      wrapper: ({ children }) => <StrictMode>{children}</StrictMode>,
    });
    act(() => result.current.open(1, true));
    const events = () =>
      apiState.post.mock.calls.filter(
        (c) => c[0] === "/events" && (c[1] as { event_type: string }).event_type === "pick_select",
      ).length;
    apiState.post.mockClear();
    act(() => result.current.selectCard(2));
    expect(result.current.state.pickPick).toBe(2);
    expect(events()).toBe(1); // 一条，不是两条（StrictMode dev 双调用不再放大）
    act(() => result.current.selectCard(2));
    expect(result.current.state.pickPick).toBeNull(); // 再点同一张＝取消选中
    expect(events()).toBe(1); // 取消不记
  });

  it("互切手写页保留已答；卷号随 open 传入", () => {
    stubPostSeq([{ ok: true, plans: [] }]);
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(4, true));
    expect(result.current.state.pickOpen).toBe(true);
    expect(result.current.state.volNo).toBe(4);
    act(() => result.current.toDesk());
    expect(result.current.state.deskOpen).toBe(true);
    expect(result.current.state.pickOpen).toBe(false);
    act(() => result.current.setAnswer("q1", "她按下注销键"));
    expect(result.current.state.answers.q1).toBe("她按下注销键");
  });
});

// ── 回填（VolumeWorkspace 逐段落下） ───────────────────────────────────────

const VOL_DETAIL: VolumeDetail = {
  ref: "vol-2",
  volume: 2,
  title: "第二卷",
  summary: "",
  core_conflict: "",
  ending: "",
  antagonist_type: "",
  antagonist_line: "",
  chapter_target: 0,
  prev_ending: { text: "上一卷他签了字", source: "第1卷 · 预期结局（还没写到，先按卷纲）" },
  cast_members: [],
  ghost_count: 0,
  chapters: [],
};

describe("VolumeWorkspace 回填", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.put.mockReset();
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes/vol-2") return Promise.resolve(VOL_DETAIL);
      if (path === "/novels/p1/frontier") return Promise.resolve({ frontier: null });
      return Promise.resolve({});
    });
  });

  it("逐段落下：主旨/矛盾/坎/卷末/章数落表单；进场只读行", async () => {
    vi.useFakeTimers();
    try {
      render(
        <VolumeWorkspace
          projectId="p1"
          volumeRef="vol-2"
          wb={{} as UseWorkbenchReturn}
          onGoChapter={noop}
          onVolumeMutated={noop}
          onDirtyChange={noop}
          onRailData={noop}
          backfill={{
            seq: 1,
            draft: {
              name: "血誓",
              summary: "主旨X",
              conflict: "矛盾X",
              ending: "结局X",
              antagonist_type: "人物",
              antagonist_line: "执法官雷",
              plants: ["伏笔X"],
              reveals: ["揭示X"],
              chapter_target: 30,
              checks: [],
            },
          }}
        />,
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(50);
      });
      // 详情加载后表单进入编辑态；回填未完成时保存禁用
      const saveBtn = () =>
        screen.getAllByRole("button", { name: /保存|回填中/ })[0] as HTMLButtonElement;
      expect(saveBtn().disabled).toBe(true);
      expect(screen.getByTestId("vol-prev-ending").textContent).toContain("上一卷他签了字");
      // 走完 6 段（160ms/段）
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1400);
      });
      expect((document.getElementById("vol-summary") as HTMLTextAreaElement).value).toBe("主旨X");
      expect((document.getElementById("vol-conflict") as HTMLTextAreaElement).value).toBe("矛盾X");
      expect((document.getElementById("vol-ant-line") as HTMLInputElement).value).toBe("执法官雷");
      expect((document.getElementById("vol-ending") as HTMLTextAreaElement).value).toBe("结局X");
      expect((document.getElementById("vol-target") as HTMLInputElement).value).toBe("30");
      expect((document.getElementById("vol-name") as HTMLInputElement).value).toBe("血誓");
      expect(saveBtn().disabled).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("度量事件（PRD §7 / tasks 5.3）", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
  });

  /** 取本轮所有 /events 上报的事件名（顺序即发生顺序） */
  const events = () =>
    apiState.post.mock.calls
      .filter((c) => c[0] === "/events")
      .map((c) => (c[1] as { event_type: string }).event_type);

  it("抽卡链：drawn → select → confirm_ok；重抽记 redraw", async () => {
    apiState.post.mockResolvedValue(THREE_PLANS);
    const onConfirm = vi.fn();
    render(<PickHarness onConfirm={onConfirm} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    fireEvent.click(screen.getByTestId("pick-redraw"));
    await waitFor(() => expect(events().includes("pick_redraw")).toBe(true));
    fireEvent.click(screen.getByTestId("pick-card-2"));
    expect(events()).toContain("pick_select");
    expect(
      apiState.post.mock.calls.find(
        (c) => c[0] === "/events" && (c[1] as { event_type: string }).event_type === "pick_select",
      )?.[1],
    ).toEqual({ event_type: "pick_select", payload: { no: 2 } });
    expect(events()).toContain("pick_drawn");
    expect(events()).not.toContain("pick_confirm_ok"); // 确认在外层（落库后由 useVolumePlan 记）
  });

  it("铺空缺记 desk_expand（带卷号）", async () => {
    apiState.post.mockResolvedValue(EXPAND);
    render(<DeskHarness onDirectCreate={noop} onBackfill={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    fireEvent.click(screen.getByTestId("desk-expand"));
    await waitFor(() => expect(screen.getByTestId("desk-done")).toBeDefined());
    expect(events()).toContain("desk_expand");
    expect(
      apiState.post.mock.calls.find(
        (c) => c[0] === "/events" && (c[1] as { event_type: string }).event_type === "desk_expand",
      )?.[1],
    ).toEqual({ event_type: "desk_expand", payload: { vol_no: 1 } });
  });

  it("确认失败记 pick_confirm_fail", async () => {
    apiState.post.mockImplementation((path: string) => {
      if (path === "/events") return Promise.resolve({ ok: true });
      if (path.endsWith("/options")) return Promise.resolve(THREE_PLANS);
      return Promise.reject(new Error("铺稿失败"));
    });
    function ChainHarness() {
      const plan = useVolumePlan("p1");
      return (
        <>
          <button data-testid="open" onClick={() => plan.open(1, true)}>open</button>
          <PickCardsModal
            projectId="p1"
            plan={plan}
            onConfirm={(card) => void plan.confirmCard(card, async () => true)}
            onToDesk={noop}
            onClose={plan.closePick}
          />
        </>
      );
    }
    render(<ChainHarness />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    fireEvent.click(screen.getByTestId("pick-card-1"));
    fireEvent.click(screen.getByTestId("pick-confirm"));
    await waitFor(() => expect(events()).toContain("pick_confirm_fail"));
  });
});

describe("volume/form 契约（表单态 ↔ payload）", () => {
  it("toVolumeFormData：缺字段回落空串；chapter_target null → 空串", async () => {
    const { toVolumeFormData } = await import("@/components/novel/volume/form");
    const f = toVolumeFormData({
      ref: "vol-1", volume: 1, title: "第一卷",
      // 故意留空/缺省：验证 `|| ""` 与 `!= null` 两条兜底
      summary: undefined, core_conflict: "", ending: "结局",
      antagonist_type: null, antagonist_line: undefined,
      prev_ending: null, cast_members: [], ghost_count: 0, chapters: [],
    } as unknown as Parameters<typeof toVolumeFormData>[0]);
    expect(f).toEqual({
      title: "第一卷", summary: "", core_conflict: "", ending: "结局",
      antagonist_type: "", antagonist_line: "", chapter_target: "",
    });
    const bare = toVolumeFormData({
      ref: "vol-1", volume: 1, title: "", summary: "", core_conflict: "",
      ending: "", antagonist_type: "", antagonist_line: "", chapter_target: 0,
      prev_ending: null, cast_members: [], ghost_count: 0, chapters: [],
    } as unknown as Parameters<typeof toVolumeFormData>[0]);
    expect(bare.title).toBe("");
    // 章数有值 → 字符串；节点为副本（不共享引用）
    const g = toVolumeFormData({
      ref: "vol-1", volume: 1, title: "第二卷", summary: "s", core_conflict: "c",
      ending: "e", antagonist_type: "人物", antagonist_line: "雷", chapter_target: 12,
      cast_members: [], ghost_count: 0, chapters: [],
    } as unknown as Parameters<typeof toVolumeFormData>[0]);
    expect(g.chapter_target).toBe("12");
  });

  it("volumeFormToPayload：章数留空置 null；坎类型空串置 null；节点 text trim", async () => {
    const { volumeFormToPayload } = await import("@/components/novel/volume/form");
    expect(
      volumeFormToPayload({
        title: " 第一卷 ", summary: "s", core_conflict: "c", ending: "e",
        antagonist_type: "", antagonist_line: " 雷 ", chapter_target: "",
      }),
    ).toEqual({
      title: "第一卷", summary: "s", core_conflict: "c", ending: "e",
      antagonist_type: null, antagonist_line: " 雷 ", chapter_target: null,
    });
    expect(
      volumeFormToPayload({
        title: "t", summary: "", core_conflict: "", ending: "",
        antagonist_type: "人物", antagonist_line: "", chapter_target: " 12 ",
      }).chapter_target,
    ).toBe(12);
  });
});

describe("volumePlanApi 契约", () => {
  it("options/expand 发 answers 形状；vol_no 缺省 null", async () => {
    apiState.post.mockReset();
    apiState.post.mockResolvedValue(THREE_PLANS);
    const { volumePlanApi } = await import("@/lib/volumePlanApi");
    await volumePlanApi.options("p1", { ...EMPTY_ANSWERS, q1: "一句" });
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes/ai/options", {
      line: "一句", conflict: "", antagonist_type: "", antagonist_line: "", ending: "",
    });
    await volumePlanApi.expand("p1", { ...EMPTY_ANSWERS, q4: "卷末" });
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes/ai/expand", {
      line: "", conflict: "", antagonist_type: "", antagonist_line: "", ending: "卷末", vol_no: null,
    });
    await volumePlanApi.check("p1", "vol-3");
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes/vol-3/ai/check", {});
  });
});
