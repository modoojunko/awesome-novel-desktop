import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ArchiveModal } from "@/components/novel/workbench/modals";
import { RelationsGraphPane } from "@/components/novel/workbench/RelationsGraphPane";

// ---------------------------------------------------------------------------
// 原型审计收尾两项：①归档弹窗收尾计划预览（PRO 五件事 / 免费说明）；
// ②角色关系页签按章投影（本章高亮、来源章与状态列、孤立点）。
// 09-28 起章打开态并入「截至本章」剧情关系边（图为主表达，行清单兜底）；
// 09-29 起卷选中态并入截至本卷末剧情边（c-volume-rels-live，随时对齐本卷最新）。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));

const dossierState = vi.hoisted(() => ({ preview: vi.fn(), get: vi.fn() }));
vi.mock("@/lib/dossierApi", () => ({
  DOSSIER_CHANGED_EVENT: "dossier-relations-changed",
  dossierApi: dossierState,
}));

beforeEach(() => {
  apiState.get.mockReset();
  dossierState.preview.mockReset();
  dossierState.get.mockReset();
});

describe("ArchiveModal 收尾计划预览", () => {
  it("归档收尾全档免费：列出台后两件事与「未确认不参与提示词」说明", () => {
    render(<ArchiveModal open onClose={() => {}} onConfirm={() => {}} isPro />);
    // c-chapter-dossier：收尾收缩为两件提案（tier-plan-four-tiers：全档免费）
    expect(screen.getByText("归档收尾提案")).toBeTruthy();
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
    expect(screen.getByText(/已确认的条目保留不动/)).toBeTruthy();
    expect(screen.getByText(/提案不重跑/)).toBeTruthy();
    expect(screen.getByText(/已确认 3 条将保留/)).toBeTruthy();
    expect(screen.getByText(/其余 2 条由重提替换/)).toBeTruthy();
    // 重归档不重跑收尾：计划预览区不出现
    expect(screen.queryByText("归档收尾（PRO）")).toBeNull();
    expect(screen.queryByText(/提取成功本章才正式归档/)).toBeNull();
  });

  it("免费档：章档全档说明＋重归档警示可出", () => {
    const { rerender } = render(
      <ArchiveModal open onClose={() => {}} onConfirm={() => {}} isPro={false} />,
    );
    // 撤 isPro（tier-plan-four-tiers 5.6）：收尾预览全档同一套（归档 AI 免费）
    expect(screen.getByText(/随归档自动提取，全档可用/)).toBeTruthy();
    expect(screen.getByText("登记伏笔（埋下 / 收束）——产出在「伏笔」页签确认")).toBeTruthy();
    rerender(
      <ArchiveModal
        open
        onClose={() => {}}
        onConfirm={() => {}}
        isPro={false}
        rearchive={{ rows: 5, accepted: 3 }}
      />,
    );
    expect(screen.getByText(/已确认 3 条将保留/)).toBeTruthy();
    expect(screen.getByText(/其余 2 条由重提替换/)).toBeTruthy();
  });
});

const GRAPH = {
  ok: true,
  data: {
    nodes: [
      { id: "c1", name: "林晚", role: "主角" },
      { id: "c2", name: "老聋", role: "反派" },
      { id: "c3", name: "船帮", role: "势力" }, // 词表外（历史数据）→ 按配角默认
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
      { chapter: 1, ref: "vol-1-ch-1", title: "渡口", stale: true, archived: true },
      { chapter: 2, ref: "vol-1-ch-2", title: "雾中城", stale: false, archived: true },
    ],
  },
];

function mockBookApi() {
  apiState.get.mockImplementation(async (p: string) => {
    if (p.endsWith("/characters/graph")) return GRAPH;
    if (p.endsWith("/volumes")) return TREE;
    throw new Error("unexpected " + p);
  });
}

