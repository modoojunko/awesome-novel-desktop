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
  entry: vi.fn(),
  entryRelations: vi.fn(),
  relationFeedback: vi.fn(),
  instancesFlat: vi.fn(),
  baselineProbe: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return {
    ...actual,
    kbApi: {
      ...actual.kbApi,
      entries: api.entries,
      entry: api.entry,
      libraries: api.libraries,
      genres: api.genres,
      instancesFlat: api.instancesFlat,
      baselineProbe: api.baselineProbe,
      organize: {
        ...actual.kbApi.organize,
        entryRelations: api.entryRelations,
        relationFeedback: api.relationFeedback,
      },
    },
  };
});

import KnowledgeBasePage, { fieldsOf, payloadRows } from "@/pages/KnowledgeBasePage";
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
  api.entryRelations.mockResolvedValue({ relations: [], merged_into: null });
  api.entry.mockResolvedValue(ENTRY); // 行点击取详情＝列表同款；外部对端用例自设
  // 实例行列表（c-kb-instance-list）：默认空集；知识行用例走官方精选回退臂
  api.instancesFlat.mockResolvedValue({ ok: true, rows: [] });
  // 官方知识探测（c-kb-baseline-update-ux）：默认同版静默
  api.baselineProbe.mockResolvedValue({ installed: 3, latest: 3, update_available: false });
  window.localStorage.removeItem("kb-sync-dismissed");
});

// 官方条目默认并入单列表（2026-11-08 无特权臂）——直接等待行上屏
async function openFallbackArm() {
  await screen.findByText(/刘望津/);
}

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
    await openFallbackArm();
    fireEvent.click(screen.getAllByText(/刘望津/)[0]);
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
    await openFallbackArm();
    fireEvent.click(screen.getAllByText(/刘望津/)[0]);
    await waitFor(() => expect(screen.getByText("字段")).toBeTruthy());
    expect(screen.queryByText("指令")).toBeNull();
    expect(screen.getByText("一句话人设")).toBeTruthy();
    // 列表卡片同渲染该句 → 多命中按存在性断言
    expect(screen.getAllByText("漂亮热情的农村出身姑娘。").length).toBeGreaterThan(0);
  });

  it("关联知识段（c-kb-relations-view）：active 行句式渲染＋点跳切对端", async () => {
    const entryB: KbEntry = { ...ENTRY, id: "kbentry-0002", title: "李耀", definition: "对端条目定义。" };
    api.entries.mockResolvedValue({ entries: [ENTRY, entryB], next_cursor: "" });
    api.entryRelations.mockResolvedValue({
      relations: [
        { id: "r1", rel_type: "applies_to", status: "active", direction: "out",
          other_id: "kbentry-0002", other_title: "李耀", confidence: 1, note: "", evidence: "" },
        { id: "r2", rel_type: "derived_from", status: "pending", direction: "in",
          other_id: "kbentry-0002", other_title: "李耀", confidence: 0.5, note: "", evidence: "" },
      ],
      merged_into: null,
    });
    renderPage();
    await openFallbackArm();
    fireEvent.click(screen.getAllByText(/刘望津/)[0]);
    await waitFor(() => expect(screen.getByText(/关联知识 · 来自知识整理/)).toBeTruthy());
    // 出向句式；pending 行不出
    expect(screen.getByText(/适用于 李耀/)).toBeTruthy();
    expect(screen.queryByText(/李耀 源自本知识/)).toBeNull();
    expect(api.entryRelations).toHaveBeenCalledWith("kbentry-0001", { status: "active" });
    // 点跳对端（B 在列表内→走 selected 切换），抽屉切到对端（标题两处：列表＋抽屉）
    fireEvent.click(screen.getByText(/适用于 李耀/));
    await waitFor(() => expect(screen.getByRole("heading", { name: /李耀/ })).toBeTruthy());
  });

  it("点跳对端不在列表：拉详情兜底切换", async () => {
    api.entry.mockResolvedValue({ ...ENTRY, id: "kbentry-external", title: "外部对端" });
    api.entryRelations.mockResolvedValue({
      relations: [
        { id: "rx", rel_type: "derived_from", status: "active", direction: "in",
          other_id: "kbentry-external", other_title: "外部对端", confidence: 1, note: "", evidence: "" },
      ],
      merged_into: null,
    });
    renderPage();
    await openFallbackArm();
    fireEvent.click(screen.getAllByText(/刘望津/)[0]);
    await waitFor(() => expect(screen.getByText(/外部对端 源自本知识/)).toBeTruthy());
    fireEvent.click(screen.getByText(/外部对端 源自本知识/));
    await waitFor(() => expect(api.entry).toHaveBeenCalledWith("kbentry-external"));
    // 兜底详情落到抽屉标题（列表无此行，唯一的 h2）
    await waitFor(() => expect(screen.getByRole("heading", { name: "外部对端" })).toBeTruthy());
  });

  it("定义空不拿实例文本冒充（c-kb-relations-view 顺手修）：只显示待补提示", async () => {
    const noDef: KbEntry = { ...ENTRY, id: "kbentry-nodef", title: "无定义条目", definition: "", instruction: "先写结果，再倒回去拆折。" };
    api.entries.mockResolvedValue({ entries: [noDef], next_cursor: "" });
    api.entry.mockResolvedValue(noDef);
    renderPage();
    fireEvent.click(screen.getByTestId("kb-src-官方"));
    await screen.findByText(/无定义条目/);
    fireEvent.click(screen.getByText(/无定义条目/));
    await waitFor(() => expect(screen.getByText(/知识定义待补/)).toBeTruthy());
    // 实例文本不得出现在「知识定义」段冒充定义（定义段只允许待补提示）
    const defSection = screen.getByText("知识定义").parentElement!;
    expect(defSection.textContent).not.toContain("先写结果");
  });

  it("视图切换臂：列表/树 setView 可点", async () => {
    renderPage();
    await openFallbackArm();
    fireEvent.click(screen.getByText("树"));
    await waitFor(() => expect(screen.getByText("列表")).toBeTruthy());
    fireEvent.click(screen.getByText("列表"));
    await waitFor(() => expect(screen.getAllByText(/刘望津/).length).toBeGreaterThan(0));
  });

  it("关闭抽屉后字段段退场", async () => {
    renderPage();
    await openFallbackArm();
    fireEvent.click(screen.getAllByText(/刘望津/)[0]);
    await waitFor(() => expect(screen.getByText("字段")).toBeTruthy());
    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByText("字段")).toBeNull());
  });
});

