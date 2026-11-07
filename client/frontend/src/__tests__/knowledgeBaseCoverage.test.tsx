// 知识库页覆盖（c-knowledge-base）：题材栏折叠/概念页签/手录全分支/详情抽屉/加载更多。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const libApi = vi.hoisted(() => ({
  listLibrary: vi.fn(),
}));

vi.mock("@/lib/libraryApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/libraryApi")>();
  return { ...actual, listLibrary: libApi.listLibrary };
});

const api = vi.hoisted(() => ({
  genres: vi.fn(),
  entries: vi.fn(),
  libraries: vi.fn(),
  createEntry: vi.fn(),
  deleteEntry: vi.fn(),
  listInstances: vi.fn(),
  entry: vi.fn(),
  instancesFlat: vi.fn(),
  graphAggregate: vi.fn(),
  graphCell: vi.fn(),
}));

const organize = vi.hoisted(() => ({
  graphEntries: vi.fn(),
  entryRelations: vi.fn(),
  relationFeedback: vi.fn(),
  status: vi.fn(),
  findings: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  // kbApi 是对象导出：mock 要替换对象内方法，不是模块顶层
  return {
    ...actual,
    kbApi: { ...actual.kbApi, ...api, organize: { ...actual.kbApi.organize, ...organize } },
  };
});

// force-graph 两层 mock（jsdom 无 canvas；kapsule 初始化会抛）
const kbGraphMock = vi.hoisted(() => {
  const inst: Record<string, ReturnType<typeof vi.fn>> = {};
  for (const k of [
    "graphData", "nodeColor", "nodeLabel", "nodeVal", "linkColor", "linkWidth",
    "nodeId", "nodeCanvasObject", "onNodeHover", "onNodeClick",
    "width", "height", "zoomToFit",
  ]) {
    inst[k] = vi.fn().mockReturnThis();
  }
  const second = vi.fn(() => inst);
  return { second };
});
vi.mock("force-graph", () => ({
  default: vi.fn(() => kbGraphMock.second),
}));

import KnowledgeBasePage from "@/pages/KnowledgeBasePage";

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


function entry(over: Record<string, unknown> = {}) {
  return {
    id: "aaaaaaaa-0000-0000-0000-000000000001",
    genre: "都市",
    concept: "手法",
    concept_id: "都市:手法",
    title: "先果后因",
    instruction: "先给果再补因。",
    payload: {},
    example: "他倒在血泊里，三分钟前剑才出鞘。",
    negative_example: "别按时间顺序平铺。",
    when: {},
    evidence: "第3章 引文",
    src_kind: "manual",
    src_novel_name: "",
    created_at: "",
    updated_at: "",
    ...over,
  };
}

const SEVEN_GENRES = [
  { name: "都市", count: 3 },
  { name: "仙侠/修真", count: 2 },
  { name: "玄幻", count: 1 },
  { name: "悬疑", count: 1 },
  { name: "科幻", count: 1 },
  { name: "末世/废土", count: 1 },
  { name: "谍战", count: 1 },
  { name: "游戏文", count: 0 },
  { name: "美食", count: 0 },
];

beforeEach(() => {
  libApi.listLibrary.mockResolvedValue({ count: 0, items: [] });
  api.genres.mockResolvedValue(SEVEN_GENRES);
  api.libraries.mockResolvedValue([
    { id: "l1", genre: "都市", concept: "手法", name: "手法库", purpose: "写每一章时的场面打法", contract: "live", enabled: true, entry_count: 6, bound_novels: 3, bound_in_book: 1 },
    { id: "l2", genre: "都市", concept: "文风", name: "文风库", purpose: "", contract: "snapshot", enabled: true, bound_novels: 0 }, // 缺 entry_count 走 ?? 0 臂
    { id: "l3", genre: "", concept: "文笔", name: "文笔库", purpose: "通用句子的写法", contract: "snapshot", enabled: true, entry_count: 0 },
  ]);
  api.entries.mockResolvedValue({ entries: [entry()], next_cursor: "" });
  api.createEntry.mockResolvedValue(entry());
  api.deleteEntry.mockResolvedValue({ deleted: "x" });
  api.listInstances = api.listInstances || vi.fn();
  api.listInstances.mockResolvedValue({ ok: true, instances: [] });
  // 实例行列表（c-kb-instance-list）：默认空集——实例臂空态走「记一条」卡
  api.instancesFlat.mockResolvedValue({ ok: true, rows: [] });
});

// 实例行 fixture（c-kb-instance-list 行形状：row_kind 判别＋后端拼好的 chain；
// chain 末段＝所属知识点本身、顶层父在前——与后端 _chain 口径一致）
function flatRow(over: Record<string, unknown> = {}) {
  return {
    row_kind: "instance",
    id: "inst-0001",
    knowledge_id: "kkkkkkkk-0000-0000-0000-000000000001",
    knowledge_title: "开篇钩子",
    chain: [
      { id: "kkkkkkkk-0000-0000-0000-000000000002", title: "场面手法" },
      { id: "kkkkkkkk-0000-0000-0000-000000000001", title: "开篇钩子" },
    ],
    genre: "都市",
    concept: "手法",
    text: "先写结果，再倒回去拆折。",
    quote: "留半拍空白让台词自己落地",
    source_novel: "13路末班车",
    source_chapter: "第3章",
    src_kind: "拆书",
    created_at: "2026-11-07T10:00:00",
    ...over,
  };
}

beforeEach(() => {
  api.graphAggregate.mockResolvedValue({ nodes: [], links: [] });
  api.graphCell.mockResolvedValue({ nodes: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KnowledgeBasePage 题材栏与列表", () => {
  it("题材>5 折叠/展开、库分组标题、加载更多追加、详情抽屉开关", async () => {
    // 分页链先于挂载：首屏带 cursor 出「加载更多」，第二页收口。
    // 第二页条目三无（无标题/无指令/无例证）：标题与预览双兜底臂＋抽屉空字段臂
    api.entries
      .mockResolvedValueOnce({ entries: [entry()], next_cursor: "cur2" })
      .mockResolvedValueOnce({
        entries: [entry({ id: "bbbbbbbb-0000-0000-0000-000000000002", title: "", instruction: "", example: "", negative_example: "", evidence: "" })],
        next_cursor: "",
      });
    const { container } = renderPage();
    // 知识行列表退居回退臂（c-kb-instance-list）：切「官方精选」后本用例的条目行为生效
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    await screen.findByText("先果后因");
    // 首屏：visibleGenres 截 5（末世/废土 藏起），0 计数题材只露前两个
    await screen.findByText("更多题材 (2)");
    expect(screen.getByText("都市")).toBeInTheDocument();
    expect(screen.queryByText("末世/废土")).not.toBeInTheDocument();
    expect(screen.getByText("游戏文")).toBeInTheDocument();
    // 库分组：都市×2 ＋ 跨题材通用×1（genre 空串走兜底名）
    await screen.findByText("都市 · 2 个库");
    expect(screen.getByText("跨题材通用 · 1 个库")).toBeInTheDocument();
    // 库卡：徽章/用途/成员数/在用数（含空 purpose 与 0 在用臂）
    expect(screen.getByText("本书已启用")).toBeInTheDocument();
    expect(screen.getByText("写每一章时的场面打法")).toBeInTheDocument();
    expect(screen.getByText("6 条")).toBeInTheDocument();
    expect(screen.getByText("3 本书在用")).toBeInTheDocument();
    expect(screen.getAllByText("0 条").length).toBeGreaterThanOrEqual(1); // 缺 entry_count 卡与 0 计数卡
    expect(screen.queryByText("0 本书在用")).not.toBeInTheDocument();
    // 展开全部题材 → 收起臂（展开后按钮仍要在，收得回去）
    fireEvent.click(screen.getByText("更多题材 (2)"));
    expect(screen.getByText("收起")).toBeInTheDocument();
    expect(screen.getByText("末世/废土")).toBeInTheDocument();
    fireEvent.click(screen.getByText("收起"));
    expect(await screen.findByText("更多题材 (2)")).toBeInTheDocument();
    expect(screen.queryByText("末世/废土")).not.toBeInTheDocument();
    // 列表分页：第二页空标题走 instruction 截断兜底，无 cursor 后按钮消失
    fireEvent.click(await screen.findByText("加载更多"));
    await waitFor(() => expect(api.entries).toHaveBeenCalledTimes(2));
    expect(api.entries.mock.calls[1][0].cursor).toBe("cur2");
    await screen.findByText(/bbbbbbbb/); // 第二页条目已追加（头行 id 前缀，插值拆节点用正则）
    // 三无条目详情：无指令/正例/反例/证据（假臂），标题兜底空
    fireEvent.click(screen.getAllByText(/bbbbbbbb/)[0]); // 列表头（抽屉头同文案）
    await screen.findByText("✕"); // 抽屉已开
    expect(screen.queryByText("指令")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("✕"));
    expect(screen.queryByText("加载更多")).not.toBeInTheDocument();
    // 详情抽屉：全字段 + ✕ 关
    fireEvent.click(screen.getByText("先果后因"));
    expect(screen.getByText("正例")).toBeInTheDocument();
    expect(screen.getByText("反例")).toBeInTheDocument();
    expect(screen.getByText("证据")).toBeInTheDocument();
    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByText("正例")).not.toBeInTheDocument());
    // 背景遮罩点击关抽屉
    fireEvent.click(screen.getByText("先果后因"));
    await screen.findByText("正例");
    fireEvent.click(container.querySelector(".bg-black\\/50")!);
    await waitFor(() => expect(screen.queryByText("正例")).not.toBeInTheDocument());
  });

  it("概念页签切换带 concept 参数、题材切换带 genre、搜索带 q、情节页签禁用", async () => {
    renderPage();
    // 实例臂（c-kb-instance-list）：筛选参数由 instancesFlat 承接
    await screen.findByTestId("kb-count-line");
    // 初始 libraries 不带 genre（undefined 臂）
    expect(api.libraries).toHaveBeenCalledWith(undefined);
    // 概念页签 → 手法
    fireEvent.click(screen.getByTitle("写每一章时的场面打法"));
    await waitFor(() => expect(api.instancesFlat.mock.calls.at(-1)![0].concept).toBe("手法"));
    // 概念页签回「全部」→ 参数缺席（undefined）
    fireEvent.click(screen.getAllByText("全部")[1]);
    await waitFor(() => expect(api.instancesFlat.mock.calls.at(-1)![0].concept).toBeUndefined());
    // 题材切换：libraries 收到 genre（truthy 臂）
    fireEvent.click(screen.getByText("都市"));
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith("都市"));
    await waitFor(() => expect(api.instancesFlat.mock.calls.at(-1)![0].genre).toBe("都市"));
    // 搜索
    fireEvent.change(screen.getByPlaceholderText("搜名字、内容、来源书名"), { target: { value: "打斗" } });
    await waitFor(() => expect(api.instancesFlat.mock.calls.at(-1)![0].q).toBe("打斗"));
    // 情节页签禁用不可点
    expect(screen.getByText(/情节/)).toBeDisabled();
    // 侧栏「全部」复位＋0 计数题材两态点击（折叠 slice(0,2) 臂 / 展开 map 臂）
    fireEvent.click(screen.getAllByText("全部")[0]);
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith(undefined));
    fireEvent.click(screen.getByText("游戏文"));
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith("游戏文"));
    fireEvent.click(screen.getByText("更多题材 (2)"));
    fireEvent.click(screen.getByText("美食"));
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith("美食"));
    // 回退臂（官方精选）：entries 筛选参数照旧口径
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    await screen.findByText("先果后因");
    fireEvent.click(screen.getByTitle("写每一章时的场面打法"));
    await waitFor(() => expect(api.entries.mock.calls.at(-1)![0].concept).toBe("手法"));
  });

  it("genres 接口失败静默（catch 臂），列表照常", async () => {
    api.genres.mockRejectedValue(new Error("network"));
    renderPage();
    await screen.findByTestId("kb-count-line");
    await waitFor(() => expect(api.genres).toHaveBeenCalled());
  });
});

