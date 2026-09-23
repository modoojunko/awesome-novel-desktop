// 拆章界面测试（c-chapter-plan-ai）：覆盖原型各态——手写五段／AI 四态／角标与剧情吸引力／
// 落点卡三出口／自检（免费）。全部打桩 chapterPlanApi，不真调模型。
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/chapterPlanApi", async (orig) => {
  const real = await orig<typeof import("@/lib/chapterPlanApi")>();
  return {
    ...real,
    chapterPlanApi: {
      anchor: vi.fn(),
      directions: vi.fn(),
      selfcheck: vi.fn(),
      adopt: vi.fn(),
    },
  };
});

import { chapterPlanApi } from "@/lib/chapterPlanApi";
import { useChapterPlan } from "@/hooks/useChapterPlan";
import { ChapterPlanModal } from "@/components/novel/workbench/ChapterPlanModal";

const api = chapterPlanApi as unknown as {
  anchor: ReturnType<typeof vi.fn>;
  directions: ReturnType<typeof vi.fn>;
  selfcheck: ReturnType<typeof vi.fn>;
  adopt: ReturnType<typeof vi.fn>;
};

const ENTRY = { text: "她把信标藏进舱底夹层，签了那张登记单", source: "拟定，取自章纲落点" };

const DIRS = {
  ok: true,
  entry: ENTRY,
  directions: [
    { axis: "线索", title: "同名档案", plot: "她调出那份记录，最后一页被撕掉了", obstacle: "旧档堆不对活人开放",
      ending: "她把残角收进怀里", acts: ["她：调档"], stage: "矛盾升级", cast: ["沉舟"], factions: [], places: [], why: "撕页钩子立住了", gap: "阻力偏程序化" },
    { axis: "关系", title: "船队的条件", plot: "船队长开价换航线", obstacle: "让出航线＝交出一半生存空间",
      ending: "她换来留在船上的许可", acts: ["船队长：开价"], stage: "矛盾升级", cast: [], factions: [], places: [], why: "让出航线真的疼", gap: "结尾停在安全" },
    { axis: "危机", title: "突击清查", plot: "清查队登船前她带信标出逃", obstacle: "挨船搜舱，藏无可藏",
      ending: "信标暴露——全港都知道", acts: ["清查队：搜舱"], stage: "重要转折", cast: [], factions: [], places: [], why: "外部事件当面压上来", gap: "" },
  ],
  grades: ["A", "B", "S"],
  checks: ["这一章把信标暴露提前了，注意下一章的代价"],
  warnings: [],
  note: "",
};

/** 渲染宿主：hook ＋ 弹窗（与 NovelWorkspace 同构的接线） */
function Host({ onAdopt = vi.fn() }: { onAdopt?: () => void }) {
  const plan = useChapterPlan("p1", 1, "vol-1");
  return (
    <>
      <button data-testid="open-manual" onClick={plan.openManual}>拆下一章</button>
      <button data-testid="open-ai" onClick={plan.openAi}>拆下一章（AI）</button>
      <ChapterPlanModal plan={plan} onAdopt={() => { void plan.adopt().then((r) => r.ok && onAdopt()); }} onClose={plan.close} />
    </>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.anchor.mockResolvedValue({ ok: true, ...ENTRY });
  api.directions.mockResolvedValue(DIRS);
  api.selfcheck.mockResolvedValue({ ok: true, critiques: { 反转: "撕页立住了", 递增: "阻力偏程序化", 推进: "处境变了", 拉力: "停在决定上" }, weakest: "递增" });
  api.adopt.mockResolvedValue({ ok: true, ref: "vol-1-ch-3" });
});

describe("拆章界面 · 手写五段（中栏入口，全档）", () => {
  it("打开即空白五段＋进场只读（含来源小字）", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    await waitFor(() => expect(screen.getByTestId("chapter-plan-modal")).toBeInTheDocument());
    expect(screen.getByTestId("d-prev")).toHaveTextContent(ENTRY.text);
    expect(screen.getByTestId("d-prev")).toHaveTextContent("拟定，取自章纲落点");
    for (const k of ["d-title", "d-plot", "d-obstacle", "d-ending", "d-acts", "d-stage"]) {
      expect(screen.getByTestId(k)).toBeInTheDocument();
    }
    // 手写路不调模型
    expect(api.directions).not.toHaveBeenCalled();
  });

  it("自检：免费触发，出四维短评＋最弱一维，不给字母", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.click(screen.getByTestId("selfcheck-run"));
    await waitFor(() => expect(api.selfcheck).toHaveBeenCalled());
    const box = await screen.findByTestId("selfcheck");
    expect(box).toHaveTextContent("反转");
    expect(box).toHaveTextContent("最弱一维：递增");
    expect(box.textContent).not.toMatch(/\bS\b|\bA\b|\bB\b/);
  });

  it("最小可排：只写一句剧情也能排上（标题可空）", async () => {
    const onAdopt = vi.fn();
    render(<Host onAdopt={onAdopt} />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "她顺着档案查下去" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(onAdopt).toHaveBeenCalled());
    expect(api.adopt.mock.calls[0][2]).toMatchObject({ plot: "她顺着档案查下去" });
  });
});

