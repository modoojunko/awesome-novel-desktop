// 知识树视图测试（原型定稿 2026-11-08：树只管结构——实例不树上展开，点叶子开抽屉）。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  graphTree: vi.fn(),
  instancesFlat: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return {
    ...actual,
    kbApi: {
      ...actual.kbApi,
      graphTree: api.graphTree,
      instancesFlat: api.instancesFlat,
    },
  };
});

import KnowledgeTreePanel from "@/components/tools/KnowledgeTreePanel";
import type { KbInstanceRow } from "@/lib/kbApi";

const TREE = {
  ok: true,
  roots: [
    {
      id: "root:都市:", kind: "root", title: "写作知识", concept: "", genre: "都市",
      definition: "", children: [
        {
          id: "k1", kind: "knowledge", title: "笔法", concept: "文笔", genre: "都市",
          definition: "怎么落笔", children: [
            {
              id: "k2", kind: "knowledge", title: "场面打法", concept: "手法", genre: "都市",
              definition: "场面写法", children: [
                { id: "k3", kind: "knowledge", title: "大招打法", concept: "手法", genre: "都市", definition: "", children: [] },
              ],
            },
          ],
        },
        { id: "k9", kind: "knowledge", title: "其他", concept: "", genre: "都市", definition: "暂存", children: [] },
      ],
    },
  ],
  rel_edges: [],
};

const INSTANCE = (id: string, kid: string, text: string): KbInstanceRow => ({
  row_kind: "instance",
  id,
  knowledge_id: kid,
  knowledge_title: "",
  chain: [],
  genre: "都市",
  concept: "手法",
  text,
  quote: "原文例句",
  source_novel: "测试书",
  source_chapter: "第1章",
  src_kind: "拆书",
  created_at: "2026-11-08T00:00:00",
  fields_json: "{}",
  knowledge_schema_json: "[]",
  name: "",
});

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("KnowledgeTreePanel", () => {
  it("层级渲染知识点，默认展开枝干、叶子收起", async () => {
    api.graphTree.mockResolvedValue(TREE);
    api.instancesFlat.mockResolvedValue({ ok: true, rows: [] });
    render(<KnowledgeTreePanel genre="都市" />);
    await waitFor(() => expect(screen.getByTestId("kb-tree-panel")).toBeTruthy());
    expect(screen.getByText("笔法")).toBeTruthy();
    expect(screen.getByText("场面打法")).toBeTruthy();
    expect(screen.queryByText("大招打法")).toBeNull();
  });

  it("树只管结构：实例不树上展开，点叶子开抽屉看实例列表", async () => {
    api.graphTree.mockResolvedValue(TREE);
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [INSTANCE("i1", "k9", "他推门进来，风铃响了一声。")],
    });
    render(<KnowledgeTreePanel genre="都市" />);
    await waitFor(() => expect(screen.getByTestId("kb-tree-panel")).toBeTruthy());
    // 树面上没有实例行（结构纯净）
    expect(screen.queryByTestId("kb-tree-instance")).toBeNull();
    // 点叶子「其他」→ 抽屉打开，实例列在抽屉里
    fireEvent.click(screen.getByText("其他"));
    await waitFor(() => expect(screen.getByTestId("kb-tree-drawer")).toBeTruthy());
    const insts = screen.getAllByTestId("kb-tree-instance");
    expect(insts.length).toBe(1);
    expect(screen.getByText(/风铃/)).toBeTruthy();
    // 关抽屉
    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByTestId("kb-tree-drawer")).toBeNull());
  });

  it("实例数徽标＝该知识点实例数；抽屉里点实例回调详情", async () => {
    api.graphTree.mockResolvedValue(TREE);
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [INSTANCE("i1", "k9", "实例甲"), INSTANCE("i2", "k9", "实例乙")],
    });
    const onSelect = vi.fn();
    render(<KnowledgeTreePanel genre="都市" onSelectInstance={onSelect} />);
    await waitFor(() => expect(screen.getAllByTestId("kb-tree-count").length).toBeGreaterThan(0));
    expect(screen.getByTestId("kb-tree-count").textContent).toBe("2");
    fireEvent.click(screen.getByText("其他"));
    await waitFor(() => expect(screen.getAllByTestId("kb-tree-instance").length).toBe(2));
    fireEvent.click(screen.getAllByTestId("kb-tree-instance")[0]);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].id).toBe("i1");
  });

  it("空态：没有知识点给引导文案", async () => {
    api.graphTree.mockResolvedValue({ ok: true, roots: [], rel_edges: [] });
    api.instancesFlat.mockResolvedValue({ ok: true, rows: [] });
    render(<KnowledgeTreePanel genre="都市" />);
    await waitFor(() => expect(screen.getByText(/还没有知识点/)).toBeTruthy());
  });
});