describe("角色设定页签同构（c-kb-view-unify：档案柜视图退役）", () => {
  it("?concept=角色设定 深链落位：与其余页签同构的实例行列表", async () => {
    renderPage(<KnowledgeBasePage />, { route: "/tools/kb?concept=角色设定" });
    // 档案柜视图退役；统一计数行在位（实例臂）
    await waitFor(() => expect(screen.getByTestId("kb-count-line")).toBeTruthy());
    expect(screen.queryByTestId("char-instance-view")).toBeNull();
  });

  it("来源切「官方精选」→ 知识行回退臂（仍带角色设定概念过滤）", async () => {
    renderPage(<KnowledgeBasePage />, { route: "/tools/kb?concept=角色设定" });
    await waitFor(() => expect(screen.getByTestId("kb-count-line")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-src-官方"));
    await waitFor(() => expect(screen.getAllByText(/刘望津/).length).toBeGreaterThan(0));
    expect(screen.getByTestId("kb-count-line").textContent).toContain("共 1 条实例");
  });

  it("非法 ?concept= 落「全部」", async () => {
    renderPage(<KnowledgeBasePage />, { route: "/tools/kb?concept=不存在" });
    await waitFor(() => expect(screen.getByTestId("kb-src-官方")).toBeTruthy());
    expect(screen.getByTestId("kb-count-line")).toBeTruthy();
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

describe("官方知识更新探测（c-kb-baseline-update-ux）", () => {
  function watchKbSyncEvents() {
    const seen: Record<string, unknown>[] = [];
    const on = (e: Event) => seen.push((e as CustomEvent).detail);
    window.addEventListener("kb-sync-modal:open", on);
    return { seen, off: () => window.removeEventListener("kb-sync-modal:open", on) };
  }

  it("有新版且未锚压制→自动弹更新窗；页头入口带版本号", async () => {
    const { clearDialogQueue } = await import("@/lib/dialogQueue");
    const { resetKbProbeState } = await import("@/lib/kbProbe");
    clearDialogQueue();
    resetKbProbeState();
    api.baselineProbe.mockResolvedValue({ installed: 3, latest: 4, update_available: true });
    const w = watchKbSyncEvents();
    try {
      renderPage();
      await waitFor(() => expect(w.seen.length).toBe(1));
      expect(w.seen[0]).toEqual({ mode: "update", from: 3, to: 4 });
      expect((screen.getByTestId("kb-baseline-entry").textContent ?? "")).toContain("v3");
    } finally {
      w.off();
    }
  });

  it("同版静默不弹；「暂不更新」锚压制同版自动弹（手动入口不受影响）", async () => {
    const { clearDialogQueue } = await import("@/lib/dialogQueue");
    const { resetKbProbeState } = await import("@/lib/kbProbe");
    clearDialogQueue();
    resetKbProbeState();
    const w = watchKbSyncEvents();
    try {
      renderPage();
      await waitFor(() => expect(api.baselineProbe).toHaveBeenCalled());
      expect(w.seen.length).toBe(0); // 同版静默

      cleanup();
      window.localStorage.setItem("kb-sync-dismissed", JSON.stringify({ updateVersion: "4" }));
      api.baselineProbe.mockResolvedValue({ installed: 3, latest: 4, update_available: true });
      renderPage();
      await waitFor(() => expect(api.baselineProbe).toHaveBeenCalledTimes(2));
      expect(w.seen.length).toBe(0); // 锚压制：同版不重弹

      // 手动入口不受锚影响
      fireEvent.click(screen.getByTestId("kb-baseline-entry"));
      expect(w.seen.length).toBe(1);
      expect(w.seen[0]).toEqual({ mode: "manual" });
    } finally {
      w.off();
    }
  });
  it("探测失败静默不弹；未装（installed=0）入口不带版本号仍可点", async () => {
    const { clearDialogQueue } = await import("@/lib/dialogQueue");
    const { resetKbProbeState } = await import("@/lib/kbProbe");
    clearDialogQueue();
    resetKbProbeState();
    const w = watchKbSyncEvents();
    try {
      api.baselineProbe.mockRejectedValue(new Error("cdn"));
      renderPage();
      await waitFor(() => expect(api.baselineProbe).toHaveBeenCalled());
      expect(w.seen.length).toBe(0); // 探测失败＝无更新静默
      const label = screen.getByTestId("kb-baseline-entry").textContent ?? "";
      expect(label).not.toContain("v");

      // 未装态（installed=0）入口显示无版本号；update_available 仍自动弹（补装语义）
      cleanup();
      api.baselineProbe.mockResolvedValue({ installed: 0, latest: 4, update_available: true });
      renderPage();
      await waitFor(() => expect(w.seen.length).toBe(1));
      expect((screen.getByTestId("kb-baseline-entry").textContent ?? "")).not.toContain("v");
    } finally {
      w.off();
    }
  });
});

describe("fieldsOf（实例字段：知识点模板序在前）", () => {
  it("模板序命中在前、剩余键尾随；畸形 JSON 兜底", () => {
    const row = {
      row_kind: "instance",
      fields_json: JSON.stringify({ b: "第二条", a: "第一条", c: ["丙", "丁"] }),
      knowledge_schema_json: JSON.stringify([
        { name: "c", desc: "丙格" },
        { name: "a", desc: "甲格" },
        { name: "zzz" }, // 模板键不在 fields：跳过
      ]),
    } as unknown as Parameters<typeof fieldsOf>[0];
    const rows = fieldsOf(row);
    // 模板序在前（c、a），剩余键按存储序尾随（b）
    expect(rows.map(([k]) => k)).toEqual(["c", "a", "b"]);
    expect(rows[0]).toEqual(["c", "丙、丁"]);

    // 非 instance 行返空；畸形 JSON 走兜底不炸
    expect(fieldsOf({ row_kind: "material" } as never)).toEqual([]);
    const bad = { row_kind: "instance", fields_json: "{oops", knowledge_schema_json: "[}" } as never;
    expect(fieldsOf(bad)).toEqual([]);
  });

  it("与实例正文同值（句末归一）的字段不重复显示——官方条目拼装份防线", () => {
    const row = {
      row_kind: "instance",
      text: "吐槽穿插：惊悚推进中插入主角内心吐槽或黑色幽默独白，调节节奏并强化爽感。",
      fields_json: JSON.stringify({
        slot: "rule",
        text: "吐槽穿插：惊悚推进中插入主角内心吐槽或黑色幽默独白，调节节奏并强化爽感", // 同值（历史拼装份，差句号）
        name: "吐槽穿插", // 前缀子串：不是同值，保留
        how: "惊悚推进中插入主角内心吐槽或黑色幽默独白，调节节奏并强化爽感", // 子串：保留
        scene: "日常",
      }),
    } as unknown as Parameters<typeof fieldsOf>[0];
    const rows = fieldsOf(row).map(([label, value]) => [label, value] as const);
    // 拼装份（text，与正文同值差句号）被句末归一跳过；渲染输出为中文标签
    expect(rows.map(([label]) => label)).toEqual(["槽位", "名字", "怎么写", "适用场面"]);
    expect(rows.map(([, v]) => v)).not.toContain("吐槽穿插：惊悚推进中插入主角内心吐槽或黑色幽默独白，调节节奏并强化爽感");
  });

  it("角色卡逐字段原句：有原句的格带第三元、field_quotes 本身不成行", () => {
    const row = {
      row_kind: "instance",
      concept: "角色设定",
      text: "沉默寡言的老法医",
      fields_json: JSON.stringify({
        persona: "沉默寡言的老法医",
        look: "总穿一件旧夹克",
        field_quotes: { look: "他总穿那件洗得发白的旧夹克。", speech: "凶手把一个人锯成了麻将。" },
      }),
    } as unknown as Parameters<typeof fieldsOf>[0];
    const rows = fieldsOf(row);
    expect(rows.map(([label]) => label)).not.toContain("field_quotes");
    const look = rows.find(([label]) => label === "外貌标签");
    expect(look?.[2]).toBe("他总穿那件洗得发白的旧夹克。");
    // 无对应字段值的原句不单独出行（speech 未抽到值 → 不出行）
    expect(rows.map(([label]) => label)).not.toContain("语感口音");
  });

  it("模板序循环的同值字段同样跳过（schema 循环同防线）", () => {
    const row = {
      row_kind: "instance",
      text: "正文一句话。",
      fields_json: JSON.stringify({ a: "正文一句话", b: "别的格" }),
      knowledge_schema_json: JSON.stringify([{ name: "a", desc: "甲格" }, { name: "b", desc: "乙格" }]),
    } as unknown as Parameters<typeof fieldsOf>[0];
    expect(fieldsOf(row).map(([label]) => label)).toEqual(["b"]);
  });
});

describe("官方知识探测在途槽与提炼失败兜底（c-kb-baseline-update-ux 补臂）", () => {
  it("探测槽被占（StrictMode 双挂载第二臂）：挂载不再发探测", async () => {
    const { claimKbProbe, releaseKbProbe, resetKbProbeState } = await import("@/lib/kbProbe");
    resetKbProbeState();
    expect(claimKbProbe()).toBe(true); // 模拟首挂载在途
    try {
      renderPage();
      await screen.findByText(/刘望津/);
      expect(api.baselineProbe).not.toHaveBeenCalled();
    } finally {
      releaseKbProbe();
    }
  });

  it("知识提炼创建失败：弹窗收起并落列表区提示", async () => {
    const { resetKbProbeState } = await import("@/lib/kbProbe");
    resetKbProbeState();
    api.genres.mockResolvedValue([{ name: "玄幻", count: 5 }]);
    const refineMock = vi.fn().mockRejectedValue(new Error("模型额度不足"));
    const kbApiMod = await import("@/lib/kbApi");
    const orig = kbApiMod.kbApi.refineTasks;
    kbApiMod.kbApi.refineTasks = { ...orig, create: refineMock } as typeof orig;
    try {
      renderPage();
      await screen.findByText(/刘望津/);
      fireEvent.click(await screen.findByTestId("kb-refine-btn"));
      // 「全部题材」须先选题材（后端按题材建任务）
      const pick = await screen.findByTestId("kb-refine-genre-pick");
      fireEvent.change(pick.querySelector("select")!, { target: { value: "玄幻" } });
      fireEvent.click(await screen.findByTestId("kb-refine-start"));
      await waitFor(() => expect(screen.getByText(/模型额度不足/)).toBeTruthy());
    } finally {
      kbApiMod.kbApi.refineTasks = orig;
    }
  });
});