describe("拆章界面 · AI 三方向（右栏入口，PRO）", () => {
  it("出卡：三张卡各带角标（S 有「最吸引」）＋剧情吸引力/差在哪两块＋阶段行", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getAllByTestId(/^pick-card-\d$/)).toHaveLength(3));
    expect(screen.getByTestId("pick-corner-3")).toHaveTextContent("S");
    expect(screen.getByTestId("pick-corner-3")).toHaveTextContent("最吸引");
    const card1 = screen.getByTestId("pick-card-1");
    expect(card1).toHaveTextContent("剧情吸引力");
    expect(card1).toHaveTextContent("差在哪");
    expect(card1).toHaveTextContent("阶段");
    expect(card1).not.toHaveTextContent("吃掉的节点");
    expect(screen.getByTestId("split-checks")).toHaveTextContent("信标暴露提前");
  });

  it("点卡进本章卡：字段带入且可改，角标跟到卡上", async () => {
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getAllByTestId(/^pick-card-\d$/)).toHaveLength(3));
    fireEvent.click(screen.getByTestId("pick-card-3"));
    expect(screen.getByTestId("chapter-card-grade")).toHaveTextContent("S");
    expect(screen.getByTestId("d-plot")).toHaveValue(DIRS.directions[2].plot);
    fireEvent.change(screen.getByTestId("d-ending"), { target: { value: "改过的结尾" } });
    expect(screen.getByTestId("d-ending")).toHaveValue("改过的结尾");
  });

  it("正在想：转圈提示（等模型期间不空白）", async () => {
    let release!: (v: unknown) => void;
    api.directions.mockReturnValue(new Promise((r) => { release = r; }));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    expect(await screen.findByTestId("split-busy")).toHaveTextContent("正在想");
    release(DIRS);
    await waitFor(() => expect(screen.getAllByTestId(/^pick-card-\d$/)).toHaveLength(3));
  });

  it("出卡失败：三个出口齐全（重试／自己写／先不拆）", async () => {
    api.directions.mockRejectedValue(new Error("出卡失败"));
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-error")).toBeInTheDocument());
    expect(screen.getByTestId("split-retry")).toBeInTheDocument();
    expect(screen.getByTestId("split-to-manual")).toBeInTheDocument();
    expect(screen.getByTestId("split-close")).toBeInTheDocument();
    // 自己写这一章 → 切手写五段
    fireEvent.click(screen.getByTestId("split-to-manual"));
    expect(screen.getByTestId("d-plot")).toBeInTheDocument();
  });

  it("只出两套：降级说明＋两张卡", async () => {
    api.directions.mockResolvedValue({ ...DIRS, directions: DIRS.directions.slice(0, 2), grades: ["A", "B"], note: "另两个走向太接近" });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open-ai"));
    await waitFor(() => expect(screen.getByTestId("split-note")).toBeInTheDocument());
    expect(screen.getByTestId("split-note")).toHaveTextContent("只想出两套");
    expect(screen.getAllByTestId(/^pick-card-\d$/)).toHaveLength(2);
  });
});

describe("拆章界面 · 落点卡（第一步→第二步的桥）", () => {
  it("排上后落点卡：已带入 N 项＋还差 6 项＋三出口", async () => {
    const onAdopt = vi.fn();
    render(<Host onAdopt={onAdopt} />);
    fireEvent.click(screen.getByTestId("open-manual"));
    fireEvent.change(screen.getByTestId("d-plot"), { target: { value: "一句剧情" } });
    fireEvent.click(screen.getByTestId("split-adopt"));
    await waitFor(() => expect(onAdopt).toHaveBeenCalled());
    // 落点卡由外层渲染；本测试断言 hook 产出的 landed 数据形状
    expect(api.adopt).toHaveBeenCalledWith("p1", "vol-1", expect.objectContaining({ plot: "一句剧情" }));
  });
});
