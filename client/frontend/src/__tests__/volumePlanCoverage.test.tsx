import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import {
  VolumeAssistPanel,
  type RailIdleData,
} from "@/components/novel/workbench/VolumeAssistPanel";
import type { VolumeRailData } from "@/components/novel/workbench/VolumeWorkspace";
import { PickCardsModal } from "@/components/novel/workbench/PickCardsModal";
import { VolumePlanModal } from "@/components/novel/workbench/VolumePlanModal";
import { useVolumePlan } from "@/hooks/useVolumePlan";

// ---------------------------------------------------------------------------
// 「卷纲规划」族覆盖率补齐（VolumePlanModal / VolumeAssistPanel / useVolumePlan /
// PickCardsModal）。每条用例断言真实用户可见行为：恢复批次不重抽、台账缺口文案、
// 未知页签回落、写作位门禁、体检降级兜底等——不凑数、不改源码。
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

const noop = () => {};

/** 受控 Promise：测「慢返回／晚到的失败」与卸载竞态 */
function deferred<T = unknown>() {
  let resolve!: (v: T) => void;
  let reject!: (e?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const THREE_PLANS = {
  ok: true,
  plans: [
    { no: 1, spine: "她按下注销键的另一半", conflict: "想追，与回不去", ending: "船不在册", focus: "代价", focus_axis: "代价", antagonist_type: "环境", antagonist_line: "母港制度——注销就没有回程" },
    { no: 2, spine: "她用校准手艺换补给", conflict: "不想欠人，与得靠人", ending: "半页坐标留在了别人手里", focus: "关系", focus_axis: "关系", antagonist_type: "势力", antagonist_line: "拾荒船队——规矩不同都得让一步" },
    { no: 3, spine: "信号比档案还老", conflict: "想确认，与怕确认", ending: "船头转向母港旧址", focus: "认知", focus_axis: "认知", antagonist_type: "难题", antagonist_line: "信号的封装层——像有人维护过" },
  ],
  note: "", volume_estimate: "约 3 卷", similar: false, warnings: [],
};

/** options 调用计数（埋点也走 post，按路径过滤） */
const optionsCalls = () =>
  apiState.post.mock.calls.filter((c) => String(c[0]).endsWith("/ai/options")).length;

beforeEach(() => {
  localStorage.clear();
  apiState.get.mockReset();
  apiState.post.mockReset();
  apiState.fetchStoryArc.mockReset();
  // 缺省桩：/events 恒成功，其余回三卡
  apiState.post.mockImplementation((path: string) =>
    path === "/events" ? Promise.resolve({ ok: true }) : Promise.resolve(THREE_PLANS),
  );
});

// ── VolumePlanModal：建卷在途（creating）────────────────────────────────────

describe("VolumePlanModal 建卷在途", () => {
  it("creating=true：创建按钮呈「创建中…」并禁用，点击不触发直建", () => {
    const onDirect = vi.fn();
    function Harness() {
      const plan = useVolumePlan("p1");
      return (
        <>
          <button data-testid="open" onClick={() => plan.open(1, false)}>open</button>
          <VolumePlanModal projectId="p1" plan={plan} isPro onUpgrade={noop}
            onDirectCreate={onDirect} onBackfill={noop} onClose={plan.closeDesk} creating />
        </>
      );
    }
    render(<Harness />);
    fireEvent.click(screen.getByTestId("open"));
    const create = screen.getByTestId("desk-create") as HTMLButtonElement;
    expect(create.textContent).toBe("创建中…");
    expect(create.disabled).toBe(true);
    fireEvent.click(create);
    expect(onDirect).not.toHaveBeenCalled();
  });
});

// ── PickCardsModal：进场（plan-anchor）三态与「从头再来」────────────────────

function PickHarness({
  volNo,
  onConfirm,
  onToDesk,
}: {
  volNo: number;
  onConfirm: (card: unknown) => void;
  onToDesk: () => void;
}) {
  const plan = useVolumePlan("p1");
  return (
    <>
      <button data-testid="open" onClick={() => plan.open(volNo, true)}>open</button>
      <PickCardsModal projectId="p1" plan={plan} onConfirm={onConfirm} onToDesk={onToDesk} onClose={plan.closePick} />
    </>
  );
}

describe("PickCardsModal 进场与重抽", () => {
  it("plan-anchor 请求失败 → 卡面进场显示「（取不到上一卷的记录）」兜底", async () => {
    apiState.get.mockImplementation((path: string) =>
      String(path).includes("/plan-anchor")
        ? Promise.reject(new Error("404"))
        : Promise.resolve({}),
    );
    render(<PickHarness volNo={2} onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    expect(screen.getByTestId("pick-enter-1").textContent).toContain("（取不到上一卷的记录）");
  });

  it("进场未返回时先出卡：显示「…」与空 title；返回后填上全文", async () => {
    const anchorGate = deferred<{ prev_ending: { text: string; source: string } }>();
    apiState.get.mockImplementation((path: string) =>
      String(path).includes("/plan-anchor") ? anchorGate.promise : Promise.resolve({}),
    );
    render(<PickHarness volNo={1} onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    // anchor 还在路上：卡面进场用「…」占位，title 为空串
    const enter = screen.getByTestId("pick-enter-1");
    expect(enter.textContent).toContain("…");
    expect(enter.querySelector("span")?.getAttribute("title")).toBe("");
    // 返回后：全文填上（title 同步）
    anchorGate.resolve({ prev_ending: { text: "上一卷他签了字", source: "第1卷" } });
    await waitFor(() =>
      expect(screen.getByTestId("pick-enter-1").textContent).toContain("上一卷他签了字"),
    );
    expect(screen.getByTestId("pick-enter-1").querySelector("span")?.getAttribute("title")).toBe(
      "上一卷他签了字",
    );
  });

  it("卸载后 anchor 才返回（成功或失败）→ alive 闸拦下，不崩不写", async () => {
    const okGate = deferred<{ prev_ending: { text: string; source: string } }>();
    const errGate = deferred();
    const gates = [okGate.promise, errGate.promise];
    let n = 0;
    apiState.get.mockImplementation((path: string) =>
      String(path).includes("/plan-anchor") ? gates[n++] : Promise.resolve({}),
    );
    // ① 成功返回落在卸载之后
    const first = render(<PickHarness volNo={1} onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    first.unmount();
    // ② 失败返回落在卸载之后
    const second = render(<PickHarness volNo={1} onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    second.unmount();
    // 两笔都在卸载后才落定：alive=false，状态一律不写、组件也不在（无异常即正确）
    await act(async () => {
      okGate.resolve({ prev_ending: { text: "晚了", source: "" } });
      errGate.reject(new Error("晚到的失败"));
    });
  });

  it("第 2 卷卡面进场标「上接」（首卷才是「起点」）", async () => {
    apiState.get.mockImplementation((path: string) =>
      String(path).includes("/plan-anchor")
        ? Promise.resolve({ prev_ending: { text: "上一卷他签了字", source: "" } })
        : Promise.resolve({}),
    );
    render(<PickHarness volNo={2} onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    const enter = screen.getByTestId("pick-enter-1");
    expect(enter.textContent).toContain("上接");
    expect(enter.textContent).toContain("上一卷他签了字");
  });

  it("换一批后「从头再来」出现：点击清空排除清单重抽，按钮随之消失", async () => {
    render(<PickHarness volNo={1} onConfirm={noop} onToDesk={noop} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("pick-grid")).toBeDefined());
    expect(screen.queryByTestId("pick-fresh")).toBeNull(); // 还没排除任何批
    fireEvent.click(screen.getByTestId("pick-redraw"));
    await waitFor(() => expect(optionsCalls()).toBe(2));
    // 这批被并入排除清单 → 「从头再来」出现
    fireEvent.click(screen.getByTestId("pick-fresh"));
    await waitFor(() => expect(optionsCalls()).toBe(3));
    // fresh＝清空排除清单重抽 → 按钮消失
    await waitFor(() => expect(screen.queryByTestId("pick-fresh")).toBeNull());
  });
});

// ── useVolumePlan：误关恢复（内存批/localStorage）与确认异常兜底 ────────────

describe("useVolumePlan 批次恢复", () => {
  it("同卷误关重开：恢复内存原批（不重抽、不重复计量），选中与一次性载荷不复活", async () => {
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1, true));
    await act(async () => {});
    expect(result.current.state.plans).toHaveLength(3);
    act(() => result.current.selectCard(2));
    expect(result.current.state.pickPick).toBe(2);
    act(() => result.current.closePick());
    expect(optionsCalls()).toBe(1);
    // 重开同卷：恢复原批
    act(() => result.current.open(1, true));
    expect(result.current.state.pickOpen).toBe(true);
    expect(result.current.state.openMode).toBe("ai");
    expect(result.current.state.plans).toHaveLength(3);
    expect(optionsCalls()).toBe(1); // 不重抽
    // 恢复①明确不复活的东西
    expect(result.current.state.pickPick).toBeNull();
    expect(result.current.state.confirmResult).toBeNull();
    expect(result.current.state.autoBackfill).toBe(false);
  });

  it("同卷在飞期间重开：批次未落（plans 空）不算恢复，走新抽", async () => {
    const gates: Array<(v: unknown) => void> = [];
    apiState.post.mockImplementation((path: string) => {
      if (path === "/events") return Promise.resolve({ ok: true });
      return new Promise((resolve) => gates.push(resolve)).then(() => THREE_PLANS);
    });
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1, true));
    act(() => result.current.open(1, true)); // 第一抽在飞（plans 仍空）→ 不算恢复
    await act(async () => {
      gates.forEach((g) => g(THREE_PLANS));
    });
    await waitFor(() => expect(result.current.state.plans).toHaveLength(3));
    expect(optionsCalls()).toBe(2); // 两抽都发了（第二次没吃掉第一抽的批）
  });

  it("localStorage 恢复：同卷刷新后原批回来（不调 options），note/exclude 跟着走", () => {
    localStorage.setItem(
      "vp-draw:p1:vol5",
      JSON.stringify({
        v: 1,
        plans: [{
          no: 1, spine: "存储里的走向", conflict: "c", ending: "e",
          focus: "", focus_axis: "代价", antagonist_type: "难题", antagonist_line: "封装层",
        }],
        note: "只剩两套",
        exclude: [{ axis: "关系", line: "旧批思路" }],
      }),
    );
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(5, true));
    expect(result.current.state.pickOpen).toBe(true);
    expect(result.current.state.plans[0].spine).toBe("存储里的走向");
    expect(result.current.state.note).toBe("只剩两套");
    expect(result.current.state.exclude).toEqual([{ axis: "关系", line: "旧批思路" }]);
    expect(optionsCalls()).toBe(0); // 恢复＝不再生成
  });

  it("localStorage 载荷缺 note/exclude 键 → 兜底空串/空数组；空批不恢复走新抽", async () => {
    localStorage.setItem(
      "vp-draw:p1:vol6",
      JSON.stringify({
        v: 1,
        plans: [{
          no: 1, spine: "缺键批", conflict: "c", ending: "e",
          focus: "", focus_axis: "代价", antagonist_type: "", antagonist_line: "",
        }],
      }),
    );
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(6, true));
    expect(result.current.state.pickOpen).toBe(true);
    expect(result.current.state.plans[0].spine).toBe("缺键批");
    expect(result.current.state.note).toBe("");
    expect(result.current.state.exclude).toEqual([]);

    // plans 为空数组 → 不算「有批可恢复」：照常发起新抽
    localStorage.setItem("vp-draw:p1:vol7", JSON.stringify({ v: 1, plans: [] }));
    act(() => result.current.open(7, true));
    await act(async () => {});
    expect(optionsCalls()).toBe(1);
    expect(result.current.state.volNo).toBe(7);
  });

  it("确认成卷请求失败：原样呈现 message；空 message／非 Error → 「确认失败，可重试」", async () => {
    const replies: Array<unknown> = [
      new Error("铺稿炸了"),
      new Error(""),
      undefined, // 非 Error 且无 message
    ];
    apiState.post.mockImplementation((path: string) => {
      if (path === "/events") return Promise.resolve({ ok: true });
      const r = replies.shift();
      return r === undefined ? Promise.reject(undefined) : Promise.reject(r);
    });
    const { result } = renderHook(() => useVolumePlan("p1"));
    // 免费路进手写页：不走抽卡，保证三笔 reject 都喂给 confirmCard 的 expand
    act(() => result.current.open(1, false));
    const card = { no: 1, spine: "走向一", conflict: "", ending: "", focus: "", focus_axis: "", antagonist_type: "", antagonist_line: "" };
    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.confirmCard(card, async () => true);
    });
    expect(ok).toBe(false);
    expect(result.current.state.pickError).toBe("铺稿炸了");

    await act(async () => {
      ok = await result.current.confirmCard(card, async () => true);
    });
    expect(ok).toBe(false);
    expect(result.current.state.pickError).toBe("确认失败，可重试");

    await act(async () => {
      ok = await result.current.confirmCard(card, async () => true);
    });
    expect(ok).toBe(false);
    expect(result.current.state.pickError).toBe("确认失败，可重试");
  });

  it("铺空缺成功响应缺 warnings 键 → deskWarnings 兜底空数组", async () => {
    apiState.post.mockImplementation((path: string) =>
      path === "/events"
        ? Promise.resolve({ ok: true })
        : Promise.resolve({
            ok: true,
            vol_no: 2,
            draft: {
              name: "血誓", summary: "s", conflict: "c", ending: "e",
              antagonist_type: "", antagonist_line: "", plants: [], reveals: [],
              chapter_target: 30, checks: [],
            },
          }),
    );
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(2, false));
    await act(async () => {
      await result.current.expandDesk();
    });
    expect(result.current.state.deskPhase).toBe("done");
    expect(result.current.state.deskWarnings).toEqual([]);
    expect(result.current.state.autoBackfill).toBe(true);
  });
});