describe("KnowledgeBasePage 视图切换（c-kb-organize）", () => {
  it("列表/星图切换：页签在位", async () => {
    renderPage();
    await screen.findByTestId("kb-count-line");
    expect(screen.getByText("列表")).toBeInTheDocument();
    expect(screen.getByText("星图")).toBeInTheDocument();
  });
});

describe("KnowledgeBasePage 角色设定条目头像框", () => {
  it("角色设定条目出姓氏占位（无字节），其他概念不出头像框", async () => {
    api.entries.mockResolvedValue({
      entries: [
        entry({
          id: "cccccccc-0000-0000-0000-000000000001",
          concept: "角色设定",
          concept_id: "年代文:角色设定",
          title: "刘望津",
          instruction: "漂亮热情的农村出身姑娘。",
        }),
        entry({
          id: "cccccccc-0000-0000-0000-000000000002",
          concept: "手法",
          title: "传功只给一句",
          instruction: "传功只给一句口诀。",
        }),
      ],
      next_cursor: "",
    });
    renderPage();
    // 头像框住在回退臂知识行（c-kb-instance-list）：切「官方精选」出条目列表
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    await screen.findByText("刘望津");
    const frames = screen.getAllByTestId("kb-entry-avatar-fallback");
    expect(frames).toHaveLength(1); // 只有角色设定条目有头像框
    expect(frames[0].textContent).toContain("刘");
  });
});

