// 条目图接线测试（c-kb-organize 批D）：数据装载、关系清单渲染、cap 截断、空态、错误兜底。
// 图装配（force-graph）由 kbGraphView.test 同构覆盖；本文件 mock kbApi.organize 命名空间。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  graphEntries: vi.fn(),
  status: vi.fn(),
  findings: vi.fn(),
  run: vi.fn(),
  adoptFinding: vi.fn(),
  ignoreFinding: vi.fn(),
  adoptRelation: vi.fn(),
  rejectRelation: vi.fn(),
  relationFeedback: vi.fn(),
}));

vi.mock("@/lib/kbApi", () => ({
  kbApi: { organize: api },
}));

import "force-graph";
import KbEntryGraphView from "@/components/tools/KbEntryGraphView";
import { mountEntryGraph } from "@/lib/kbEntryGraph";

const GRAPH = {
  genre: "玄幻",
  nodes: [
    { id: "e1", title: "打斗手法", concept: "手法", instruction: "先果后因。" },
    { id: "e2", title: "短句文风", concept: "文风", instruction: "打斗短句。" },
  ],
  edges: [
    { rel_type: "applies_to", from_id: "e1", to_id: "e2", confidence: 0.9, note: "打斗适用", evidence: "第3章" },
  ],
  edge_count: 1,
  edge_truncated: 0,
};

beforeEach(() => {
  api.graphEntries.mockReset();
  api.graphEntries.mockResolvedValue(GRAPH);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KbEntryGraph", () => {
  it("数据装载与关系清单渲染", async () => {
    render(<KbEntryGraphView genre="玄幻" />);
    await waitFor(() => expect(api.graphEntries).toHaveBeenCalledWith("玄幻"));
    await waitFor(() => expect(screen.getByText(/打斗手法 → 短句文风/)).toBeTruthy());
    expect(screen.getByText(/置信 90%/)).toBeTruthy();
  });

  it("清单点击出详情浮层（说明＋证据）", async () => {
    render(<KbEntryGraphView genre="玄幻" />);
    await waitFor(() => expect(screen.getByText(/打斗手法 → 短句文风/)).toBeTruthy());
    fireEvent.click(screen.getByText(/打斗手法 → 短句文风/).closest("button")!);
    await waitFor(() => expect(screen.getByTestId("edge-info")).toBeTruthy());
    expect(screen.getAllByText(/applies_to/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/证据：第3章/)).toBeTruthy();
    fireEvent.click(screen.getByText("收起"));
    expect(screen.queryByTestId("edge-info")).toBeNull();
  });

  it("cap 截断提示", async () => {
    api.graphEntries.mockResolvedValue({ ...GRAPH, edge_truncated: 7 });
    render(<KbEntryGraphView genre="玄幻" />);
    await waitFor(() => expect(screen.getByText(/另有 7 条未画出/)).toBeTruthy());
  });

  it("空态", async () => {
    api.graphEntries.mockResolvedValue({ ...GRAPH, edges: [], edge_count: 0 });
    render(<KbEntryGraphView genre="玄幻" />);
    await waitFor(() => expect(screen.getByText(/还没有生效关系/)).toBeTruthy());
  });

  it("错误兜底", async () => {
    api.graphEntries.mockRejectedValue(new Error("条目图加载失败"));
    render(<KbEntryGraphView genre="玄幻" />);
    await waitFor(() => expect(screen.getByText("条目图加载失败")).toBeTruthy());
  });
});

import { assembleEntryGraph, type EntryGraphFactory, type EntryGraphInstance } from "@/lib/kbEntryGraph";

describe("assembleEntryGraph（装配纯函数）", () => {
  it("链式配置与边点击回调回放", async () => {
    const inst: Record<string, ReturnType<typeof vi.fn>> = {};
    for (const k of ["nodeId", "nodeColor", "nodeLabel", "nodeVal", "linkColor",
      "linkWidth", "width", "height", "onLinkClick"]) {
      inst[k] = vi.fn().mockReturnValue(inst);
    }
    const factory = vi.fn(() => inst);
    const el = { clientWidth: 800 } as unknown as HTMLElement;
    let captured: unknown = null;
    const g = assembleEntryGraph(factory as unknown as EntryGraphFactory, el, {
      onEdgeClick: (info) => { captured = info; },
      titleOf: (id) => (id === "e1" ? "打斗手法" : "短句文风"),
    });
    expect(g).toBe(inst);
    expect(inst.width).toHaveBeenCalledWith(800);
    expect(inst.height).toHaveBeenCalledWith(480);
    const clickFn = inst.onLinkClick.mock.calls[0][0] as (l: object) => void;
    clickFn({ source: "e1", target: "e2", rel_type: "applies_to", note: "n", evidence: "第3章", confidence: 0.9 });
    expect(captured).toMatchObject({
      rel_type: "applies_to", from_title: "打斗手法", to_title: "短句文风", confidence: 0.9,
    });
    clickFn({ source: { id: "e1" }, target: { id: "e2" }, rel_type: "refines" });
    expect((captured as { to_title: string }).to_title).toBe("短句文风");
  });
});

describe("mountEntryGraph 装配直测", () => {
  it("链式配置与边点击回调回放", () => {
    const inst: Record<string, ReturnType<typeof vi.fn>> = {};
    for (const k of ["nodeId", "nodeColor", "nodeLabel", "nodeVal", "linkColor",
      "linkWidth", "width", "height", "onLinkClick"]) {
      inst[k] = vi.fn().mockReturnValue(inst);
    }
    const factory = vi.fn(() => inst);
    const el = { clientWidth: 800 } as unknown as HTMLElement;
    let captured: unknown = null;
    const g = mountEntryGraph(factory as unknown as Parameters<typeof mountEntryGraph>[0], el, (info) => { captured = info; },
      (id) => (id === "e1" ? "打斗手法" : "短句文风"));
    expect(g).toBe(inst);
    expect(inst.width).toHaveBeenCalledWith(800);
    const click = inst.onLinkClick.mock.calls[0][0] as (l: object) => void;
    click({ source: "e1", target: "e2", rel_type: "applies_to", note: "n", evidence: "第3章", confidence: 0.9 });
    expect(captured).toMatchObject({ rel_type: "applies_to", from_title: "打斗手法", to_title: "短句文风", confidence: 0.9 });
    click({ source: { id: "e1" }, target: { id: "e2" }, rel_type: "refines" });
    expect((captured as { to_title: string }).to_title).toBe("短句文风");
  });
});
