// 知识库页详情抽屉通用「字段」段测试（c-kb-entry-detail-fields）：规格原文
// 「条目详情抽屉：字段、正反例、证据只读」实现补课——payload 概念无关平铺。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { RedirectToKbCharView } from "@/App";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const libApi = vi.hoisted(() => ({
  listLibrary: vi.fn(),
}));

vi.mock("@/lib/libraryApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/libraryApi")>();
  return { ...actual, listLibrary: libApi.listLibrary };
});

const api = vi.hoisted(() => ({
  entries: vi.fn(),
  libraries: vi.fn(),
  genres: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return { ...actual, kbApi: { ...actual.kbApi, entries: api.entries, libraries: api.libraries, genres: api.genres } };
});

import KnowledgeBasePage, { payloadRows } from "@/pages/KnowledgeBasePage";
import type { KbEntry } from "@/lib/kbApi";

// c-charlib-into-kb：页组件引入 useSearchParams/useCharacterLibrary 后，
// 渲染必须挂 Router＋QueryClient 上下文（既有裸渲染统一走这里）。
function renderPage(ui: React.ReactElement = <KnowledgeBasePage />, opts: { route?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[opts.route ?? "/"]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}


const ENTRY: KbEntry = {
  id: "kbentry-0001",
  genre: "悬疑",
  concept: "角色设定",
  concept_id: "悬疑:角色设定",
  title: "刘望津",
  instruction: "漂亮热情的农村出身姑娘，能识怪字、有阴阳眼。",
  definition: "角色设定条目的一般性定义：造角色的方法。",
  when_text: "新角色出场前；人物关系翻转时",
  version: 1,
  origin: "manual",
  archived_at: null,
  payload: {
    archetype: "刘望津",
    persona: "漂亮热情的农村出身姑娘。",
    aliases: ["小刘", "津津"],
    gender: "女",
    age: "44",
    plot: "与李耀相亲；识怪字；出车祸丢魂昏迷。",
    empty_key: "",
    blank_arr: [],
    custom_note: "字段字典未收录的键",
  },
  example: "",
  negative_example: "",
  when: {},
  evidence: "第9章",
  rev: 1,
  src_kind: "character_library_migration",
  src_novel_name: "怪字书",
  created_at: "2026-11-02T00:00:00",
  updated_at: "2026-11-02T00:00:00",
};

beforeEach(() => {
  libApi.listLibrary.mockResolvedValue({ count: 0, items: [] });
  api.entries.mockResolvedValue({ entries: [ENTRY], next_cursor: "" });
  api.libraries.mockResolvedValue([]);
  api.genres.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("payloadRows（通用载荷平铺）", () => {
  it("字符串按存储序平铺、空值跳过、数组顿号连", () => {
    const rows = payloadRows(ENTRY.payload);
    expect(rows.map(([k]) => k)).toEqual([
      "archetype", "persona", "aliases", "gender", "age", "plot", "custom_note",
    ]);
    expect(rows[2]).toEqual(["aliases", "小刘、津津"]);
  });

  it("null/缺格跳过、对象走紧凑 JSON、数字转串", () => {
    const rows = payloadRows({
      n: null as unknown as string,
      obj: { a: 1 },
      num: 42,
      arrObj: [{ x: 1 }],
      emptyArr: [],
      emptyStr: "",
    });
    expect(rows).toEqual([
      ["obj", '{"a":1}'],
      ["num", "42"],
      ["arrObj", '{"x":1}'], // 单元素数组 join 无分隔符
    ]);
  });
});

describe("KnowledgeBasePage 详情抽屉", () => {
  it("点开条目：字段以中文标签逐格渲染（迁移卡属性全可见）", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("刘望津")).toBeTruthy());
    fireEvent.click(screen.getByText("刘望津"));
    await waitFor(() => expect(screen.getByText("字段")).toBeTruthy());
    // 中文标签（通用字典），不露英文字段名
    expect(screen.getByText("性别")).toBeTruthy();
    expect(screen.getByText("名字")).toBeTruthy();
    expect(screen.getByText("一句话人设")).toBeTruthy();
    expect(screen.getByText("别名")).toBeTruthy();
    expect(screen.getByText("年龄")).toBeTruthy();
    expect(screen.getByText("剧情定位")).toBeTruthy();
    expect(screen.queryByText("gender")).toBeNull();
    expect(screen.queryByText("archetype")).toBeNull();
    // 值：标量与数组顿号连
    expect(screen.getByText("女")).toBeTruthy();
    expect(screen.getByText("小刘、津津")).toBeTruthy();
    expect(screen.getByText("与李耀相亲；识怪字；出车祸丢魂昏迷。")).toBeTruthy();
    // 空值键不出行；字典未收录的键回退原键（不编造中文）
    expect(screen.queryByText("empty_key")).toBeNull();
    expect(screen.queryByText("blank_arr")).toBeNull();
    expect(screen.getByText("custom_note")).toBeTruthy();
    expect(screen.getByText("字段字典未收录的键")).toBeTruthy();
    // 其余四段照旧；证据＝章锚、小说名住「源自小说」专行
    expect(screen.getByText("知识定义")).toBeTruthy();
    expect(screen.getByText(/分类：类别/)).toBeTruthy();
    expect(screen.getAllByText(/实例/).length).toBeGreaterThan(0);
    expect(screen.getByText("证据")).toBeTruthy();
    expect(screen.getByText("第9章")).toBeTruthy();
    expect(screen.getByText("源自小说")).toBeTruthy();
    expect(screen.getByText("怪字书")).toBeTruthy();
  });

  it("指令与一句话人设相同时去重，人设本身照常显示", async () => {
    api.entries.mockResolvedValue({
      entries: [{ ...ENTRY, instruction: String(ENTRY.payload.persona) }],
      next_cursor: "",
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("刘望津")).toBeTruthy());
    fireEvent.click(screen.getByText("刘望津"));
    await waitFor(() => expect(screen.getByText("字段")).toBeTruthy());
    expect(screen.queryByText("指令")).toBeNull();
    expect(screen.getByText("一句话人设")).toBeTruthy();
    // 列表卡片同渲染该句 → 多命中按存在性断言
    expect(screen.getAllByText("漂亮热情的农村出身姑娘。").length).toBeGreaterThan(0);
  });

  it("关闭抽屉后字段段退场", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("刘望津")).toBeTruthy());
    fireEvent.click(screen.getByText("刘望津"));
    await waitFor(() => expect(screen.getByText("字段")).toBeTruthy());
    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByText("字段")).toBeNull());
  });
});

