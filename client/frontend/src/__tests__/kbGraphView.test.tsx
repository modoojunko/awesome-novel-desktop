// 全局图组件接线测试（c-kb-organize）：force-graph mock 下验证聚合装载、格子点击下钻、
// 面包屑返回、错误兜底、卸载清理。canvas 本体不在此测（jsdom 无 2D 上下文）。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  graphAggregate: vi.fn(),
  graphCell: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return { ...actual, kbApi: { ...actual.kbApi, ...api } };
});

// force-graph mock：链式实例记录配置，onNodeClick/onNodeHover 句柄可回放
const graphInstance = vi.hoisted(() => {
  const inst: Record<string, ReturnType<typeof vi.fn>> = {};
  const chain = [
    "graphData", "nodeColor", "nodeLabel", "nodeVal", "linkColor", "linkWidth",
    "nodeId", "nodeCanvasObject", "onNodeHover", "onNodeClick", "width", "height",
  ];
  for (const k of chain) inst[k] = vi.fn().mockReturnValue(inst);
  return inst;
});

const forceGraphFactory = vi.hoisted(() => vi.fn(() => graphInstance));

vi.mock("force-graph", () => ({ default: forceGraphFactory }));

import KbGraph from "@/components/tools/KbGraph";

const AGG = {
  nodes: [
    { id: "genre:都市", kind: "genre" as const, genre: "都市", concept: "", count: 5 },
    { id: "cell:都市:文风", kind: "cell" as const, genre: "都市", concept: "文风", count: 3 },
  ],
  links: [{ source: "genre:都市", target: "cell:都市:文风" }],
};

const CELL = {
  nodes: [
    { id: "e1", kind: "entry" as const, genre: "都市", concept: "文风", title: "先果后因", scope: "base" },
    { id: "e2", kind: "entry" as const, genre: "都市", concept: "文风", title: "打斗短句", scope: "scene" },
  ],
};

