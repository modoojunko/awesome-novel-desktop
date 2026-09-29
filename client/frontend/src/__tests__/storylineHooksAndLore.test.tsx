import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { HooksPane } from "@/components/novel/workbench/HooksPane";
import { SettingsChangelogPane } from "@/components/novel/workbench/SettingsChangelogPane";
import HooksSettingForm from "@/components/novel/settings/HooksSettingForm";

// ---------------------------------------------------------------------------
// A 组（storyline 补齐）：章内伏笔台账投影（本章高亮）＋设定页「截至本章」
// 投影并入书级设定条目（world history/factions/extra，origin=章 ref 过滤）。
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/lib/api", () => ({ api: apiState }));

const TREE = [
  {
    name: "vol-1",
    ref: "vol-1",
    chapters: [
      { id: "c1", chapter: 1, ref: "vol-1-ch-1", title: "第一章", status: "archived" },
      { id: "c2", chapter: 2, ref: "vol-1-ch-2", title: "风起渡口", status: "outline" },
    ],
  },
];

const HOOKS = {
  data: {
    count: 3,
    items: [
      {
        id: "h1",
        code: "#H-0001",
        description: "谁在暗中跟着她",
        type: "mystery",
        priority: 1,
        status: "active",
        introduced_chapter_id: "c2",
        planned_chapter_id: null,
        resolved_chapter_id: null,
      },
      {
        id: "h2",
        code: "#H-0002",
        description: "旧航图的缺口",
        type: "clue",
        priority: 2,
        status: "resolved",
        introduced_chapter_id: "c1",
        planned_chapter_id: null,
        resolved_chapter_id: "c2",
      },
      {
        id: "h3",
        code: "#H-0003",
        description: "船徽来历",
        type: "relationship",
        priority: 3,
        status: "active",
        introduced_chapter_id: "c1",
        planned_chapter_id: null,
        resolved_chapter_id: null,
      },
    ],
  },
};

beforeEach(() => {
  apiState.get.mockReset();
});

describe("HooksPane（章内伏笔台账投影）", () => {
  it("台账行序/埋点章/悬置与已收状态；本章埋下与回收条目高亮", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/hooks")) return HOOKS;
      if (p.endsWith("/volumes")) return TREE;
      throw new Error("unexpected " + p);
    });
    render(<HooksPane projectId="p1" chapterRef="vol-1-ch-2" />);
    expect(await screen.findByText("谁在暗中跟着她")).toBeTruthy();
    // 汇总：3 条 · 2 悬置 · 本章埋下 1 · 本章回收 1
    const sum = document.querySelector(".hp-sum")?.textContent ?? "";
    expect(sum).toContain("3");
    expect(sum).toContain("2");
    expect(sum).toContain("本章埋下");
    expect(sum).toContain("本章回收");
    // 第 1 章埋的条目标「悬置」与「已收 · 第 2 章」；本章（第 2 章）埋/收的条目高亮
    const hitRows = document.querySelectorAll(".hp-row.hit");
    expect(hitRows.length).toBe(2);
    expect(screen.getByText("已收 · 第 2 章")).toBeTruthy();
    // 埋点章展示（第 1 章 · 第一章；h2/h3 两条都埋在第 1 章）
    expect(screen.getAllByText(/埋于 第 1 章 · 第一章/).length).toBe(2);
  });

  it("废弃条目不进投影：汇总计数与台账行都不含已弃（c-hooks-abandoned-hidden）", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/hooks"))
        return {
          data: {
            count: 3,
            items: [
              ...HOOKS.data.items,
              {
                id: "h9",
                code: "#H-0009",
                description: "已废弃的重复变体",
                type: "mystery",
                priority: 2,
                status: "abandoned",
                introduced_chapter_id: "c2",
                planned_chapter_id: null,
                resolved_chapter_id: null,
              },
            ],
          },
        };
      if (p.endsWith("/volumes")) return TREE;
      throw new Error("unexpected " + p);
    });
    render(<HooksPane projectId="p1" chapterRef="vol-1-ch-2" />);
    (await screen.findAllByText("谁在暗中跟着她"))[0];
    // 汇总仍是 3 条（非 4）；无「已弃」行、无废弃描述
    const sum = document.querySelector(".hp-sum")?.textContent ?? "";
    expect(sum).toContain("3");
    expect(screen.queryByText("已弃")).toBeNull();
    expect(screen.queryByText("已废弃的重复变体")).toBeNull();
  });

  it("投影行推进与该收了（c-hooks-advance-ledger）：mentioned 晚于埋点显示、planned ≤ 当前章标注", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/hooks"))
        return {
          data: {
            count: 1,
            items: [
              {
                id: "h5",
                code: "#H-0005",
                description: "西仓巷的新委托",
                type: "clue",
                priority: 2,
                status: "active",
                introduced_chapter_id: "c1",
                mentioned_chapter_id: "c2", // 推进于第 2 章（≠埋点 → 显示）
                planned_chapter_id: "c1", // 计划收第 1 章 ≤ 当前章 2 → 该收了
                resolved_chapter_id: null,
              },
            ],
          },
        };
      if (p.endsWith("/volumes")) return TREE;
      throw new Error("unexpected " + p);
    });
    render(<HooksPane projectId="p1" chapterRef="vol-1-ch-2" />);
    const origin = await screen.findByText(/埋于 第 1 章 · 第一章/);
    expect(origin.textContent).toContain("最近推进 第 2 章");
    expect(origin.textContent).toContain("计划收 第 1 章");
    expect(document.querySelector(".hp-due")?.textContent).toBe("该收了");
  });
});