describe("RelationsGraphPane 章态并入剧情关系", () => {
  it("双源上图：往章演变走 preview、本章采纳/待确认走章档端点；同向覆盖开书边", async () => {
    mockBookApi();
    dossierState.preview.mockResolvedValue({
      up_to_ref: "vol-1-ch-2",
      domains: {
        relations: [
          // 往章演变：覆盖开书设定「林晚 → 船帮：敌对」
          { owner: "林晚", other: "船帮", rel_type: "同盟", change_note: "入伙同船", ref: "vol-1-ch-1" },
        ],
      },
      counts: { relations: 1 },
      skipped_stale_refs: [],
    });
    dossierState.get.mockResolvedValue({
      rows: [
        // 本章已采纳：高亮边，覆盖开书设定「老聋 → 林晚：师徒」（与工作流区同源）
        { id: "r2", domain: "relations", status: "accepted", owner: "老聋", other: "林晚",
          rel_type: "决裂", change_note: "翻脸", flags: "", evidence: "", decided_at: "" },
        // 本章待确认：虚线提案边（无角色卡也能上图为占位节点的场景另测）
        { id: "r1", domain: "relations", status: "pending", owner: "船帮", other: "林晚",
          rel_type: "追缉", change_note: "悬赏缉拿", flags: "", evidence: "", decided_at: "" },
      ],
      progress: { pending: 1, accepted: 1, rejected: 0 },
      extraction: null,
      not_extracted: false,
      stale: false,
      archived: true,
      accepted_count: 1,
    });
    const { container } = render(<RelationsGraphPane projectId="p1" chapterRef="vol-1-ch-2" />);

    // 图：4 条边 = 2 开书（林晚→老聋 保留）＋1 往章＋1 本章＋1 待确认（待确认不在清单）
    const rows = await screen.findAllByTestId("rg-row");
    expect(rows).toHaveLength(2);
    // 清单行 1：往章演变（覆盖开书敌对），带极性色签与变更注记、来源章
    expect(rows[0].querySelector(".rg-swatch.friendly")).toBeTruthy();
    expect(rows[0].textContent).toContain("林晚 → 船帮：同盟");
    expect(rows[0].textContent).toContain("（入伙同船）");
    expect(rows[0].textContent).toContain("第 1 章 · 渡口");
    expect(rows[0].textContent).toContain("随剧情演变");
    // 清单行 2：未被覆盖的开书设定边（有来源章 → 来源章＋随剧情演变）
    expect(rows[1].textContent).toContain("林晚 → 老聋：同盟 · 互信");
    expect(rows[1].textContent).toContain("第 2 章 · 雾中城");
    expect(rows[1].textContent).toContain("随剧情演变");
    // 来源=本章的开书边在清单里也高亮＋「· 本章」标注（#405 口径，评审 P2 修复）
    expect(rows[1].className).toContain("hit");
    expect(rows[1].textContent).toContain("· 本章");
    // 被覆盖的开书边不上图：老聋→林晚（师徒）与 林晚→船帮（敌对）消失
    expect(screen.queryByText(/师徒/)).toBeNull();
    // SVG：本章高亮 2 条（剧情采纳边＋来源=本章的开书边）；待确认虚线恰 1 条
    expect(document.querySelectorAll('[data-hit="1"]')).toHaveLength(2);
    expect(document.querySelectorAll(".rg-edge.pending .rg-line")).toHaveLength(1);
    expect(document.querySelector(".rg-edge.pending text")?.textContent).toContain("追缉 · 待确认");
    // 极性着色：同盟/友绿、决裂/追缉红；箭头 marker 同极性且真实挂到路径上
    expect(document.querySelectorAll(".rg-edge.p-friendly .rg-line")).toHaveLength(2);
    expect(document.querySelectorAll(".rg-edge.p-hostile .rg-line")).toHaveLength(2);
    const hostileLine = document.querySelector(".rg-edge.p-hostile .rg-line");
    expect(hostileLine?.getAttribute("marker-end")).toContain("hostile");
    expect(container.querySelectorAll(".rg-arrow.friendly, .rg-arrow.hostile, .rg-arrow.neutral")).toHaveLength(3);
    // 节点按角色类型着色：主角实心品牌色、反派红软底、词表外回落配角、图例四色键
    expect(container.querySelectorAll(".rg-node.role-protagonist")).toHaveLength(1);
    expect(container.querySelectorAll(".rg-node.role-villain")).toHaveLength(1);
    expect(container.querySelectorAll(".rg-node.role-support")).toHaveLength(1);
    expect(container.querySelectorAll(".rg-dot.protagonist, .rg-dot.villain, .rg-dot.support, .rg-dot.extra")).toHaveLength(4);
    // 图例：3 卡＋0 占位 · 4 条边（剧情演变 2 · 待确认 1）
    expect(screen.getByText(/3 个角色 · 4 条关系（剧情演变 2 · 待确认 1）/)).toBeTruthy();
    expect(screen.queryByText(/还没连线/)).toBeNull();
  });

  it("画布缩放：默认整图适配，按钮缩放/复位改变 viewBox", async () => {
    mockBookApi();
    dossierState.preview.mockResolvedValue({
      up_to_ref: "vol-1-ch-1",
      domains: { relations: [] },
      counts: { relations: 0 },
      skipped_stale_refs: [],
    });
    dossierState.get.mockResolvedValue({
      rows: [],
      progress: { pending: 0, accepted: 0, rejected: 0 },
      extraction: null,
      not_extracted: false,
      stale: false,
      archived: false,
      accepted_count: 0,
    });
    render(<RelationsGraphPane projectId="p1" volumeScope={1} />);
    const svg = await screen.findByRole("img", { name: "角色关系图（截至第 1 卷末剧情投影）" });
    // 默认＝整图适配（viewBox 全见）
    expect(svg.getAttribute("viewBox")).toBe("0 0 560 380");
    fireEvent.click(screen.getByTestId("rg-zoom-in"));
    const vb = (svg.getAttribute("viewBox") ?? "").split(" ").map(Number);
    expect(vb[2]).toBeLessThan(560);
    expect(vb[3]).toBeCloseTo(vb[2] * (380 / 560), 5);
    // 缩放下限＝整图适配：一路缩小自动对齐回全图
    fireEvent.click(screen.getByTestId("rg-zoom-out"));
    expect(svg.getAttribute("viewBox")).toBe("0 0 560 380");
    // 复位按钮
    fireEvent.click(screen.getByTestId("rg-zoom-in"));
    fireEvent.click(screen.getByTestId("rg-zoom-reset"));
    expect(svg.getAttribute("viewBox")).toBe("0 0 560 380");
  });

  it("缩放按钮不被拖拽捕获吞掉点击（真机实锤：pointer capture 重定向 pointerup）", async () => {
    mockBookApi();
    dossierState.preview.mockResolvedValue({
      up_to_ref: "vol-1-ch-1",
      domains: { relations: [] },
      counts: { relations: 0 },
      skipped_stale_refs: [],
    });
    dossierState.get.mockResolvedValue({
      rows: [],
      progress: { pending: 0, accepted: 0, rejected: 0 },
      extraction: null,
      not_extracted: false,
      stale: false,
      archived: false,
      accepted_count: 0,
    });
    const { container } = render(<RelationsGraphPane projectId="p1" volumeScope={1} />);
    const svg = await screen.findByRole("img", { name: "角色关系图（截至第 1 卷末剧情投影）" });
    expect(svg.getAttribute("viewBox")).toBe("0 0 560 380");
    const vp = container.querySelector(".rg-viewport")!;
    const btn = screen.getByTestId("rg-zoom-in");
    // 真实浏览器序列：pointerdown 落在按钮上（冒泡进容器）→ 不得开启拖拽态
    fireEvent.pointerDown(btn, { button: 0 });
    expect(vp.className).not.toContain("dragging");
    // click 后 viewBox 变化
    fireEvent.click(btn);
    expect(svg.getAttribute("viewBox")).not.toBe("0 0 560 380");
  });

  it("未归档章的已采纳行也上图；preview 的本章行不重复", async () => {
    mockBookApi();
    // 本章未归档：preview 理应不含本章行；即便含（曾归档后回草稿）也按 ref 过滤防重复
    dossierState.preview.mockResolvedValue({
      up_to_ref: "vol-1-ch-1",
      domains: {
        relations: [
          { owner: "老聋", other: "林晚", rel_type: "敌对", change_note: "举枪相向", ref: "vol-1-ch-1" },
        ],
      },
      counts: { relations: 1 },
      skipped_stale_refs: [],
    });
    dossierState.get.mockResolvedValue({
      rows: [
        { id: "d1", domain: "relations", status: "accepted", owner: "老聋", other: "林晚",
          rel_type: "决裂", change_note: "举枪相向", flags: "", evidence: "", decided_at: "" },
      ],
      progress: { pending: 0, accepted: 1, rejected: 0 },
      extraction: null,
      not_extracted: false,
      stale: false,
      archived: false,
      accepted_count: 1,
    });
    render(<RelationsGraphPane projectId="p1" chapterRef="vol-1-ch-1" />);
    // 恰 1 条本章高亮边（章档端点承载，preview 同向行被 ref 过滤不重复），决裂＝红
    await screen.findByText(/3 个角色 · 3 条关系（剧情演变 1 · 待确认 0）/);
    expect(document.querySelectorAll(".rg-edge.hit .rg-line")).toHaveLength(1);
    // 本章 hit 边（决裂）为敌对红；开书边 林晚→船帮 敌对 也计入极性红，故 hit∧hostile 恰 1
    expect(document.querySelectorAll(".rg-edge.hit.p-hostile .rg-line")).toHaveLength(1);
    expect(document.querySelectorAll(".rg-edge.pending")).toHaveLength(0);
    // 本章采纳边覆盖开书设定「老聋 → 林晚：师徒」
    expect(screen.queryByText(/师徒/)).toBeNull();
  });

  it("未登记名给虚线占位节点，关系照常上图", async () => {
    mockBookApi();
    dossierState.preview.mockResolvedValue({
      up_to_ref: "vol-1-ch-2",
      domains: { relations: [] },
      counts: { relations: 0 },
      skipped_stale_refs: [],
    });
    dossierState.get.mockResolvedValue({
      rows: [
        { id: "r2", domain: "relations", status: "pending", owner: "黑市商人", other: "林晚",
          rel_type: "交易", change_note: "银器换情报", flags: "unregistered", evidence: "", decided_at: "" },
      ],
      progress: { pending: 1, accepted: 0, rejected: 0 },
      extraction: null,
      not_extracted: false,
      stale: false,
      archived: true,
      accepted_count: 0,
    });
    const { container } = render(<RelationsGraphPane projectId="p1" chapterRef="vol-1-ch-2" />);
    // 4 节点＝3 卡＋1 占位；4 边＝3 开书＋1 待确认提案
    await screen.findByText(/4 个角色 · 4 条关系（剧情演变 0 · 待确认 1）/);
    // 占位节点：虚线圈＋未登记名
    const ghost = container.querySelector(".rg-node.ghost");
    expect(ghost).toBeTruthy();
    expect(ghost?.textContent).toContain("黑市商人");
    expect(document.querySelectorAll(".rg-edge.pending .rg-line")).toHaveLength(1);
    // 占位节点有边 → 不进「还没连线」
    expect(screen.queryByText(/还没连线/)).toBeNull();
  });

  it("preview/章行拉取失败静默：退回开书设定边，孤立点照常提示", async () => {
    mockBookApi();
    dossierState.preview.mockRejectedValue(new Error("preview down"));
    dossierState.get.mockRejectedValue(new Error("dossier down"));
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/characters/graph"))
        return {
          ok: true,
          data: { nodes: [...GRAPH.data.nodes, { id: "c9", name: "独行客", role: "路人" }], edges: GRAPH.data.edges },
        };
      if (p.endsWith("/volumes")) return TREE;
      throw new Error("unexpected " + p);
    });
    render(<RelationsGraphPane projectId="p1" chapterRef="vol-1-ch-2" />);
    const rows = await screen.findAllByTestId("rg-row");
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain("第 2 章 · 雾中城");
    expect(rows[1].textContent).toContain("基于旧设定");
    expect(rows[2].textContent).toContain("开书设定");
    // 剧情边缺席，但来源=本章的开书边仍沿 #405 口径高亮；无虚线
    expect(document.querySelectorAll('[data-hit="1"]')).toHaveLength(1);
    expect(document.querySelectorAll(".rg-edge.pending")).toHaveLength(0);
    expect(screen.getByText(/还没连线：独行客/)).toBeTruthy();
    // 路人＝虚线圈
    expect(document.querySelectorAll(".rg-node.role-extra")).toHaveLength(1);
  });

  it("卷选中态并入剧情边：preview 截至本卷末章，同向覆盖开书边，跨卷来源剔除", async () => {
    mockBookApi();
    dossierState.preview.mockImplementation(async (_p: string, upTo: string) => {
      // 折叠截至本卷末章（写章消费单源口径）
      expect(upTo).toBe("vol-1-ch-2");
      return {
        up_to_ref: upTo,
        domains: {
          relations: [
            { owner: "林晚", other: "船帮", rel_type: "同盟", change_note: "入伙同船", ref: "vol-1-ch-1" },
            // 跨卷来源（第 2 卷）→ 卷投影过滤剔除
            { owner: "老聋", other: "船帮", rel_type: "交易", change_note: "", ref: "vol-2-ch-1" },
          ],
        },
        counts: { relations: 2 },
        skipped_stale_refs: [],
      };
    });
    dossierState.get.mockResolvedValue({
      rows: [],
      progress: { pending: 0, accepted: 0, rejected: 0 },
      extraction: null,
      not_extracted: false,
      stale: false,
      archived: true,
      accepted_count: 0,
    });
    render(<RelationsGraphPane projectId="p1" volumeScope={1} />);
    const rows = await screen.findAllByTestId("rg-row");
    // 3 条清单＝剧情边 1（覆盖开书「林晚→船帮：敌对」）＋未覆盖开书边 2；跨卷剧情边不进投影
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain("林晚 → 船帮：同盟");
    expect(rows[0].textContent).toContain("第 1 章 · 渡口");
    expect(screen.queryByText(/交易/)).toBeNull();
    // 图例：截至本卷末投影＋剧情演变条数；无待确认（卷态不显示提案）
    expect(screen.getByText(/3 个角色 · 3 条关系（含剧情演变 1 条）/)).toBeTruthy();
    expect(screen.getByText(/截至第 1 卷末（只读投影）/)).toBeTruthy();
    expect(document.querySelectorAll(".rg-edge.pending")).toHaveLength(0);
  });

  it("卷态未归档章的已采纳行并入投影（随时对齐最新），待确认不上图", async () => {
    // 第 2 章归档后回草稿（未归档）：其已采纳关系行仍属已确认剧情事实
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/characters/graph")) return GRAPH;
      if (p.endsWith("/volumes")) {
        return [
          {
            name: "vol-1",
            chapters: [
              { chapter: 1, ref: "vol-1-ch-1", title: "渡口", stale: false, archived: true },
              { chapter: 2, ref: "vol-1-ch-2", title: "雾中城", stale: false, archived: false },
            ],
          },
        ];
      }
      throw new Error("unexpected " + p);
    });
    dossierState.preview.mockResolvedValue({
      up_to_ref: "vol-1-ch-2",
      domains: { relations: [] },
      counts: { relations: 0 },
      skipped_stale_refs: [],
    });
    dossierState.get.mockImplementation(async (_p: string, ref: string) => {
      // 只逐章拉未归档章
      expect(ref).toBe("vol-1-ch-2");
      return {
        rows: [
          { id: "d1", domain: "relations", status: "accepted", owner: "老聋", other: "林晚",
            rel_type: "决裂", change_note: "翻脸", flags: "", evidence: "", decided_at: "" },
          { id: "d2", domain: "relations", status: "pending", owner: "船帮", other: "林晚",
            rel_type: "追缉", change_note: "悬赏缉拿", flags: "", evidence: "", decided_at: "" },
        ],
        progress: { pending: 1, accepted: 1, rejected: 0 },
        extraction: null,
        not_extracted: false,
        stale: false,
        archived: false,
        accepted_count: 1,
      };
    });
    render(<RelationsGraphPane projectId="p1" volumeScope={1} />);
    const rows = await screen.findAllByTestId("rg-row");
    // 剧情边 1（决裂，覆盖开书「老聋→林晚：师徒」）＋未覆盖开书边 2；待确认提案不进投影
    expect(rows).toHaveLength(3);
    expect(rows[0].textContent).toContain("老聋 → 林晚：决裂");
    expect(rows[0].textContent).toContain("第 2 章 · 雾中城");
    expect(screen.queryByText(/追缉/)).toBeNull();
    expect(document.querySelectorAll(".rg-edge.pending")).toHaveLength(0);
    expect(screen.getByText(/含剧情演变 1 条/)).toBeTruthy();
  });

  it("卷态加载门控：剧情边就位前呈加载态，投影失败静默退回开书设定边", async () => {
    mockBookApi();
    let resolvePreview: (v: unknown) => void = () => {};
    dossierState.preview.mockReturnValue(
      new Promise((res) => {
        resolvePreview = res;
      }),
    );
    const view = render(<RelationsGraphPane projectId="p1" volumeScope={1} />);
    // 卷树/剧情边未就位 → 加载态（不闪开书设定半成品图）
    expect(screen.getByText("加载中……")).toBeTruthy();
    resolvePreview({
      up_to_ref: "vol-1-ch-2",
      domains: { relations: [] },
      counts: { relations: 0 },
      skipped_stale_refs: [],
    });
    await screen.findByRole("img", { name: "角色关系图（截至第 1 卷末剧情投影）" });
    expect(screen.getAllByTestId("rg-row")).toHaveLength(3);
    view.unmount();
    // 再挂载投影挂掉：静默退回开书设定边，图例无剧情演变计数
    dossierState.preview.mockRejectedValue(new Error("preview down"));
    render(<RelationsGraphPane projectId="p1" volumeScope={1} />);
    const rows = await screen.findAllByTestId("rg-row");
    expect(rows).toHaveLength(3);
    expect(
      rows.every((r) =>
        ["开书设定", "随剧情演变", "基于旧设定"].some((s) => r.textContent!.includes(s)),
      ),
    ).toBe(true);
    expect(screen.queryByText(/含剧情演变/)).toBeNull();
  });
});
