// 章剧情三版抽卡（c-plot-split 5.2/5.3）：代际守卫＋失败二分三出口＋替换明示。
// **打桩层＝`@/lib/api`**（契约真的执行：URL/响应映射写错这里能红）。
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  request: vi.fn(),
}));

import { api } from "@/lib/api";
import { usePlotDraw, type PlotDrawController } from "@/hooks/usePlotDraw";
import PlotDrawModal from "@/components/novel/workbench/PlotDrawModal";

const mockApi = api as unknown as { post: ReturnType<typeof vi.fn> };

/** 渲染宿主：hook ＋ 弹窗（与 ChapterWorkspace 同构接线）＋ 探针按钮 */
function Host({
  onAdopt = vi.fn(),
  writtenCount = 0,
}: {
  onAdopt?: (items: string[]) => void;
  writtenCount?: number;
}) {
  const draw: PlotDrawController = usePlotDraw("p1", "vol-1-ch-2");
  return (
    <>
      <button data-testid="open" onClick={draw.openDraw}>开</button>
      <button data-testid="redraw" onClick={draw.redraw}>换一批</button>
      <button data-testid="close" onClick={draw.close}>关</button>
      <span data-testid="phase">{draw.state.phase}</span>
      <span data-testid="pick">{draw.state.pick == null ? "-" : String(draw.state.pick)}</span>
      <PlotDrawModal
        state={draw.state}
        chapterLabel="第2章 · 锚点"
        writtenCount={writtenCount}
        onPick={draw.pickCard}
        onAdopt={() => {
          const { pick, versions } = draw.state;
          if (pick != null) onAdopt(versions[pick]);
        }}
        onRedraw={draw.redraw}
        onManual={draw.close}
        onClose={draw.close}
        onOpenConfig={vi.fn()}
      />
    </>
  );
}

const THREE = {
  ok: true,
  versions: [
    { items: ["起——接进场", "中段甲一", "止——收章末"] },
    { items: ["起——接进场", "中段乙一", "中段乙二", "止——收章末"] },
    { items: ["起——接进场", "中段丙一", "止——收章末"] },
  ],
  grades: ["S", "A", ""],
  warnings: [],
};

describe("三版抽卡弹窗（c-plot-split）", () => {
  it("成功出 3 版：卡面逐条预览＋角标，缺名次不出角标", async () => {
    mockApi.post.mockResolvedValue(THREE);
    render(<Host />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    // 三版共用首尾：首条/末条逐字相同
    expect(screen.getAllByText("起——接进场")).toHaveLength(3);
    expect(screen.getAllByText("止——收章末")).toHaveLength(3);
    // 角标：S/A 出、缺名次不出
    expect(screen.getByTitle("抓人程度 S")).toHaveTextContent("S");
    expect(screen.getByTitle("抓人程度 A")).toHaveTextContent("A");
    expect(screen.queryByTitle("抓人程度 ")).not.toBeInTheDocument();
  });

  it("点卡选中后按钮明示「将替换已写的 N 条」，N＝已写非空条数", async () => {
    mockApi.post.mockResolvedValue(THREE);
    render(<Host writtenCount={3} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    const adopt = screen.getByTestId("plot-adopt");
    expect(adopt).toBeDisabled();
    expect(adopt).toHaveTextContent("就填这版 · 将替换已写的 3 条");
    fireEvent.click(screen.getByTestId("plot-card-1"));
    expect(adopt).not.toBeDisabled();
  });

  it("就填这版＝整表替换该版条目（onAdopt 收到选中版）", async () => {
    mockApi.post.mockResolvedValue(THREE);
    const onAdopt = vi.fn();
    render(<Host onAdopt={onAdopt} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("plot-card-1"));
    fireEvent.click(screen.getByTestId("plot-adopt"));
    expect(onAdopt).toHaveBeenCalledWith(THREE.versions[1].items);
  });

  it("换一批清选中（上一批候选作废）", async () => {
    mockApi.post.mockResolvedValue(THREE);
    render(<Host />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("plot-card-2"));
    expect(screen.getByTestId("pick")).toHaveTextContent("2");
    fireEvent.click(screen.getByTestId("redraw"));
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    expect(screen.getByTestId("pick")).toHaveTextContent("-");
    expect(screen.getByTestId("plot-adopt")).toBeDisabled();
  });

  it("关窗后晚到响应不落表（代际守卫丢弃）", async () => {
    let release: (v: unknown) => void = () => {};
    mockApi.post.mockReturnValue(
      new Promise((r) => {
        release = r;
      }),
    );
    render(<Host />);
    fireEvent.click(screen.getByTestId("open"));
    expect(screen.getByTestId("phase")).toHaveTextContent("busy");
    expect(screen.getByTestId("plot-busy")).toHaveTextContent("AI 创作中，请勿关闭弹窗");
    fireEvent.click(screen.getByTestId("close")); // 关窗＝换代
    await act(async () => {
      release(THREE); // 晚到才返回
    });
    expect(screen.getByTestId("phase")).toHaveTextContent("busy"); // 状态未被晚到响应改写
    expect(screen.queryByTestId("plot-grid")).not.toBeInTheDocument();
  });

  it("自己写＝关窗退回原列表（不触发采纳）", async () => {
    mockApi.post.mockResolvedValue(THREE);
    const onAdopt = vi.fn();
    render(<Host onAdopt={onAdopt} />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("plot-manual"));
    expect(onAdopt).not.toHaveBeenCalled();
    // Modal 200ms 退场后再卸载
    await waitFor(() => expect(screen.queryByTestId("plot-grid")).not.toBeInTheDocument());
  });

  it("凑不满 3 版判失败：不出 2 版候选，走失败三出口", async () => {
    mockApi.post.mockResolvedValue({
      ok: true,
      versions: [
        { items: ["起", "中", "止"] },
        { items: ["起", "中", "止"] },
      ],
      grades: ["S", "A"],
      warnings: [],
    });
    render(<Host />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("plot-error")).toBeInTheDocument());
    expect(screen.queryByTestId("plot-grid")).not.toBeInTheDocument();
    // 三出口：去模型配置 / 再试一次 / 先自己写
    expect(screen.getByTestId("plot-config")).toBeInTheDocument();
    expect(screen.getByTestId("plot-retry")).toBeInTheDocument();
    expect(screen.getByTestId("plot-manual")).toBeInTheDocument();
  });

  it("请求异常也走失败三出口（再试一次能重抽）", async () => {
    mockApi.post.mockRejectedValueOnce(new Error("boom"));
    mockApi.post.mockResolvedValueOnce(THREE);
    render(<Host />);
    fireEvent.click(screen.getByTestId("open"));
    await waitFor(() => expect(screen.getByTestId("plot-error")).toBeInTheDocument());
    fireEvent.click(screen.getByTestId("plot-retry"));
    await waitFor(() => expect(screen.getByTestId("plot-grid")).toBeInTheDocument());
  });
});