describe("HooksSettingForm 废弃组默认隐藏（c-hooks-abandoned-hidden）", () => {
  const PROPS = {
    projectId: "p1",
    onPanelState: () => {},
    onSaveStateChange: () => {},
  } as any;

  function mockFormApi() {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/hooks"))
        return {
          data: {
            count: 3,
            items: [
              ...HOOKS.data.items,
              {
                id: "h9",
                code: "#H-0009",
                description: "已废弃的重复变体",
                type: "mystery",
                priority: 2,
                status: "abandoned",
                introduced_chapter_id: "c1",
                planned_chapter_id: null,
                resolved_chapter_id: null,
              },
            ],
          },
        };
      if (p.endsWith("/volumes")) return TREE;
      throw new Error("unexpected " + p);
    });
  }

  it("默认不渲染废弃组与废弃条目；点「显示已废弃」后出现", async () => {
    mockFormApi();
    render(<HooksSettingForm {...PROPS} />);
    (await screen.findAllByText("谁在暗中跟着她"))[0];
    // 默认：活跃组在、废弃描述不在、开关文案带计数
    expect(screen.queryByText("已废弃的重复变体")).toBeNull();
    // 组头无「废弃」分组（卡上三态切换器仍含废弃选项，属卡片功能不在此断言）
    expect(document.querySelector(".hk-group")?.textContent ?? "").not.toContain("废弃");
    const toggle = screen.getByTestId("toggle-abandoned");
    expect(toggle.textContent).toContain("显示已废弃（1）");
    // 点开：废弃组＋条目出现
    fireEvent.click(toggle);
    expect(await screen.findByText("已废弃的重复变体")).toBeTruthy();
    expect(
      [...document.querySelectorAll(".hk-group")].some((g) => g.textContent?.includes("废弃")),
    ).toBe(true);
    expect(screen.getByTestId("toggle-abandoned").textContent).toContain("隐藏已废弃");
  });

  it("无废弃条目时不出开关", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.endsWith("/hooks")) return HOOKS;
      if (p.endsWith("/volumes")) return TREE;
      throw new Error("unexpected " + p);
    });
    render(<HooksSettingForm {...PROPS} />);
    (await screen.findAllByText("谁在暗中跟着她"))[0];
    expect(screen.queryByTestId("toggle-abandoned")).toBeNull();
  });
});

describe("SettingsChangelogPane 截至本章投影", () => {
  it("书级设定条目按 origin 章序过滤（未来章条目排除、开书条目保留）", async () => {
    apiState.get.mockImplementation(async (p: string) => {
      if (p.includes("/chapters/vol-1-ch-1")) {
        return {
          outline: {
            characters: ["林晚"],
            character_states: [{ name: "林晚", state_change: "决定不再等船" }],
          },
        };
      }
      if (p.endsWith("/characters")) return [{ id: "ch1", name: "林晚" }];
      if (p.endsWith("/characters/relations")) return [];
      if (p.endsWith("/volumes")) return TREE;
      if (p.endsWith("/settings/world")) {
        return {
          history: [
            { key: "旧案", value: "十五年前的信", origin: "" }, // 开书
            { key: "渡口", value: "新渡口落成", origin: "vol-1-ch-1" },
            { key: "后事", value: "第 3 章伏笔", origin: "vol-1-ch-3" }, // 未来章 → 排除
          ],
          factions: [{ name: "船帮", note: "临江势力", origin: "vol-1-ch-1" }],
          extra: [],
        };
      }
      throw new Error("unexpected " + p);
    });
    render(<SettingsChangelogPane projectId="p1" chapterRef="vol-1-ch-1" />);
    expect(await screen.findByText("决定不再等船")).toBeTruthy();
    // 出场角色名字上屏（characters=string[] 契约）
    expect(screen.getByText("林晚")).toBeTruthy();
    // 设定条目组：开书 + 第 1 章条目显示，第 3 章条目排除
    expect(screen.getByText("旧案")).toBeTruthy();
    expect(screen.getByText("渡口")).toBeTruthy();
    expect(screen.getByText("船帮")).toBeTruthy();
    expect(screen.queryByText("后事")).toBeNull();
    expect(screen.getByText("开书")).toBeTruthy();
  });
});