// ── VolumeAssistPanel：分卷依据（BasisCard）四态 ────────────────────────────

const IDLE_EMPTY: RailIdleData = { volumes: [], chapters: 0 };

function renderPanel(props: Partial<Parameters<typeof VolumeAssistPanel>[0]> = {}) {
  const mocks = {
    onPlanVolume: vi.fn(),
    onSelectVolume: vi.fn(),
    onGoOutline: vi.fn(),
    onSplitAi: vi.fn(),
    onUpgrade: vi.fn(),
  };
  const view = render(
    <VolumeAssistPanel
      projectId="p1"
      data={null}
      idle={IDLE_EMPTY}
      genreLabel="悬疑"
      onPlanVolume={mocks.onPlanVolume}
      onSplitAi={mocks.onSplitAi}
      onGoOutline={mocks.onGoOutline}
      isPro
      onUpgrade={mocks.onUpgrade}
      onSelectVolume={mocks.onSelectVolume}
      autoCheckSeq={0}
      {...props}
    />,
  );
  return { ...mocks, unmount: view.unmount };
}

describe("VolumeAssistPanel 分卷依据台账", () => {
  beforeEach(() => {
    apiState.fetchStoryArc.mockResolvedValue({ fullstory: "", ending: {} });
    apiState.get.mockResolvedValue({ items: [] });
  });

  it("主线/结局/角色齐全 → 台账「已填／已登记」，结局三问按｜拼接", async () => {
    apiState.fetchStoryArc.mockResolvedValue({
      fullstory: "她从孤岛出发去母港讨回坐标",
      ending: { scene: "母港码头", hero: "她", tone: "冷" },
    });
    apiState.get.mockResolvedValue({ items: [{}, {}] });
    renderPanel();
    await waitFor(() =>
      expect(screen.getByTestId("plan-basis").textContent).toContain("她从孤岛出发去母港讨回坐标"),
    );
    const basis = screen.getByTestId("plan-basis").textContent;
    expect(basis).toContain("已填");
    expect(basis).toContain("母港码头｜她｜冷");
    expect(basis).toContain("2 人");
    expect(basis).toContain("已登记");
  });

  it("主线缺（arc 为 null）→ 两行「缺口」照标；角色卡空 → 「还没有角色卡（不拦）」", async () => {
    apiState.fetchStoryArc.mockResolvedValue(null); // ?? {} 兜底
    apiState.get.mockResolvedValue({}); // items 缺 → 非数组 → 0
    renderPanel();
    await waitFor(() =>
      expect(screen.getByTestId("plan-basis").textContent).toContain("缺口——先去设定补主线"),
    );
    const basis = screen.getByTestId("plan-basis").textContent;
    expect(basis).toContain("缺口——只作参照，不拦拆卷");
    expect(basis).toContain("还没有角色卡（不拦）");
  });

  it("题材未定（genreLabel 空）→ 初始台账「待定（不拦）」；projectId 空 → 不发请求", async () => {
    renderPanel({ projectId: "", genreLabel: "" });
    const basis = screen.getByTestId("plan-basis").textContent;
    expect(basis).toContain("待定（不拦）");
    expect(basis).toContain("待定"); // 状态列也是「待定」
    await act(async () => {}); // 给可能的请求一个 tick
    expect(apiState.fetchStoryArc).not.toHaveBeenCalled();
    expect(apiState.get).not.toHaveBeenCalled();
  });

  it("题材未定但设定读得到 → 异步落定的台账里题材行仍是「待定（不拦）」", async () => {
    renderPanel({ genreLabel: "" }); // projectId 有值 → 请求照发
    await waitFor(() =>
      expect(screen.getByTestId("plan-basis").textContent).toContain("缺口——先去设定补主线"),
    );
    const basis = screen.getByTestId("plan-basis").textContent;
    expect(basis).toContain("待定（不拦）");
    expect(basis).toContain("还没有角色卡（不拦）"); // 角色空（缺省桩 items: []）
  });

  it("读取失败（挂载中）→ 台账整列「（读取失败，不拦）」", async () => {
    apiState.fetchStoryArc.mockRejectedValue(new Error("500"));
    renderPanel();
    await waitFor(() =>
      expect(screen.getByTestId("plan-basis").textContent).toContain("（读取失败，不拦）"),
    );
  });

  it("卸载后请求才失败 → alive 闸拦下 setState，不崩不写", async () => {
    const gate = deferred();
    apiState.fetchStoryArc.mockReturnValue(gate.promise);
    const { unmount } = renderPanel();
    unmount();
    // 卸载后才失败：alive=false，不再写台账（act 正常走完即无异常）
    await act(async () => {
      gate.reject(new Error("晚到的失败"));
    });
  });
});