beforeEach(() => {
  api.graphAggregate.mockResolvedValue(AGG);
  api.graphCell.mockResolvedValue(CELL);
  forceGraphFactory.mockClear();
  for (const k of Object.keys(graphInstance)) graphInstance[k].mockClear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KbGraph", () => {
  it("挂载建图＋聚合数据装载；点格子下钻＋面包屑；点题材格不重复下钻（drill 态）", async () => {
    render(<KbGraph />);
    // 建图一次
    await waitFor(() => expect(forceGraphFactory).toHaveBeenCalledTimes(1));
    expect(graphInstance.graphData).toHaveBeenCalled();
    const aggData = graphInstance.graphData.mock.calls.at(-1)![0] as { nodes: { id: string }[] };
    expect(aggData.nodes.map((n) => n.id)).toEqual(["genre:都市", "cell:都市:文风"]);
    // 悬停句柄注册
    expect(graphInstance.onNodeHover).toHaveBeenCalled();
    expect(graphInstance.onNodeClick).toHaveBeenCalled();
    // 点格子 → 下钻
    const onCellClick = graphInstance.onNodeClick.mock.calls[0][0] as (n: object) => void;
    onCellClick({ id: "cell:都市:文风", kind: "cell", genre: "都市", concept: "文风" });
    await waitFor(() => expect(api.graphCell).toHaveBeenCalledWith("都市", "文风"));
    await screen.findByText("文风"); // 面包屑概念段
    const cellData = graphInstance.graphData.mock.calls.at(-1)![0] as { nodes: { id: string }[] };
    expect(cellData.nodes.map((n) => n.id)).toEqual(["cell:都市:文风", "e1", "e2"]);
    // 已下钻再点格子不再触发（drill 守卫臂）
    onCellClick({ id: "cell:都市:文风", kind: "cell", genre: "都市", concept: "文风" });
    expect(api.graphCell).toHaveBeenCalledTimes(1);
    // 面包屑返回聚合
    fireEvent.click(screen.getByText("跨题材通用".length ? "都市" : "都市"));
    await waitFor(() => expect(api.graphAggregate).toHaveBeenCalledTimes(2));
  });

  it("聚合接口失败：错误条不炸；无 message 走兜底文案", async () => {
    api.graphAggregate.mockRejectedValue(new Error("net down"));
    render(<KbGraph />);
    expect(await screen.findByText("net down")).toBeInTheDocument();

    api.graphAggregate.mockRejectedValue({ message: "" });
    render(<KbGraph />);
    expect(await screen.findByText("图谱加载失败")).toBeInTheDocument();
  });

  it("渲染回调回放：悬停邻域高亮配色、条目 scope 分色、恒显标签绘制", async () => {
    render(<KbGraph />);
    await waitFor(() => expect(graphInstance.nodeColor).toHaveBeenCalled());
    const nodeColor = graphInstance.nodeColor.mock.calls[0][0] as (n: object) => string;
    const draw = graphInstance.nodeCanvasObject.mock.calls[0][0] as (
      n: object, ctx: CanvasRenderingContext2D, scale: number,
    ) => void;
    const onHover = graphInstance.onNodeHover.mock.calls[0][0] as (n: object | null) => void;

    // 无悬停：各 kind 分色
    expect(nodeColor({ id: "genre:都市", kind: "genre" })).toBeTruthy();
    expect(nodeColor({ id: "cell:都市:文风", kind: "cell" })).toBeTruthy();
    expect(nodeColor({ id: "e1", kind: "entry", scope: "base" })).toBeTruthy();
    expect(nodeColor({ id: "e2", kind: "entry", scope: "scene" })).toBeTruthy(); // 场景条目分色臂
    // 悬停中：邻域内原色、邻域外高斯暗
    onHover({ id: "cell:都市:文风" });
    expect(nodeColor({ id: "cell:都市:文风", kind: "cell" })).not.toMatch(/rgba\(0,0,0/); // 自身
    expect(nodeColor({ id: "genre:都市", kind: "genre" })).not.toMatch(/rgba\(0,0,0/); // 邻居
    expect(nodeColor({ id: "far", kind: "cell" })).toMatch(/rgba\(0,0,0/); // 非邻域压暗
    onHover(null);
    expect(nodeColor({ id: "far", kind: "cell" })).not.toMatch(/rgba\(0,0,0/);

    // 访问器与连边配置回放
    expect((graphInstance.nodeId.mock.calls[0][0] as (n: object) => string)({ id: "x" })).toBe("x");
    expect((graphInstance.nodeVal.mock.calls[0][0] as (n: object) => number)({ val: 3 })).toBe(3);
    expect((graphInstance.nodeLabel.mock.calls[0][0] as (n: object) => string)({ label: "L" })).toBe("L");
    expect((graphInstance.linkColor.mock.calls[0][0] as (l: object) => string)({})).toBeTruthy();
    expect((graphInstance.linkWidth.mock.calls[0][0] as (l: object) => number)({})).toBe(1);

    // 标签绘制：大节点加粗＋y 偏移；无坐标早退
    interface CtxStub {
      font: string;
      fillText: ReturnType<typeof vi.fn>;
    }
    const ctx = {
      font: "", fillStyle: "", textAlign: "", textBaseline: "", fillText: vi.fn(),
    } as unknown as CanvasRenderingContext2D;
    const stub = ctx as unknown as CtxStub;
    draw({ label: "都市 9", x: 10, y: 20, val: 8 }, ctx, 2);
    expect(stub.font).toContain("600");
    expect(stub.fillText).toHaveBeenCalled();
    draw({ label: "小", x: 1, y: 2, val: 2 }, ctx, 1);
    expect(stub.font).toContain("400");
    draw({ label: "无坐标" }, ctx, 1); // 早退臂
    expect(stub.fillText).toHaveBeenCalledTimes(2);
  });

  it("卸载竞态：import resolve 前 unmount，早退臂不建图", async () => {
    const { unmount } = render(<KbGraph />);
    unmount(); // 动态 import 尚未 resolve
    await new Promise((r) => setTimeout(r, 20)); // 放行微任务
    // 不炸即过（alive=false 早退）；后续正常用例不受污染
    render(<KbGraph />);
    await waitFor(() => expect(forceGraphFactory).toHaveBeenCalledTimes(1));
  });

  it("容器缺尺寸回落 800×480；卸载清空容器", async () => {
    const { unmount } = render(<KbGraph />);
    await waitFor(() => expect(forceGraphFactory).toHaveBeenCalled());
    expect(graphInstance.width).toHaveBeenCalledWith(800); // jsdom clientWidth=0 回落
    expect(graphInstance.height).toHaveBeenCalledWith(480);
    unmount();
  });
});
