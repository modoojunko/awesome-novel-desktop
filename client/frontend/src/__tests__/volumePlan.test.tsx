import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  VolumeAssistPanel,
  type RailIdleData,
} from "@/components/novel/workbench/VolumeAssistPanel";
import { VolumePlanModal } from "@/components/novel/workbench/VolumePlanModal";
import { useVolumePlan } from "@/hooks/useVolumePlan";
import { GENRE_PENDING_LABEL } from "@/lib/genreVocab";
import type { VolumeRailData } from "@/components/novel/workbench/VolumeWorkspace";
import type { VolumeDetail } from "@/components/novel/volume/types";
import VolumeWorkspace from "@/components/novel/workbench/VolumeWorkspace";
import type { UseWorkbenchReturn } from "@/hooks/useWorkbench";

// ---------------------------------------------------------------------------
// volume-plan-ai 组件契约：
//   右栏三态（空书规划入口 / 接着往下规划＋卷的验证 / 选中卷验证面板）；
//   规划台（输入空→展开禁用；3 套卡；选卡→填回并展开；降级；免费禁用）；
//   回填（逐段落下、展开依据只读行、进场来源说明）。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  fetchStoryArc: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState }));

const IDLE_EMPTY: RailIdleData = { volumes: [], chapters: 0 };
const IDLE_ONE_VOL: RailIdleData = {
  volumes: [
    {
      name: "vol-1",
      title: "血酬",
      chapter_target: 40,
      chapters: [],
    },
  ],
  chapters: 0,
};

const noop = () => {};

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
      detail: { chapters: [] } as unknown as VolumeRailData["detail"],
    } as unknown as VolumeRailData;
    apiState.post.mockResolvedValue({
      ok: true,
      vol_no: 1,
      name: "血酬",
      report: [
        {
          name: "对主线",
          items: [{ status: "warn", text: "卷末偏虚", evidence: "预期结局" }],
        },
        {
          name: "对已写内容",
          items: [{ status: "none", text: "还没有章节" }],
        },
      ],
    });
    renderPanel({ data: detail, autoCheckSeq: 1 });
    await waitFor(() => expect(screen.getByTestId("volume-check-report")).toBeDefined());
    expect(screen.getByTestId("volume-check-report").textContent).toContain("卷末偏虚");
    expect(screen.getByTestId("volume-check-report").textContent).toContain("（预期结局）");
    expect(screen.getByTestId("volume-check-report").textContent).toContain("还没有章节");
    // 卷选中态不得出现四页签统计卡
    expect(screen.queryByTestId("volume-rail-stats")).toBeNull();
  });

  it("选中卷：体检失败（无模型）给引导不报 500", async () => {
    const detail = {
      volume: 1,
      title: "血酬",
      tab: "outline",
      detail: { chapters: [] } as unknown as VolumeRailData["detail"],
    } as unknown as VolumeRailData;
    apiState.post.mockRejectedValue(new Error("模型未配置"));
    renderPanel({ data: detail, autoCheckSeq: 1 });
    await waitFor(() =>
      expect(screen.getByTestId("volume-check-error")).toBeDefined(),
    );
    expect(screen.getByTestId("volume-check-error").textContent).toContain("先在模型配置里接一个模型");
  });
});

// ── 规划台（hook + modal 联动） ─────────────────────────────────────────────

function ModalHarness({
  isPro = true,
  onBackfill,
  genreLabel = "悬疑",
  volumes = [{ name: "vol-1", title: "血酬", chapter_target: 40, chapters: [] }],
}: {
  isPro?: boolean;
  onBackfill: () => void;
  genreLabel?: string;
  volumes?: Parameters<typeof VolumePlanModal>[0]["volumes"];
}) {
  const plan = useVolumePlan("p1");
  return (
    <>
      <button data-testid="open-plan" onClick={() => plan.open(2)}>
        open
      </button>
      <VolumePlanModal
        projectId="p1"
        plan={plan}
        isPro={isPro}
        onUpgrade={noop}
        volumes={volumes}
        genreLabel={genreLabel}
        onBackfill={onBackfill}
        onClose={plan.close}
      />
    </>
  );
}

