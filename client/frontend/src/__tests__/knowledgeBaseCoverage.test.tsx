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
  entry: vi.fn(),
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
});

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
    await screen.findByText("先果后因");
    // 初始 libraries 不带 genre（undefined 臂）
    expect(api.libraries).toHaveBeenCalledWith(undefined);
    // 概念页签 → 手法
    fireEvent.click(screen.getByTitle("写每一章时的场面打法"));
    await waitFor(() => expect(api.entries.mock.calls.at(-1)![0].concept).toBe("手法"));
    // 概念页签回「全部」→ 参数缺席（undefined）
    fireEvent.click(screen.getAllByText("全部")[1]);
    await waitFor(() => expect(api.entries.mock.calls.at(-1)![0].concept).toBeUndefined());
    // 题材切换：libraries 收到 genre（truthy 臂）
    fireEvent.click(screen.getByText("都市"));
    await waitFor(() => expect(api.libraries).toHaveBeenCalledWith("都市"));
    // 搜索
    fireEvent.change(screen.getByPlaceholderText("搜名字、内容、来源书名"), { target: { value: "打斗" } });
    await waitFor(() => expect(api.entries.mock.calls.at(-1)![0].q).toBe("打斗"));
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
  });

  it("genres 接口失败静默（catch 臂），列表照常", async () => {
    api.genres.mockRejectedValue(new Error("network"));
    renderPage();
    await screen.findByText("先果后因");
    await waitFor(() => expect(api.genres).toHaveBeenCalled());
  });
});

describe("KnowledgeBasePage 视图切换（c-kb-organize）", () => {
  it("列表/星图切换：页签在位", async () => {
    renderPage();
    await screen.findByText("先果后因");
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
    await screen.findByText("先果后因");
    fireEvent.click(screen.getByText("知识整理"));
    await waitFor(() => expect(screen.getByText(/题材「玄幻」/)).toBeTruthy());
    // 选了真实题材 → 整理面板透传该题材
    fireEvent.click(screen.getByText("都市"));
    await waitFor(() => expect(screen.getByText(/题材「都市」/)).toBeTruthy());
  });
});

describe("KnowledgeBasePage 手录表单", () => {
  it("素材行抽屉：提示卡＋删除确认真删（c-kb-summarize）", async () => {
    const mat: KbEntry = { ...entry(), id: "kbentry-mat", title: "素材条目", origin: "material", instruction: "素材原文。" };
    api.entries.mockResolvedValue({ entries: [entry(), mat], next_cursor: "" });
    renderPage();
    await waitFor(() => expect(screen.getByText("素材条目")).toBeTruthy());
    fireEvent.click(screen.getByText("素材条目"));
    await waitFor(() => expect(screen.getByText(/这是素材——/)).toBeTruthy());
    expect(screen.getByText("删除素材")).toBeTruthy();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    fireEvent.click(screen.getByText("删除素材"));
    expect(api.deleteEntry).not.toHaveBeenCalled();
    confirmSpy.mockReturnValue(true);
    fireEvent.click(screen.getByText("删除素材"));
    await waitFor(() => expect(api.deleteEntry).toHaveBeenCalledWith("kbentry-mat"));
    confirmSpy.mockRestore();
  });

  it("素材删除失败臂：opNote 提示（c-kb-summarize）", async () => {
    const mat: KbEntry = { ...entry(), id: "kbentry-mat2", title: "素材条目二", origin: "material", instruction: "素材原文。" };
    api.entries.mockResolvedValue({ entries: [mat], next_cursor: "" });
    api.deleteEntry.mockRejectedValueOnce(new Error("删除失败"));
    renderPage();
    await waitFor(() => expect(screen.getByText("素材条目二")).toBeTruthy());
    fireEvent.click(screen.getByText("素材条目二"));
    await waitFor(() => expect(screen.getByText("删除素材")).toBeTruthy());
    const spy = vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByText("删除素材"));
    await waitFor(() => expect(screen.getByText(/删除失败/)).toBeTruthy());
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
    api.entry.mockRejectedValueOnce(new Error("net"));
    renderPage();
    await waitFor(() => expect(screen.getByText("先果后因")).toBeTruthy());
    fireEvent.click(screen.getByText("先果后因"));
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