// ── VolumeAssistPanel：验证面板（选中卷）补齐分支 ───────────────────────────

const railData = (
  tab: string,
  detailExtra: Record<string, unknown> = {},
  frontierVol?: number | null,
): VolumeRailData =>
  ({
    volume: 2,
    title: "借命",
    tab,
    detail: { chapters: [], ...detailExtra },
    frontierVol,
  }) as unknown as VolumeRailData;

const OK_REPORT = {
  ok: true,
  vol_no: 2,
  report: [
    { name: "对主线", items: [{ status: "ok", text: "接得上" }] },
    { name: "对节奏", items: [{ status: "warn", text: "卷末未点名高潮" }] },
    { name: "对设定", items: [{ status: "warn", text: "伏笔重复" }] },
    { name: "对已写内容", items: [{ status: "none", text: "占位" }] },
  ],
};

describe("VolumeAssistPanel 验证面板补齐", () => {
  beforeEach(() => {
    apiState.fetchStoryArc.mockResolvedValue({ fullstory: "", ending: {} });
    apiState.get.mockResolvedValue({ items: [] });
    apiState.post.mockImplementation((path: string) =>
      path === "/events" ? Promise.resolve({ ok: true }) : Promise.resolve(OK_REPORT),
    );
  });

  it("点「体检这一卷」→ 发起体检并渲染报告（不靠 autoCheckSeq）", async () => {
    renderPanel({ data: railData("outline") });
    fireEvent.click(screen.getByTestId("volume-check-btn"));
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    expect(screen.getByTestId("volume-check-report").textContent).toContain("接得上");
  });

  it("未识别页签 → 页签名/引导语/组序三处回落「卷纲」默认值", async () => {
    renderPanel({ data: railData("cast"), autoCheckSeq: 1 });
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    expect(screen.getByTestId("volume-rail-tab").textContent).toBe("卷纲");
    expect(screen.getByTestId("volume-rail-lead").textContent).toContain("对不对得上全书设定");
    const groups = Array.from(
      screen.getByTestId("volume-check-report").querySelectorAll(".rp-k"),
    ).map((el) => el.textContent);
    expect(groups).toEqual(["对主线", "对节奏", "对设定", "对已写内容"]);
  });

  it("组名缺失（nullish）按空串归一；认不出的组名原样保留、按模型原序追加在尾", async () => {
    apiState.post.mockImplementation((path: string) =>
      path === "/events"
        ? Promise.resolve({ ok: true })
        : Promise.resolve({
            ok: true,
            vol_no: 2,
            report: [
              { items: [{ status: "ok", text: "无名组结论" }] }, // 组名缺失
              { name: "其他备注", items: [{ status: "warn", text: "备注" }] }, // 认不出
              { name: "对主线", items: [{ status: "ok", text: "接得上" }] },
            ],
          }),
    );
    renderPanel({ data: railData("outline"), autoCheckSeq: 1 });
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    const names = Array.from(
      screen.getByTestId("volume-check-report").querySelectorAll(".rp-k"),
    ).map((el) => el.textContent);
    // 「对主线」前置；无名组与「其他备注」一个不丢，按原序跟尾
    expect(names).toEqual(["对主线", "", "其他备注"]);
    expect(screen.getByTestId("volume-check-report").textContent).toContain("无名组结论");
  });

  it("体检失败：异常无 message → 「体检失败，请重试」；普通 message → 原样展示", async () => {
    // ① 无 message（非 Error 对象）
    apiState.post.mockImplementation((path: string) =>
      path === "/events" ? Promise.resolve({ ok: true }) : Promise.reject({}),
    );
    const first = renderPanel({ data: railData("outline"), autoCheckSeq: 1 });
    await waitFor(() =>
      expect(screen.getByTestId("volume-check-error").textContent).toBe("体检失败，请重试"),
    );
    first.unmount();
    // ② 有 message 但不含「模型」→ 原样展示，不做模型引导改写
    apiState.post.mockImplementation((path: string) =>
      path === "/events" ? Promise.resolve({ ok: true }) : Promise.reject(new Error("体检挂了")),
    );
    renderPanel({ data: railData("outline"), autoCheckSeq: 1 });
    await waitFor(() =>
      expect(screen.getByTestId("volume-check-error").textContent).toBe("体检挂了"),
    );
  });

  it("写作位门禁：本卷在写作位之前 → 拆章行禁用＋拦截段，desc/hint 都点名写作位", async () => {
    const { onSplitAi, onUpgrade } = renderPanel({
      data: railData("chapters", { summary: "主旨", core_conflict: "冲突", ending: "卷末" }, 3),
      autoCheckSeq: 1,
    });
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    expect(screen.getByTestId("volume-split-ai-blocked").textContent).toContain(
      "写作位在第3卷——先去那一卷拆章",
    );
    const split = screen.getByTestId("volume-split-ai") as HTMLButtonElement;
    expect(split.disabled).toBe(true);
    expect(split.textContent).toContain("这一卷还没轮到"); // desc
    expect(split.querySelector(".ra-hint")?.textContent).toBe("写作位在第3卷"); // hint
    // 禁用行点击是 no-op：既不拆章也不升级
    fireEvent.click(split);
    expect(onSplitAi).not.toHaveBeenCalled();
    expect(onUpgrade).not.toHaveBeenCalled();
  });

  it("写作位就是本卷 → 不拦：拆章行可点（frontier 比较照常参与判断）", async () => {
    const { onSplitAi } = renderPanel({
      data: railData("chapters", { summary: "主旨", core_conflict: "冲突", ending: "卷末" }, 2),
      autoCheckSeq: 1,
    });
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    expect(screen.queryByTestId("volume-split-ai-blocked")).toBeNull();
    const split = screen.getByTestId("volume-split-ai") as HTMLButtonElement;
    expect(split.disabled).toBe(false);
    fireEvent.click(split);
    await waitFor(() => expect(onSplitAi).toHaveBeenCalled());
  });

  it("卷纲缺「卷末」（主旨/矛盾已齐）→ 仍判未齐：拦截段＋「去补卷纲」出口可用", async () => {
    const { onGoOutline } = renderPanel({
      data: railData("chapters", { summary: "主旨", core_conflict: "冲突" }),
      autoCheckSeq: 1,
    });
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    expect(screen.getByTestId("volume-split-ai-outline-gate").textContent).toContain("先补卷纲");
    const split = screen.getByTestId("volume-split-ai") as HTMLButtonElement;
    expect(split.disabled).toBe(true);
    expect(split.querySelector(".ra-hint")?.textContent).toBe("先补卷纲");
    fireEvent.click(screen.getByTestId("volume-split-ai-go-outline"));
    expect(onGoOutline).toHaveBeenCalled();
  });

  it("体检降级 → degraded 卡呈现正文；hint 缺省时兜底「可重试」", async () => {
    // ① 带 hint
    apiState.post.mockImplementation((path: string) =>
      path === "/events"
        ? Promise.resolve({ ok: true })
        : Promise.resolve({ ok: true, vol_no: 2, degraded: true, text: "输出散文化", hint: "重试一次" }),
    );
    const first = renderPanel({ data: railData("outline"), autoCheckSeq: 1 });
    await waitFor(() => expect(screen.getByTestId("volume-check-degraded")).toBeDefined());
    expect(screen.getByTestId("volume-check-degraded").textContent).toContain("输出散文化");
    expect(screen.getByTestId("volume-check-degraded").textContent).toContain("重试一次");
    first.unmount();
    // ② 无 hint → 「可重试」
    apiState.post.mockImplementation((path: string) =>
      path === "/events"
        ? Promise.resolve({ ok: true })
        : Promise.resolve({ ok: true, vol_no: 2, degraded: true, text: "输出散文化" }),
    );
    renderPanel({ data: railData("outline"), autoCheckSeq: 1 });
    await waitFor(() => expect(screen.getByTestId("volume-check-degraded")).toBeDefined());
    expect(screen.getByTestId("volume-check-degraded").textContent).toContain("可重试");
  });

  it("卷的验证列表兜底：名字不合 vol-N → 第0卷；title 空 → 未命名；章数未设 → 「未设章数」", () => {
    renderPanel({
      idle: {
        volumes: [
          { name: "vol-7", title: "", chapter_target: null, chapters: [] },
          { name: "别的", title: "奇怪卷", chapter_target: 3, chapters: [] },
        ],
        chapters: 2,
      } as unknown as RailIdleData,
    });
    const v7 = screen.getByTestId("verify-vol-7").textContent;
    expect(v7).toContain("第7卷 · 未命名");
    expect(v7).toContain("未设章数");
    expect(screen.getByTestId("verify-vol-0").textContent).toContain("第0卷 · 奇怪卷");
  });

  it("有卷未选中：点「规划第N卷（AI）」→ onPlanVolume（最大卷号+1）", async () => {
    const { onPlanVolume } = renderPanel({
      idle: {
        volumes: [{ name: "vol-1", title: "血酬", chapter_target: 40, chapters: [] }],
        chapters: 3,
      },
    });
    fireEvent.click(screen.getByTestId("plan-next-volume"));
    await waitFor(() => expect(onPlanVolume).toHaveBeenCalledWith(2));
  });
});