const THREE_PLANS = {
  ok: true,
  plans: [
    { no: 1, spine: "走向一", conflict: "冲突一", ending: "卷末一", focus: "侧重一", focus_axis: "代价" },
    { no: 2, spine: "走向二", conflict: "冲突二", ending: "卷末二", focus: "侧重二", focus_axis: "关系" },
    { no: 3, spine: "走向三", conflict: "冲突三", ending: "卷末三", focus: "侧重三", focus_axis: "认知" },
  ],
  note: "",
  volume_estimate: "约 3 卷",
  similar: false,
  warnings: [],
};

const EXPAND_RESULT = {
  ok: true,
  vol_no: 2,
  plan_line: "走向二",
  draft: {
    name: "血誓",
    summary: "本卷主旨",
    conflict: "核心矛盾",
    goal: "整体目标",
    ending: "预期结局",
    plants: ["新伏笔"],
    reveals: [],
    chapter_target: 30,
    checks: ["自查一条"],
  },
  warnings: [],
};

describe("VolumePlanModal", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.fetchStoryArc.mockReset();
    apiState.fetchStoryArc.mockResolvedValue({ fullstory: "主线", ending: { scene: "s" } });
    apiState.get.mockResolvedValue({ items: [{ id: 1 }] });
  });

  it("输入为空 → 按这一句展开禁用；免费档两个生成动作都禁用", async () => {
    render(<ModalHarness isPro={false} onBackfill={noop} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    await waitFor(() => expect(screen.getByTestId("plan-line-input")).toBeDefined());
    expect((screen.getByTestId("plan-expand-btn") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByTestId("plan-options-btn") as HTMLButtonElement).disabled).toBe(true);
    // 免费仍可看材料与规则（规划台可进）；输入可写（写了也不放行生成）
    expect(screen.getByText("规划第二卷")).toBeDefined();
    fireEvent.change(screen.getByTestId("plan-line-input"), {
      target: { value: "林野第一次主动出城" },
    });
    expect(screen.getByTestId("plan-line-input").textContent).toBe("林野第一次主动出城");
    expect((screen.getByTestId("plan-expand-btn") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("分卷依据 · 来自你的设定"));
    expect(screen.getByTestId("volume-plan-modal").textContent).toContain("主线全景");
    fireEvent.click(screen.getByText("展开时遵守的规则 · 每卷都带上"));
    expect(screen.getByTestId("volume-plan-modal").textContent).toContain("不凭空添人添事");
  });

  it("材料请求无 items 键与提前卸载：兜底不炸", async () => {
    apiState.fetchStoryArc.mockResolvedValue({});
    apiState.get.mockResolvedValue(undefined);
    const { unmount } = render(<ModalHarness onBackfill={noop} genreLabel="" volumes={[]} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    unmount(); // 卸载早于 resolve → alive=false 分支
    await waitFor(() => expect(apiState.get).toHaveBeenCalled());
  });

  it("材料全缺口：缺口标出不拦（分卷依据 5 行呈 gap 口径）", async () => {
    apiState.fetchStoryArc.mockResolvedValue({});
    apiState.get.mockResolvedValue({ items: "不是数组" });
    render(<ModalHarness onBackfill={noop} genreLabel="" volumes={[]} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    fireEvent.click(await screen.findByText("分卷依据 · 来自你的设定"));
    const rows = screen.getByTestId("volume-plan-modal").textContent;
    expect(rows).toContain("缺口——先去设定补主线");
    expect(rows).toContain("还没有角色卡（不拦）");
    expect(rows).toContain("未设（可不设）");
  });

  it("两套＋similar＋warnings＋note：完成态全部呈现（note 在套数<3 时展示）", async () => {
    apiState.post.mockResolvedValueOnce({
      ok: true,
      plans: [
        { no: 1, spine: "走向甲", conflict: "冲突甲", ending: "卷末甲", focus: "侧重甲", focus_axis: "代价" },
        { no: 2, spine: "走向乙", conflict: "冲突乙", ending: "卷末乙", focus: "侧重乙", focus_axis: "关系" },
      ],
      note: "主线太薄，只想出两套",
      volume_estimate: "",
      similar: true,
      warnings: ["设定里没有这个势力：「夜巡议会」"],
    });
    render(<ModalHarness onBackfill={noop} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    fireEvent.click(await screen.findByTestId("plan-options-btn"));
    await waitFor(() => expect(screen.getByTestId("plan-card-2")).toBeDefined());
    expect(screen.getByTestId("plan-options").textContent).toContain("有两套走向偏像");
    expect(screen.getByTestId("plan-warnings").textContent).toContain("夜巡议会");
    expect(screen.getByTestId("plan-options").textContent).toContain("为什么只有两套：主线太薄");
  });

  it("给我 3 套方案 → 三张四字段卡 → 选一套填回输入框并直接展开 → 完成态含自查条数；点回填", async () => {
    const onBackfill = vi.fn();
    apiState.post.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes/ai/options") return Promise.resolve(THREE_PLANS);
      if (path === "/novels/p1/volumes/ai/expand") return Promise.resolve(EXPAND_RESULT);
      return Promise.resolve({});
    });
    render(<ModalHarness onBackfill={onBackfill} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    fireEvent.click(await screen.findByTestId("plan-options-btn"));
    // 三套不同质：focus_axis 互不相同
    await waitFor(() => expect(screen.getByTestId("plan-card-3")).toBeDefined());
    expect(screen.getByTestId("plan-options").textContent).toContain("代价");
    expect(screen.getByTestId("plan-options").textContent).toContain("关系");
    expect(screen.getByTestId("plan-options").textContent).toContain("认知");
    fireEvent.click(screen.getByTestId("plan-card-2").querySelector("button")!);
    // 选一套 → 填回输入框并直接展开（先填回再请求）
    await waitFor(() =>
      expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes/ai/expand", {
        line: "走向二",
        vol_no: 2,
      }),
    );
    // 生成完成：卷名 · 建议章数 · 自查条数 ＋ 回填
    await waitFor(() => expect(screen.getByTestId("plan-backfill-btn")).toBeDefined());
    expect(screen.getByTestId("plan-done").textContent).toContain("血誓");
    expect(screen.getByTestId("plan-done").textContent).toContain("30");
    expect(screen.getByTestId("plan-done").textContent).toContain("自查 1 处要留意");
    fireEvent.click(screen.getByTestId("plan-backfill-btn"));
    expect(onBackfill).toHaveBeenCalledTimes(1);
  });

  it("按这一句展开 → 完成态呈现自查条与 warnings；「不设」章数回落卷号占位", async () => {
    apiState.post.mockResolvedValueOnce({
      ok: true,
      vol_no: 2,
      plan_line: "林野第一次主动出城",
      draft: {
        name: "",
        summary: "主旨",
        conflict: "矛盾",
        goal: "目标",
        ending: "结局",
        plants: [],
        reveals: [],
        chapter_target: 0,
        checks: [],
      },
      warnings: ["设定里没有这个人物：「夜行人」"],
    });
    render(<ModalHarness onBackfill={noop} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    fireEvent.change(screen.getByTestId("plan-line-input"), {
      target: { value: "林野第一次主动出城" },
    });
    expect((screen.getByTestId("plan-expand-btn") as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(screen.getByTestId("plan-expand-btn"));
    await waitFor(() => expect(screen.getByTestId("plan-backfill-btn")).toBeDefined());
    expect(screen.getByTestId("plan-done").textContent).toContain("第二卷的卷纲已备好");
    expect(screen.getByTestId("plan-done").textContent).toContain("— 章");
    expect(screen.getByTestId("plan-done").textContent).toContain("夜行人");
  });

  it("错误渲染：主线空给「回到设定」提示；其他错误给通用文案；降级 hint 缺省兜底", async () => {
    const onBackfill = vi.fn();
    // 主线空
    apiState.post.mockRejectedValueOnce(new Error("主线为空，请先在设定中完成主线"));
    render(<ModalHarness onBackfill={onBackfill} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    fireEvent.change(screen.getByTestId("plan-line-input"), {
      target: { value: "一句走向" },
    });
    fireEvent.click(screen.getByTestId("plan-expand-btn"));
    await waitFor(() => expect(screen.getByTestId("plan-error")).toBeDefined());
    expect(screen.getByTestId("plan-error").textContent).toContain("回到设定 → 主线");
  });

  it("非主线错误：plan-error 无「回到设定」后缀；降级 hint 空串走缺省文案", async () => {
    const onBackfill = vi.fn();
    apiState.post.mockRejectedValueOnce(new Error("boom"));
    apiState.post.mockResolvedValueOnce({
      ok: true,
      degraded: true,
      text: "散文输出",
      hint: "",
    });
    render(<ModalHarness onBackfill={onBackfill} genreLabel={GENRE_PENDING_LABEL} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    fireEvent.click(await screen.findByTestId("plan-options-btn"));
    await waitFor(() => expect(screen.getByTestId("plan-error")).toBeDefined());
    expect(screen.getByTestId("plan-error").textContent).toBe("boom");
    // 题材待定标签也走「待定（不拦）」分支（待定题材不拦拆卷）
    fireEvent.click(screen.getByText("分卷依据 · 来自你的设定"));
    expect(screen.getByTestId("volume-plan-modal").textContent).toContain("待定（不拦）");
    fireEvent.change(screen.getByTestId("plan-line-input"), {
      target: { value: "一句走向" },
    });
    fireEvent.click(screen.getByTestId("plan-expand-btn"));
    await waitFor(() => expect(screen.getByTestId("plan-degraded")).toBeDefined());
    expect(screen.getByTestId("plan-degraded").textContent).toContain("可重试，或按上面这段手动定走向");
  });

  it("降级输出：纯文本呈现＋提示可重试，不出现回填", async () => {
    const onBackfill = vi.fn();
    apiState.post.mockResolvedValue({
      ok: true,
      degraded: true,
      text: "模型吐了段散文",
      hint: "可重试",
    });
    render(<ModalHarness onBackfill={onBackfill} />);
    fireEvent.click(screen.getByTestId("open-plan"));
    fireEvent.click(await screen.findByTestId("plan-options-btn"));
    await waitFor(() => expect(screen.getByTestId("plan-degraded")).toBeDefined());
    expect(screen.getByTestId("plan-degraded").textContent).toContain("模型吐了段散文");
    expect(screen.queryByTestId("plan-backfill-btn")).toBeNull();
  });

  it("生成中进度只在弹窗内（背景静止的组件侧证据）；步进条随时间推进", async () => {
    vi.useFakeTimers();
    try {
      let resolveExpand: (v: unknown) => void = () => {};
      apiState.post.mockImplementation(
        () =>
          new Promise((resolve) => {
            resolveExpand = resolve;
          }),
      );
      render(<ModalHarness onBackfill={noop} />);
      fireEvent.click(screen.getByTestId("open-plan"));
      fireEvent.change(screen.getByTestId("plan-line-input"), {
        target: { value: "林野第一次主动出城" },
      });
      fireEvent.click(screen.getByTestId("plan-expand-btn"));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(50);
      });
      expect(screen.getByTestId("plan-generating")).toBeDefined();
      expect(screen.getByTestId("plan-generating").textContent).toContain("正在展开第二卷");
      // 进度元素在弹窗容器内；中栏（.col-panel）不存在生成文案（背景静止）
      const modal = screen.getByTestId("volume-plan-modal");
      expect(modal.contains(screen.getByTestId("plan-generating"))).toBe(true);
      expect(document.querySelector(".col-panel")?.textContent ?? "").not.toContain("正在展开");
      // 底条：生成在后台跑，关掉也不影响
      expect(modal.textContent).toContain("生成在后台跑，关掉它也不影响");
      // 步进：900ms/步——推到最后一档后不再前进
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });
      expect(screen.getByTestId("plan-generating").textContent).toContain("自查");
      await act(async () => {
        resolveExpand(EXPAND_RESULT);
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(50);
      });
      expect(screen.getByTestId("plan-backfill-btn")).toBeDefined();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("volumePlanApi 契约", () => {
  it("expand 缺省 vol_no 落 null；options/check 路径与载荷", async () => {
    apiState.post.mockReset();
    apiState.post.mockResolvedValue({});
    const { volumePlanApi } = await import("@/lib/volumePlanApi");
    await volumePlanApi.options("p1", "");
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes/ai/options", { line: "" });
    await volumePlanApi.expand("p1", "一句走向");
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes/ai/expand", {
      line: "一句走向",
      vol_no: null,
    });
    await volumePlanApi.check("p1", "vol-3");
    expect(apiState.post).toHaveBeenCalledWith("/novels/p1/volumes/vol-3/ai/check", {});
  });
});

// ── useVolumePlan 状态机（错误/降级/生成中关弹窗自动回填） ──────────────────

import { renderHook } from "@testing-library/react";

describe("useVolumePlan 状态机", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.fetchStoryArc.mockReset();
    apiState.fetchStoryArc.mockResolvedValue({ fullstory: "主线", ending: { scene: "s" } });
    apiState.get.mockResolvedValue({ items: [] });
  });

  it("生成失败 → error 可重试；主线空 → 引导去设定而非报错文案", async () => {
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1));
    apiState.post.mockRejectedValueOnce(new Error("网络抖了"));
    await act(async () => {
      await result.current.generateOptions();
    });
    expect(result.current.state.error).toBe("网络抖了");
    act(() => result.current.resetError());
    expect(result.current.state.error).toBe("");

    apiState.post.mockRejectedValueOnce(new Error("主线为空，请先在设定中完成主线"));
    await act(async () => {
      await result.current.generateExpand("一句走向");
    });
    expect(result.current.state.error).toContain("先到设定补主线");
    // 无 message 的异常 → 通用可重试文案；空参 expand 直接返回
    apiState.post.mockRejectedValueOnce(undefined);
    await act(async () => {
      await result.current.generateOptions();
    });
    expect(result.current.state.error).toBe("生成失败，请重试");
    await act(async () => {
      await result.current.generateExpand("");
    });
    expect(apiState.post).toHaveBeenCalledTimes(3);
  });

  it("响应缺键：note/warnings/plan_line 兜底不炸；降级无 text 兜底空串", async () => {
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(1));
    // options 只带 plans（缺 note/warnings）
    apiState.post.mockResolvedValueOnce({
      ok: true,
      plans: [
        { no: 1, spine: "甲", conflict: "", ending: "收", focus: "", focus_axis: "代价" },
        { no: 2, spine: "乙", conflict: "", ending: "收", focus: "", focus_axis: "关系" },
      ],
    });
    await act(async () => {
      await result.current.generateOptions();
    });
    expect(result.current.state.plans).toHaveLength(2);
    expect(result.current.state.warnings).toEqual([]);
    // expand 降级且无 text/hint 键
    apiState.post.mockResolvedValueOnce({ ok: true, degraded: true });
    await act(async () => {
      await result.current.generateExpand("甲");
    });
    expect(result.current.state.degradedText).toBe("");
  });

  it("生成中关弹窗 → 完成后 autoBackfill 载荷只被取走一次；降级无载荷", async () => {
    let resolveExpand: (v: unknown) => void = () => {};
    apiState.post.mockImplementation(
      (_path: string, body: { line?: string }) =>
        new Promise((resolve) => {
          resolveExpand = resolve;
          void _path;
          void body;
        }),
    );
    const { result } = renderHook(() => useVolumePlan("p1"));
    act(() => result.current.open(2));
    await act(async () => {
      result.current.generateExpand("走向二");
    });
    act(() => result.current.close());
    expect(result.current.state.open).toBe(false);
    expect(result.current.state.phase).toBe("generating");
    await act(async () => {
      resolveExpand(EXPAND_RESULT);
    });
    await waitFor(() => expect(result.current.state.phase).toBe("done"));
    const payload = result.current.takeAutoBackfill();
    expect(payload?.volNo).toBe(2);
    expect(payload?.draft.name).toBe("血誓");
    expect(result.current.takeAutoBackfill()).toBeNull(); // 读走即清

    // 降级：无 autoBackfill 载荷
    apiState.post.mockResolvedValueOnce({ ok: true, degraded: true, text: "散文", hint: "" });
    act(() => result.current.open(3));
    await act(async () => {
      await result.current.generateExpand("另一句");
    });
    expect(result.current.state.degradedText).toBe("散文");
    expect(result.current.takeAutoBackfill()).toBeNull();
  });
});

