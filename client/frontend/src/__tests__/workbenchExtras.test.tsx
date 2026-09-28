import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ArchiveModal } from "@/components/novel/workbench/modals";
import { RelationsGraphPane } from "@/components/novel/workbench/RelationsGraphPane";

// ---------------------------------------------------------------------------
// 原型审计收尾两项：①归档弹窗收尾计划预览（PRO 五件事 / 免费说明）；
// ②角色关系页签按章投影（本章高亮、来源章与状态列、孤立点）。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));

beforeEach(() => {
  apiState.get.mockReset();
});

describe("ArchiveModal 收尾计划预览", () => {
  it("PRO：列出台后五件事与「未确认不参与提示词」说明", () => {
    render(<ArchiveModal open onClose={() => {}} onConfirm={() => {}} isPro />);
    // c-chapter-dossier：收尾收缩为两件 PRO 提案；三件已升级章档（全档）
    expect(screen.getByText("归档收尾（PRO）")).toBeTruthy();
    // c-ops-tab-progress-only：收尾两件各归各的页签（伏笔/设定）
    for (const t of [
      "登记伏笔（埋下 / 收束）——产出在「伏笔」页签确认",
      "识别世界要素——产出在「设定」页签确认",
    ]) {
      expect(screen.getByText(t)).toBeTruthy();
    }
    expect(screen.getByText(/点过确认才写进全书设定/)).toBeTruthy();
    expect(screen.getByText(/随归档自动提取，全档可用/)).toBeTruthy();
    expect(screen.getByText(/AI 提取本章变化/)).toBeTruthy();
    expect(screen.getByText(/提取成功本章才正式归档/)).toBeTruthy();
  });

  it("重归档变体：清空重提文案＋收尾计划区不出现", () => {
    render(
      <ArchiveModal
        open
        onClose={() => {}}
        onConfirm={() => {}}
        isPro
        rearchiveMode
        rearchive={{ rows: 5, accepted: 3 }}
      />,
    );
    // 标题与确认按钮同为「重新归档」
    expect(screen.getAllByText("重新归档").length).toBe(2);
    expect(screen.getByText(/清空并以当前正文重提/)).toBeTruthy();
    expect(screen.getByText(/提案不重跑/)).toBeTruthy();
    expect(screen.getByText(/覆盖现有变化 5 条/)).toBeTruthy();
    expect(screen.getByText(/含已采纳 3 条/)).toBeTruthy();
    // 重归档不重跑收尾：计划预览区不出现
    expect(screen.queryByText("归档收尾（PRO）")).toBeNull();
    expect(screen.queryByText(/提取成功本章才正式归档/)).toBeNull();
  });

  it("免费档：章档全档说明＋重归档警示可出", () => {
    const { rerender } = render(
      <ArchiveModal open onClose={() => {}} onConfirm={() => {}} isPro={false} />,
    );
    expect(screen.getByText(/本章变化提取全档可用/)).toBeTruthy();
    expect(screen.getByText(/伏笔登记与世界要素提案为 PRO 能力/)).toBeTruthy();
    rerender(
      <ArchiveModal
        open
        onClose={() => {}}
        onConfirm={() => {}}
        isPro={false}
        rearchive={{ rows: 5, accepted: 3 }}
      />,
    );
    expect(screen.getByText(/覆盖现有变化 5 条/)).toBeTruthy();
    expect(screen.getByText(/含已采纳 3 条/)).toBeTruthy();
  });
});

const GRAPH = {
  ok: true,
  data: {
    nodes: [
      { id: "c1", name: "林晚", role: "主角" },
      { id: "c2", name: "老聋", role: "配角" },
      { id: "c3", name: "船帮", role: "势力" },
    ],
    edges: [
      { owner_id: "c1", other_id: "c2", owner_name: "林晚", other_name: "老聋",
        rel_type: "同盟", stance: "互信", origin_chapter: "vol-1-ch-2" },
      { owner_id: "c2", other_id: "c1", owner_name: "老聋", other_name: "林晚",
        rel_type: "师徒", stance: "照拂", origin_chapter: "vol-1-ch-1" },
      { owner_id: "c1", other_id: "c3", owner_name: "林晚", other_name: "船帮",
        rel_type: "敌对", stance: "", origin_chapter: "" },
    ],
  },
};

const TREE = [
  {
    name: "vol-1",
    chapters: [
      { chapter: 1, ref: "vol-1-ch-1", title: "渡口", stale: true },
      { chapter: 2, ref: "vol-1-ch-2", title: "雾中城", stale: false },
    ],
  },
];

describe("RelationsGraphPane 按章投影", () => {
  it("本章边高亮＋状态列（开书/随剧情/基于旧设定）＋孤立点", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/characters/graph")) return GRAPH;
      if (p.endsWith("/volumes")) return TREE;
      throw new Error("unexpected " + p);
    });
    render(<RelationsGraphPane projectId="p1" chapterRef="vol-1-ch-2" />);
    const rows = await screen.findAllByTestId("rg-row");
    expect(rows).toHaveLength(3);
    // 第 1 行：本章（vol-1-ch-2）关系 → hit + 标注「本章」
    expect(rows[0].className).toContain("hit");
    expect(rows[0].textContent).toContain("第 2 章 · 雾中城");
    expect(rows[0].textContent).toContain("· 本章");
    expect(rows[0].textContent).toContain("随剧情演变");
    // 第 2 行：来源第 1 章且该章 stale → 基于旧设定
    expect(rows[1].textContent).toContain("第 1 章 · 渡口");
    expect(rows[1].textContent).toContain("基于旧设定");
    // 第 3 行：无来源 → 开书设定
    expect(rows[2].textContent).toContain("开书设定");
    // SVG 高亮线仅本章边
    expect(document.querySelectorAll('[data-hit="1"]')).toHaveLength(1);
    // 孤立点（船帮有边，无孤立 → 不显示；补一个无边节点场景另测）
    expect(screen.queryByText(/还没连线/)).toBeNull();
  });

  it("孤立节点提示「还没连线」", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/characters/graph"))
        return {
          ok: true,
          data: { nodes: [...GRAPH.data.nodes, { id: "c9", name: "独行客", role: "龙套" }], edges: GRAPH.data.edges },
        };
      if (p.endsWith("/volumes")) return TREE;
      throw new Error("unexpected " + p);
    });
    render(<RelationsGraphPane projectId="p1" chapterRef="vol-1-ch-2" />);
    expect(await screen.findByText(/还没连线：独行客/)).toBeTruthy();
  });
});