describe("角色设定视角（c-charlib-into-kb）", () => {
  it("?concept=角色设定 深链落位：档案柜视图体在位，通用列表退位", async () => {
    renderPage(<KnowledgeBasePage />, { route: "/tools/kb?concept=角色设定" });
    await waitFor(() => expect(screen.getByTestId("char-instance-view")).toBeTruthy());
    // 通用列表退位：条数行不出现（entries 有 1 条，若未退位会渲染「1 条」）
    expect(screen.queryByText("1 条")).toBeNull();
    // 库分组与通用搜索退位
    expect(screen.queryByTestId("kb-baseline-sync")).toBeNull();
  });

  it("来源切「官方精选」→ 通用列表回位（仍带角色设定概念过滤）", async () => {
    renderPage(<KnowledgeBasePage />, { route: "/tools/kb?concept=角色设定" });
    await waitFor(() => expect(screen.getByTestId("char-instance-view")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    await waitFor(() => expect(screen.queryByTestId("char-instance-view")).toBeNull());
    // 官方精选臂下通用列表在位：条目行照常出
    await waitFor(() => expect(screen.getByText("刘望津")).toBeTruthy());
    expect(screen.getByText("1 条")).toBeTruthy();
  });

  it("非法 ?concept= 落「全部」，不进视角", async () => {
    renderPage(<KnowledgeBasePage />, { route: "/tools/kb?concept=不存在" });
    await waitFor(() => expect(screen.getByTestId("kb-src-官方精选")).toBeTruthy());
    expect(screen.queryByTestId("char-instance-view")).toBeNull();
  });
});

describe("旧地址重定向（c-charlib-into-kb）", () => {
  it("/tools/characters → /tools/kb?concept=角色设定", () => {
    function ShowLoc() {
      const location = useLocation();
      return <span data-testid="loc">{location.pathname + location.search}</span>;
    }
    render(
      <MemoryRouter initialEntries={["/tools/characters"]}>
        <Routes>
          <Route path="/tools/characters" element={<RedirectToKbCharView />} />
          <Route path="/tools/kb" element={<ShowLoc />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("loc").textContent).toBe("/tools/kb?concept=角色设定");
  });
});