// ── 回填（VolumeWorkspace） ─────────────────────────────────────────────────

const VOL_DETAIL: VolumeDetail = {
  ref: "vol-2",
  volume: 2,
  title: "第二卷",
  summary: "",
  plan_line: "",
  prev_ending: { text: "上一卷他签了字", source: "第1卷 · 预期结局（还没写到，先按卷纲）" },
  plants: [],
  reveals: [],
  cast_members: [],
  plot_nodes: [],
  ghost_count: 0,
  chapters: [],
};

describe("VolumeWorkspace 回填", () => {
  beforeEach(() => {
    apiState.get.mockReset();
    apiState.post.mockReset();
    apiState.put.mockReset();
    apiState.get.mockImplementation((path: string) => {
      if (path === "/novels/p1/volumes/vol-2")
        return Promise.resolve(VOL_DETAIL);
      if (path === "/novels/p1/frontier") return Promise.resolve({ frontier: null });
      return Promise.resolve({});
    });
  });

  it("逐段落下：主旨/矛盾/目标/结局/章数/伏笔落表单；进场与展开依据只读行", async () => {
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
              goal: "目标X",
              ending: "结局X",
              plants: ["伏笔X"],
              reveals: ["揭示X"],
              chapter_target: 30,
              checks: [],
            },
            planLine: "走向二",
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
      // 进场与展开依据只读行
      expect(screen.getByTestId("vol-prev-ending").textContent).toContain("上一卷他签了字");
      expect(screen.getByTestId("vol-plan-line").textContent).toBe("走向二");
      // 走完 7 段（160ms/段）
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1400);
      });
      expect((document.getElementById("vol-summary") as HTMLTextAreaElement).value).toBe("主旨X");
      expect((document.getElementById("vol-conflict") as HTMLTextAreaElement).value).toBe("矛盾X");
      expect((document.getElementById("vol-goal") as HTMLTextAreaElement).value).toBe("目标X");
      expect((document.getElementById("vol-ending") as HTMLTextAreaElement).value).toBe("结局X");
      expect((document.getElementById("vol-target") as HTMLInputElement).value).toBe("30");
      expect((document.getElementById("vol-plants") as HTMLTextAreaElement).value).toBe("伏笔X");
      expect((document.getElementById("vol-reveals") as HTMLTextAreaElement).value).toBe("揭示X");
      expect((document.getElementById("vol-name") as HTMLInputElement).value).toBe("血誓");
      expect(saveBtn().disabled).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});