describe("KnowledgeBasePage 全部题材兜底（星图/知识整理）", () => {
  it("全部题材 → 星图/整理（genre 传递）", async () => {
    organize.status.mockResolvedValue({
      genre: "玄幻", running: false, last_run: null, pending_relations: 0, proposed_findings: 0,
    });
    organize.findings.mockResolvedValue({ relations: [], findings: [], counts: { relations: 0, findings: 0 } });
    renderPage();
    await screen.findByTestId("kb-count-line");
    fireEvent.click(screen.getByText("知识整理"));
    await waitFor(() => expect(screen.getByText(/题材「玄幻」/)).toBeTruthy());
    // 选了真实题材 → 整理面板透传该题材
    fireEvent.click(screen.getByText("都市"));
    await waitFor(() => expect(screen.getByText(/题材「都市」/)).toBeTruthy());
  });
});

describe("KnowledgeBasePage 手录表单", () => {
  it("素材行抽屉：提示卡＋删除确认真删（c-kb-summarize）", async () => {
    // 素材行住在实例臂（c-kb-instance-list）：点行 → entry(行 id) → 抽屉 material 分支
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [flatRow({ row_kind: "material", id: "kbentry-mat", knowledge_id: "", knowledge_title: "", chain: [], text: "素材原文。", src_kind: "手录", source_novel: "", source_chapter: "", quote: "" })],
    });
    api.entry.mockResolvedValue({ ...entry(), id: "kbentry-mat", title: "素材条目", origin: "material", instruction: "素材原文。" });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-material-row")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-material-row"));
    await waitFor(() => expect(api.entry).toHaveBeenCalledWith("kbentry-mat"));
    await waitFor(() => expect(screen.getByText(/这是素材——/)).toBeTruthy());
    expect(screen.getByTestId("kb-material-delete")).toBeTruthy();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByTestId("kb-material-delete"));
    expect(api.deleteEntry).not.toHaveBeenCalled();
    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByTestId("kb-material-delete"));
    await waitFor(() => expect(api.deleteEntry).toHaveBeenCalledWith("kbentry-mat"));
    confirmSpy.mockRestore();
  });

  it("字段 schema 段与实例群按 fields 渲染（c-kb-summarize schema 层）", async () => {
    // 抽屉改从实例行进入（c-kb-instance-list）：点行 → entry(knowledge_id)
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [flatRow({ knowledge_id: "kbentry-schema", knowledge_title: "小人物卷入" })],
    });
    api.entry.mockResolvedValue({
      ...entry(),
      id: "kbentry-schema",
      title: "小人物卷入",
      definition: "让普通小人物被动卷入超常事件。",
      schema_json: JSON.stringify([
        { name: "身份反差", desc: "日常身份与异常处境的落差" },
        { name: "性格底色", desc: "核心性格与说话方式" },
      ]),
    });
    api.listInstances = api.listInstances || vi.fn();
    api.listInstances.mockResolvedValue({
      ok: true,
      instances: [
        { id: "i1", text: "市井司机卷入冤魂案", source_kind: "拆书", source_novel: "13路末班车", source_chapter: "第1章", quote: "", fields_json: JSON.stringify({ 身份反差: "市井司机 vs 十年冤魂案", 性格底色: "嘴贫胆小却重情义" }), sort: 0 },
        { id: "i2", text: "无字段的实例", source_kind: "手录", source_novel: "", source_chapter: "", quote: "", fields_json: "{}", sort: 1 },
      ],
    });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-inst-row")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-inst-row"));
    await waitFor(() => expect(api.entry).toHaveBeenCalledWith("kbentry-schema"));
    await waitFor(() => expect(screen.getByText("字段 schema")).toBeTruthy());
    expect(screen.getByText(/日常身份与异常处境的落差/)).toBeTruthy();
    await screen.findByText("实例群"); // 实例群段随 listInstances 异步回填
    expect(screen.getByText("市井司机卷入冤魂案")).toBeTruthy();
    expect(screen.getByText(/身份反差：/)).toBeTruthy();
    expect(screen.getByText(/嘴贫胆小却重情义/)).toBeTruthy();
    expect(screen.getByText(/源自小说：13路末班车/)).toBeTruthy();
  });

  it("schema 为空不渲染字段段（c-kb-summarize）", async () => {
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [flatRow({ id: "inst-noschema", knowledge_id: "kbentry-noschema", knowledge_title: "无schema条目", quote: "", source_novel: "", source_chapter: "" })],
    });
    api.entry.mockResolvedValue({ ...entry(), id: "kbentry-noschema", title: "无schema条目", schema_json: "[]" });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-inst-row")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-inst-row"));
    await waitFor(() => expect(screen.getByText("知识定义")).toBeTruthy());
    // schema 为空：字段 schema 段不渲染；素材提示卡与实例群（无素材/无实例）也不出
    expect(screen.queryByText("字段 schema")).toBeNull();
    expect(screen.queryByText(/这是素材——/)).toBeNull();
    expect(screen.queryByText("实例群")).toBeNull();
  });

  it("素材删除失败臂：opNote 提示（c-kb-summarize）", async () => {
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [flatRow({ row_kind: "material", id: "kbentry-mat2", knowledge_id: "", knowledge_title: "", chain: [], text: "素材原文。", src_kind: "手录", source_novel: "", source_chapter: "", quote: "" })],
    });
    api.entry.mockResolvedValue({ ...entry(), id: "kbentry-mat2", title: "素材条目二", origin: "material", instruction: "素材原文。" });
    api.deleteEntry.mockRejectedValueOnce(new Error("删除失败"));
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-material-row")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-material-row"));
    await waitFor(() => expect(screen.getByTestId("kb-material-delete")).toBeTruthy());
    const spy = vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByTestId("kb-material-delete"));
    await waitFor(() => expect(screen.getAllByText(/删除失败/).length).toBeGreaterThan(0));
    spy.mockRestore();
  });

  it("点跳兜底失败臂：对端拉详情失败给提示（c-kb-relations-view）", async () => {
    organize.entryRelations.mockResolvedValue({
      relations: [
        { id: "rel-x", rel_type: "applies_to", status: "active", direction: "out",
          other_id: "kbentry-external-oops", other_title: "外部对端", confidence: 1, note: "", evidence: "" },
      ],
      merged_into: null,
    });
    api.instancesFlat.mockResolvedValue({ ok: true, rows: [flatRow({ quote: "", source_novel: "", source_chapter: "" })] });
    // 第一跳：点实例行开抽屉（entry 命中）；第二跳：点关联对端（entry 拒绝→提示）
    api.entry
      .mockResolvedValueOnce({ ...entry(), id: "kkkkkkkk-0000-0000-0000-000000000001", title: "开篇钩子" })
      .mockRejectedValueOnce(new Error("net"));
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-inst-row")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-inst-row"));
    await waitFor(() => expect(screen.getByText(/关联知识 · 来自知识整理/)).toBeTruthy());
    const relButton = screen.getByText(/适用于 外部对端/).closest("button");
    fireEvent.click(relButton!);
    await waitFor(() => expect(screen.getByText(/暂时打不开/)).toBeTruthy());
  });

  async function openManual() {
    api.entries.mockResolvedValue({ entries: [], next_cursor: "" });
    renderPage();
    fireEvent.click(await screen.findByText("记一条"));
    await screen.findByText("题材 *");
  }

  it("空文本/未选题材校验、保存成功三连刷新、取消", async () => {
    await openManual();
    fireEvent.click(screen.getByText("保存"));
    expect(screen.getByText("先写一条")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("你想记什么写法？贴上来"), { target: { value: "打斗先给果。" } });
    fireEvent.click(screen.getByText("保存"));
    expect(screen.getByText("选一个题材")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "题材" }), { target: { value: "都市" } });
    // 保存成功后的题材计数刷新失败走静默 catch 臂
    api.genres.mockRejectedValueOnce(new Error("net"));
    fireEvent.click(screen.getByText("保存"));
    // 类别归组选择臂
    fireEvent.change(screen.getByRole("combobox", { name: "类别" }), { target: { value: "文风" } });
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() =>
      expect(api.createEntry).toHaveBeenCalledWith({ genre: "都市", concept: "文风", instruction: "打斗先给果。" }),
    );
    // 成功提示在窗（素材口径），取消后关
    await waitFor(() => expect(screen.getByText(/素材已收录，总结后成为知识点/)).toBeTruthy());
    fireEvent.click(screen.getByText("取消"));
    await waitFor(() => expect(screen.queryByText("题材 *")).not.toBeInTheDocument());
    await waitFor(() => expect(api.libraries).toHaveBeenCalledTimes(3)); // 条目＋库重载＋再开窗拉一次
    // 取消臂
    fireEvent.click(await screen.findByText("记一条"));
    fireEvent.click(screen.getByText("取消"));
    await waitFor(() => expect(screen.queryByText("题材 *")).not.toBeInTheDocument());
  });

  it("保存失败两分支：后端 422 的 message / 无 message 兜底", async () => {
    await openManual();
    fireEvent.change(screen.getByPlaceholderText("你想记什么写法？贴上来"), { target: { value: "打斗先给果。" } });
    fireEvent.change(screen.getByRole("combobox", { name: "题材" }), { target: { value: "都市" } });
    // ① ApiError.message＝后端第一条闸门错误
    api.createEntry.mockRejectedValueOnce(new Error("指令不能为空"));
    fireEvent.click(screen.getByText("保存"));
    await screen.findByText("指令不能为空");
    // ② message 空 → 兜底
    api.createEntry.mockRejectedValueOnce({ message: "" });
    fireEvent.click(screen.getByText("保存"));
    await screen.findByText("保存失败");
  });
});

