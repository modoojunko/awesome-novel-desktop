// 知识库页「官方精选」面（c-kb-baseline 批B）：来源筛选、只读徽章、隐藏/恢复官方版。
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
  concepts: vi.fn(),
  baselineOverride: vi.fn(),
  clearBaselineOverride: vi.fn(),
  baselineStatus: vi.fn(),
  baselineSync: vi.fn(),
  instancesFlat: vi.fn(),
  baselineProbe: vi.fn(),
  entry: vi.fn(),
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
      concepts: api.concepts,
      baselineOverride: api.baselineOverride,
      clearBaselineOverride: api.clearBaselineOverride,
      baselineStatus: api.baselineStatus,
      baselineSync: api.baselineSync,
      instancesFlat: api.instancesFlat,
      baselineProbe: api.baselineProbe,
      entry: api.entry,
    },
  };
});

vi.mock("force-graph", () => ({
  default: vi.fn(() => {
    const inst: Record<string, ReturnType<typeof vi.fn>> = {};
    for (const k of [
      "graphData", "nodeColor", "nodeLabel", "nodeVal", "linkColor", "linkWidth",
      "nodeId", "onLinkClick", "width", "height", "zoomToFit",
    ]) inst[k] = vi.fn().mockReturnValue(inst);
    return inst;
  }),
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


const BASE_ENTRY = {
  id: "b1", genre: "玄幻", concept: "手法", concept_id: "玄幻:手法",
  title: "官方手法A", instruction: "交手先守后攻，招式收在第三拍。",
  payload: {}, example: "", negative_example: "", when: { scene: "打斗" },
  evidence: "", rev: 1, src_kind: "baseline", src_novel_name: "",
  created_at: "2026-11-01T00:00:00", updated_at: "2026-11-01T00:00:00",
  layer: "baseline" as const, src_key: "baseline:玄幻:tech-a",
};

beforeEach(() => {
  libApi.listLibrary.mockResolvedValue({ count: 0, items: [] });
  api.genres.mockResolvedValue([{ name: "玄幻", count: 1 }]);
  api.entries.mockResolvedValue({ entries: [BASE_ENTRY], next_cursor: "" });
  api.libraries.mockResolvedValue([]);
  api.concepts.mockResolvedValue({ concepts: [], themes: [] });
  api.baselineOverride.mockResolvedValue({ entry_id: "b1", action: "hide" });
  api.clearBaselineOverride.mockResolvedValue({ entry_id: "b1", restored: true });
  api.baselineStatus.mockResolvedValue({ version: 0, entries: 0 });
  api.baselineSync.mockResolvedValue({ status: "synced", version: 1 });
  // 实例行列表（c-kb-instance-list）：基线用例一律走官方精选回退臂，实例臂空集
  api.instancesFlat.mockResolvedValue({ ok: true, rows: [] });
  // 统一行点行 → entry(id) 开详情抽屉（回退臂行不再携带全量 KbEntry）
  api.entry.mockImplementation(async (id: string) => {
    const all = await (api.entries.mock.results.at(-1)?.value as Promise<{ entries: typeof BASE_ENTRY[] }> | undefined);
    return all?.entries.find((e) => e.id === id) ?? BASE_ENTRY;
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KnowledgeBasePage · 官方来源（合并单列表，无特权臂——boss 2026-11-08）", () => {
  it("官方条目默认并入单列表：统一行形态＋来源标＋点行开知识弹窗", async () => {
    api.entries.mockResolvedValue({ entries: [BASE_ENTRY], next_cursor: "" });
    api.entry.mockResolvedValue(BASE_ENTRY);
    renderPage();
    const row = await screen.findByTestId("kb-inst-row");
    expect(row.textContent).toContain("官方手法A");
    expect(row.textContent).toContain("官方"); // 来源标
    expect(screen.getByTestId("kb-count-line").textContent).toContain("共 1 条实例");
    fireEvent.click(row);
    await waitFor(() => expect(api.entry).toHaveBeenCalledWith("b1"));
    await waitFor(() => expect(screen.getByText("知识定义")).toBeTruthy()); // 知识弹窗（无特殊只读段）
    expect(screen.queryByText("官方精选 · 只读")).toBeNull();
  });

  it("来源切「官方」：只剩官方行；切回「全部来源」合并", async () => {
    api.entries.mockResolvedValue({ entries: [BASE_ENTRY], next_cursor: "" });
    renderPage();
    await screen.findByText(/官方手法A/);
    fireEvent.click(screen.getByTestId("kb-src-官方"));
    await waitFor(() => expect(screen.getAllByTestId("kb-inst-row")).toHaveLength(1));
    fireEvent.click(screen.getByTestId("kb-src-全部"));
    await waitFor(() => expect(screen.getAllByTestId("kb-inst-row").length).toBeGreaterThanOrEqual(1));
  });

  it("无正文官方条目：行与弹窗标题走正文兜底", async () => {
    api.entries.mockResolvedValue({ entries: [{ ...BASE_ENTRY, title: "" }], next_cursor: "" });
    api.entry.mockResolvedValue({ ...BASE_ENTRY, title: "" });
    renderPage();
    const row = await screen.findByTestId("kb-inst-row");
    expect(row.textContent).toContain("交手先守后攻");
    fireEvent.click(row);
    await waitFor(() => expect(screen.getByRole("heading", { name: /交手先守后攻/ })).toBeTruthy());
  });

  it("旧路由跳知识库", () => {
    // 深链行为保留（App 层测试钉过，此处只验页挂载不炸）
    renderPage();
    expect(screen.getByTestId("kb-src-官方")).toBeTruthy();
  });
});
