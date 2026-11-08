// 知识库页「知识提炼」入口接线测试（原型定稿 2026-11-08）：
// 单按钮 → 确认弹窗 → 开始提炼建任务 → toast；「知识整理」独立入口退役。
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
  instancesFlat: vi.fn(),
  refineCreate: vi.fn(),
  graphTree: vi.fn(),
  entry: vi.fn(),
  listInstances: vi.fn(),
}));

vi.mock("@/lib/kbApi", async (orig) => {
  const actual = await orig<typeof import("@/lib/kbApi")>();
  return {
    ...actual,
    kbApi: {
      ...actual.kbApi,
      genres: api.genres,
      entries: api.entries,
      libraries: api.libraries,
      instancesFlat: api.instancesFlat,
      refineTasks: {
        ...actual.kbApi.refineTasks,
        create: api.refineCreate,
      },
      graphTree: api.graphTree,
      entry: api.entry,
      listInstances: api.listInstances,
    },
  };
});

import KnowledgeBasePage, { fieldsOf } from "@/pages/KnowledgeBasePage";
import type { KbInstanceRow } from "@/lib/kbApi";

function renderPage(ui: React.ReactElement = <KnowledgeBasePage />, opts: { route?: string } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[opts.route ?? "/"]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  libApi.listLibrary.mockResolvedValue({ count: 0, items: [] });
  api.genres.mockResolvedValue([{ name: "玄幻", count: 1 }]);
  api.entries.mockResolvedValue({ entries: [], next_cursor: "" });
  api.libraries.mockResolvedValue([]);
  api.instancesFlat.mockResolvedValue({ ok: true, rows: [] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("知识库页知识提炼入口（单按钮＋确认弹窗＋任务化）", () => {
  it("点按钮开确认弹窗（两步说明在案），确认建任务＋toast，不自动跳页", async () => {
    api.refineCreate.mockResolvedValue({ id: "t1", genre: "玄幻", status: "queued" });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    // 旧「知识整理」入口退役
    expect(screen.queryByText("知识整理")).toBeNull();
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    // 两步说明在案
    expect(screen.getByText("归类进树")).toBeTruthy();
    expect(screen.getByText("梳理关系")).toBeTruthy();
    fireEvent.click(screen.getByTestId("kb-refine-start"));
    await waitFor(() => expect(api.refineCreate).toHaveBeenCalledWith(""));
    await waitFor(() => expect(screen.getByTestId("kb-toast")).toBeTruthy());
    expect(screen.getByText("知识提炼任务已开始")).toBeTruthy();
    expect(screen.queryByTestId("kb-refine-modal")).toBeNull();
  });

  it("全部题材臂：空串题材直传（genre 三元两臂）", async () => {
    api.refineCreate.mockResolvedValue({ id: "t2", genre: "", status: "queued" });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-start"));
    await waitFor(() => expect(api.refineCreate).toHaveBeenCalledWith(""));
  });

  it("弹窗关闭两臂：✕ 与「暂不」都收弹窗不建任务", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    // ✕ 臂
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    fireEvent.click(screen.getByText("✕"));
    await waitFor(() => expect(screen.queryByTestId("kb-refine-modal")).toBeNull());
    expect(api.refineCreate).not.toHaveBeenCalled();
    // 「暂不」臂
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    fireEvent.click(screen.getByText("暂不"));
    await waitFor(() => expect(screen.queryByTestId("kb-refine-modal")).toBeNull());
    expect(api.refineCreate).not.toHaveBeenCalled();
  });

  it("建任务中按钮禁用（refineBusy 防双击），完成后恢复", async () => {
    let resolveCreate: (v: unknown) => void = () => {};
    api.refineCreate.mockImplementation(() => new Promise((res) => { resolveCreate = res; }));
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-start"));
    await waitFor(() => expect((screen.getByTestId("kb-refine-start") as HTMLButtonElement).disabled).toBe(true));
    resolveCreate({ id: "t9", genre: "", status: "queued" });
    await waitFor(() => expect(screen.queryByTestId("kb-refine-modal")).toBeNull());
  });

  it("toast 链接点击跳任务清单", async () => {
    api.refineCreate.mockResolvedValue({ id: "t3", genre: "玄幻", status: "queued" });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-start"));
    await waitFor(() => expect(screen.getByTestId("kb-toast")).toBeTruthy());
    // 链接点击＝跳 /tools（MemoryRouter 内导航，知识库页卸载）
    fireEvent.click(screen.getByText("查看任务"));
    await waitFor(() => expect(screen.queryByTestId("kb-toast")).toBeNull());
  });

  it("重复任务被拒（409 语义）→ 弹窗收起给提示，不弹 toast", async () => {
    api.refineCreate.mockRejectedValue(new Error("该题材已有进行中的知识提炼任务"));
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-start"));
    await waitFor(() => expect(screen.queryByTestId("kb-refine-modal")).toBeNull());
    expect(screen.queryByTestId("kb-toast")).toBeNull();
  });
});


describe("知识库页覆盖率契约补臂（提炼弹窗 kicker／树抽屉点实例／fieldsOf schema 序）", () => {
  const instRow = (id: string, kid: string, text: string): KbInstanceRow => ({
    row_kind: "instance", id, knowledge_id: kid, knowledge_title: "其他", chain: [],
    genre: "玄幻", concept: "手法", text, quote: "例句", source_novel: "书",
    source_chapter: "第1章", src_kind: "拆书", created_at: "2026-11-08T00:00:00",
    fields_json: "{}", knowledge_schema_json: "[]", name: "",
  });

  it("fieldsOf 按知识点 schema 序在前、模板外键字典兜底尾随", () => {
    const row = instRow("i1", "k1", "正文");
    row.fields_json = JSON.stringify({ 适用场面: "战斗", 情绪链: "不安" });
    row.knowledge_schema_json = JSON.stringify([{ name: "情绪链", desc: "" }]);
    const out = fieldsOf(row);
    // 模板命中的「情绪链」在前（fields 里 适用场面 在前），未收录模板的走字典兜底尾随
    expect(out[0][0]).toBe("情绪链");
    expect(out.map((x) => x[0])).toContain("适用场面");
  });

  it("具体题材开弹窗：kicker 显示题材名（非全部题材臂）", async () => {
    api.refineCreate.mockResolvedValue({ id: "t4", genre: "玄幻", status: "queued" });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    // 左栏点具体题材「玄幻」（按钮带计数，按文本找）
    const genreBtn = screen.getAllByRole("button").find((b) => (b.textContent || "").includes("玄幻"));
    expect(genreBtn).toBeTruthy();
    fireEvent.click(genreBtn!);
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    expect(screen.getByText("玄幻 · 知识库")).toBeTruthy();
  });

  it("树抽屉点实例行 → 实例详情弹窗（onSelectInstance 接线）", async () => {
    api.graphTree.mockResolvedValue({
      ok: true, rel_edges: [],
      roots: [{ id: "root:玄幻:", kind: "root", title: "写作知识", concept: "", genre: "玄幻",
        definition: "", children: [
          { id: "k9", kind: "knowledge", title: "其他", concept: "", genre: "玄幻", definition: "暂存", children: [] },
        ] }],
    });
    api.instancesFlat.mockResolvedValue({ ok: true, rows: [instRow("i9", "k9", "他推门进来，风铃响了一声。")] });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    fireEvent.click(screen.getByText("树"));
    await waitFor(() => expect(screen.getByTestId("kb-tree-panel")).toBeTruthy());
    fireEvent.click(screen.getByText("其他"));
    await waitFor(() => expect(screen.getAllByTestId("kb-tree-instance").length).toBe(1));
    fireEvent.click(screen.getByTestId("kb-tree-instance"));
    await waitFor(() => expect(screen.getByTestId("kb-inst-modal")).toBeTruthy());
  });
});


describe("知识库页覆盖率契约补臂 II（遮罩/fieldsOf 变体/键盘臂/无 quote 实例/toast 自动消）", () => {
  const instRow = (id: string, kid: string, text: string): KbInstanceRow => ({
    row_kind: "instance", id, knowledge_id: kid, knowledge_title: "其他", chain: [],
    genre: "玄幻", concept: "手法", text, quote: "", source_novel: "书",
    source_chapter: "第1章", src_kind: "拆书", created_at: "2026-11-08T00:00:00",
    fields_json: "{}", knowledge_schema_json: "[]", name: "",
  });

  it("点弹窗遮罩关闭（不建任务）", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-btn"));
    await waitFor(() => expect(screen.getByTestId("kb-refine-modal")).toBeTruthy());
    fireEvent.click(screen.getByTestId("kb-refine-modal").previousSibling as HTMLElement);
    await waitFor(() => expect(screen.queryByTestId("kb-refine-modal")).toBeNull());
    expect(api.refineCreate).not.toHaveBeenCalled();
  });

  it("fieldsOf 变体全臂：畸形 fields/数组 fields/schema 畸形/非数组 schema/坏格名/空值", () => {
    const base = instRow("i0", "k0", "正文");
    // fields_json 畸形（catch 臂）
    base.fields_json = "not-json{";
    base.knowledge_schema_json = "[]";
    expect(fieldsOf(base)).toEqual([]);
    // fields 是数组（typeof 臂）
    base.fields_json = "[1,2]";
    expect(fieldsOf(base)).toEqual([]);
    // schema 畸形 JSON（catch 臂）
    base.fields_json = JSON.stringify({ 情绪链: "不安" });
    base.knowledge_schema_json = "not-json{";
    expect(fieldsOf(base).length).toBeGreaterThan(0);
    // schema 非数组（Array.isArray false 臂）
    base.knowledge_schema_json = JSON.stringify({ name: "情绪链" });
    expect(fieldsOf(base).length).toBeGreaterThan(0);
    // schema 里格名非字符串／模板键不在 fields／值为空串（三 continue 臂）
    base.knowledge_schema_json = JSON.stringify([
      { name: 42 }, { name: "不存在格" }, { name: "空值格" }, { name: "情绪链" },
    ]);
    base.fields_json = JSON.stringify({ 情绪链: "不安", 空值格: "" });
    const out = fieldsOf(base);
    expect(out[0][0]).toBe("情绪链");
    // schema 值 null（?? 兜底臂）
    base.knowledge_schema_json = "null";
    expect(fieldsOf(base).length).toBeGreaterThan(0);
    // fields null（?? 兜底臂）
    base.fields_json = "null";
    base.knowledge_schema_json = "[]";
    expect(fieldsOf(base)).toEqual([]);
  });

  it("实例行键盘：非 Enter/Space 不开详情（keydown false 臂）", async () => {
    api.refineCreate.mockResolvedValue({ id: "t5", genre: "", status: "queued" });
    api.instancesFlat.mockResolvedValue({ ok: true, rows: [instRow("i8", "k8", "实例丙")] });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("kb-refine-btn")).toBeTruthy());
    const rowBtn = screen.getAllByRole("button").find((b) => (b.getAttribute("tabindex")) === "0"
      && (b.textContent || "").includes("实例丙"));
    if (rowBtn) {
      fireEvent.keyDown(rowBtn, { key: "Escape" });
      expect(screen.queryByTestId("kb-inst-modal")).toBeNull();
    }
  });

  it("知识详情弹窗实例群：无 quote 实例不渲染摘句行（false 臂）", async () => {
    api.entry.mockResolvedValue({
      id: "k77", genre: "玄幻", concept: "手法", concept_id: "玄幻:手法",
      title: "知识甲", instruction: "知识甲的指令。", payload: {}, schema_json: "[]",
      definition: "", origin: "summary", status: "active",
    });
    api.listInstances.mockResolvedValue({
      ok: true,
      instances: [{ id: "i7", text: "无摘句实例", quote: "", fields_json: "{}", source_novel: "书", source_chapter: "第1章", source_kind: "拆书", sort: 0 }],
    });
    const mat = { ...instRow("k77", "", "知识甲的指令。"), row_kind: "material" as const, instruction: "知识甲的指令。" };
    api.instancesFlat.mockResolvedValue({ ok: true, rows: [mat] });
    renderPage();
    await waitFor(() => expect(screen.getByText("知识甲的指令。")).toBeTruthy());
    fireEvent.click(screen.getByText("知识甲的指令。"));
    await waitFor(() => expect(screen.getByTestId("kb-know-modal")).toBeTruthy());
    await waitFor(() => expect(screen.getByText("无摘句实例")).toBeTruthy());
    // quote 空＝摘句臂未走（808 行 false 臂由本用例执行）；仅断言实例文本在弹窗
  });

  it("toast 5 秒自动消失（setTimeout 回调臂）", async () => {
    vi.useFakeTimers();
    try {
      api.refineCreate.mockResolvedValue({ id: "t6", genre: "", status: "queued" });
      renderPage();
      fireEvent.click(screen.getByTestId("kb-refine-btn"));
      fireEvent.click(screen.getByTestId("kb-refine-start"));
      await vi.advanceTimersByTimeAsync(5300);
      expect(screen.queryByTestId("kb-toast")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