describe("实例行列表（c-kb-instance-list）", () => {
  it("行渲染：归属链（题材段非链接＋知识级可点）、标签、出处行、收录日期与来源标", async () => {
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [
        flatRow(),
        flatRow({
          row_kind: "material", id: "inst-mat", knowledge_id: "", knowledge_title: "", chain: [],
          text: "夜雨转场的素材句", quote: "", source_novel: "", source_chapter: "", src_kind: "手录",
        }),
      ],
    });
    const { container } = renderPage();
    await screen.findByTestId("kb-inst-row");
    // 计数行：N 与分类分布同口径（实例＋素材共 2 条手法）
    expect(screen.getByTestId("kb-count-line").textContent).toContain("共 2 条实例");
    expect(screen.getByTestId("kb-count-line").textContent).toContain("手法 2");
    // 归属链：知识级 accent 可点（kb-chain-seg×2，末段＝所属知识点），题材段是非链接文字
    const row = screen.getByTestId("kb-inst-row");
    expect(row.textContent).toContain("都市"); // 题材段
    expect(row.textContent).toContain("场面手法");
    expect(row.textContent).toContain("开篇钩子");
    const segs = row.querySelectorAll("[data-testid='kb-chain-seg']");
    expect(segs).toHaveLength(2);
    expect(segs[0].textContent).toBe("场面手法");
    expect(segs[1].textContent).toBe("开篇钩子");
    // 实例内容一句话＋摘句、出处行、收录日期＋来源标
    expect(row.textContent).toContain("先写结果，再倒回去拆折。");
    expect(row.textContent).toContain("——留半拍空白让台词自己落地");
    expect(row.textContent).toContain("源自：13路末班车 · 第3章");
    expect(row.textContent).toContain("2026-11-07 收录");
    expect(row.textContent).toContain("拆书");
    // 素材行：待归属标；无出处（空片段不渲染）；链区无知识级
    const mat = screen.getByTestId("kb-material-row");
    expect(screen.getByTestId("kb-row-material-badge").textContent).toBe("待归属素材");
    expect(mat.textContent).not.toContain("源自：");
    expect(mat.querySelectorAll("[data-testid='kb-chain-seg']")).toHaveLength(0);
    expect(container).toBeTruthy();
  });

  it("点行交互：实例行 entry(knowledge_id)、素材行 entry(行 id)、链上级 entry(链 id)", async () => {
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [flatRow(), flatRow({ row_kind: "material", id: "inst-mat2", knowledge_id: "", knowledge_title: "", chain: [], text: "素材句", src_kind: "手录", source_novel: "", source_chapter: "", quote: "" })],
    });
    api.entry.mockResolvedValue({ ...entry(), title: "抽屉标题" });
    renderPage();
    await screen.findByTestId("kb-inst-row");
    // 实例行本体 → 所属知识点
    fireEvent.click(screen.getByTestId("kb-inst-row"));
    await waitFor(() => expect(api.entry).toHaveBeenCalledWith("kkkkkkkk-0000-0000-0000-000000000001"));
    await waitFor(() => expect(screen.getByRole("heading", { name: "抽屉标题" })).toBeTruthy());
    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "抽屉标题" })).toBeNull());
    // 素材行 → 行 id
    fireEvent.click(screen.getByTestId("kb-material-row"));
    await waitFor(() => expect(api.entry).toHaveBeenCalledWith("inst-mat2"));
    fireEvent.click(screen.getByText("✕"));
    // 链上级（场面手法，链首段）→ 链 id
    fireEvent.click(screen.getAllByTestId("kb-chain-seg")[0]);
    await waitFor(() => expect(api.entry).toHaveBeenCalledWith("kkkkkkkk-0000-0000-0000-000000000002"));
    fireEvent.click(screen.getByText("✕")); // 关抽屉（提示渲染面在列表区，须 selected 为空）
    // 取数失败臂：抽屉没开成，提示落在列表区可见
    api.entry.mockRejectedValueOnce(new Error("net"));
    fireEvent.click(screen.getByTestId("kb-material-row"));
    await waitFor(() => expect(screen.getByTestId("kb-open-error").textContent).toContain("暂时打不开"));
  });

  it("取数失败静默空列表；在途不渲染空态卡", async () => {
    api.instancesFlat.mockRejectedValue(new Error("network"));
    const first = renderPage();
    await waitFor(() => expect(api.instancesFlat).toHaveBeenCalled());
    // 失败 → 空 rows：无筛选空态卡（记一条）在位
    await screen.findByText("记一条");
    first.unmount();
    // 在途（pending）：空态卡不闪现
    api.instancesFlat.mockReturnValue(new Promise(() => {}) as Promise<never>);
    const { unmount } = renderPage();
    await waitFor(() => expect(api.instancesFlat).toHaveBeenCalledTimes(2));
    expect(screen.queryByText("记一条")).toBeNull();
    expect(screen.queryByTestId("kb-flat-empty")).toBeNull();
    unmount();
  });

  it("筛选无命中空态＋清空筛选出口复位；零内容题材走记一条", async () => {
    api.instancesFlat.mockResolvedValue({ ok: true, rows: [] });
    renderPage();
    // 无筛选 → 记一条（零内容题材空态）
    await screen.findByText("记一条");
    // 有关键词 → 筛选无命中空态
    fireEvent.change(screen.getByPlaceholderText("搜名字、内容、来源书名"), { target: { value: "不存在的词" } });
    await screen.findByTestId("kb-flat-empty");
    expect(screen.getByTestId("kb-flat-empty").textContent).toContain("当前筛选下没有写法");
    // 清空筛选 → q/concept/src/genre 复位，回记一条空态
    fireEvent.click(screen.getByTestId("kb-clear-filters"));
    await screen.findByText("记一条");
    await waitFor(() => expect(api.instancesFlat.mock.calls.at(-1)![0].q).toBeUndefined());
  });

  it("来源（拆书/手录）与「跨题材通用」档为前端行过滤；名称排序按所属知识名、素材行末位", async () => {
    // 侧栏要有「跨题材通用」项（key=''）且在前 5 可见位（免点折叠）
    api.genres.mockResolvedValue([{ name: "跨题材通用", count: 1, key: "" }, ...SEVEN_GENRES]);
    api.instancesFlat.mockResolvedValue({
      ok: true,
      rows: [
        flatRow({ id: "inst-a", knowledge_title: "开篇钩子", src_kind: "拆书" }),
        flatRow({
          row_kind: "material", id: "inst-m", knowledge_id: "", knowledge_title: "", chain: [],
          genre: "", text: "未定题材素材", src_kind: "手录", source_novel: "", source_chapter: "", quote: "",
        }),
        flatRow({ id: "inst-b", knowledge_title: "传功只给一句", text: "传功口诀实例", src_kind: "手录" }),
      ],
    });
    renderPage();
    await screen.findAllByTestId("kb-inst-row");
    // 默认：3 行全出（全部来源＋全部题材）
    expect(screen.getAllByTestId(/kb-(inst|material)-row/)).toHaveLength(3);
    // 来源 → 手录：客户端过滤，只出手录行（传功实例＋素材），不发新参数
    fireEvent.click(screen.getByTestId("kb-src-手录"));
    await waitFor(() => expect(screen.getAllByTestId(/kb-(inst|material)-row/)).toHaveLength(2));
    expect(screen.getByTestId("kb-count-line").textContent).toContain("共 2 条实例");
    fireEvent.click(screen.getByTestId("kb-src-拆书"));
    await waitFor(() => expect(screen.getAllByTestId(/kb-(inst|material)-row/)).toHaveLength(1));
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    // 回到全部来源的实例臂——直接点「全部来源」
    fireEvent.click(screen.getByTestId("kb-src-全部"));
    await waitFor(() => expect(screen.getAllByTestId(/kb-(inst|material)-row/)).toHaveLength(3));
    // 「跨题材通用」档：只留 genre==='' 的素材行
    fireEvent.click(screen.getAllByText("跨题材通用")[0].closest("button")!); // 首个＝侧栏项
    await waitFor(() => expect(screen.getAllByTestId(/kb-(inst|material)-row/)).toHaveLength(1));
    expect(screen.getByTestId("kb-material-row").textContent).toContain("未定题材素材");
    fireEvent.click(screen.getAllByText("全部")[0]); // 复位题材
    await waitFor(() => expect(screen.getAllByTestId(/kb-(inst|material)-row/)).toHaveLength(3));
    // 名称排序：传功 < 开篇（zh 序），素材行（无知识名）恒排末位
    fireEvent.change(screen.getByRole("combobox", { name: "排序" }), { target: { value: "name" } });
    const instRows = screen.getAllByTestId("kb-inst-row");
    expect(instRows[0].textContent).toContain("传功口诀实例");
    expect(instRows[instRows.length - 1].textContent).toContain("先写结果，再倒回去拆折。");
    expect(screen.getByTestId("kb-material-row").textContent).toContain("未定题材素材");
  });
});
