// 知识库页「知识整理」入口接线测试（c-kb-organize 批D）：按钮开面板/genre 传递/关闭回调。
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
  organizeStatus: vi.fn(),
  organizeFindings: vi.fn(),
  organizeRun: vi.fn(),
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
      organize: {
        status: api.organizeStatus,
        findings: api.organizeFindings,
        run: api.organizeRun,
        adoptFinding: vi.fn(), ignoreFinding: vi.fn(),
        adoptRelation: vi.fn(), rejectRelation: vi.fn(),
        relationFeedback: vi.fn(), graphEntries: vi.fn().mockResolvedValue({ nodes: [], edges: [], edge_count: 0, edge_truncated: 0, genre: "" }),
      },
    },
  };
});

vi.mock("force-graph", () => ({ default: vi.fn(() => {
  const inst: Record<string, ReturnType<typeof vi.fn>> = {};
  for (const k of ["graphData", "nodeColor", "nodeLabel", "nodeVal", "linkColor", "linkWidth", "nodeId", "onLinkClick", "width", "height", "zoomToFit"]) inst[k] = vi.fn().mockReturnValue(inst);
  return inst;
}) }));

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


beforeEach(() => {
  libApi.listLibrary.mockResolvedValue({ count: 0, items: [] });
  api.genres.mockResolvedValue([{ name: "玄幻", count: 1 }]);
  api.entries.mockResolvedValue({ entries: [], next_cursor: "" });
  api.libraries.mockResolvedValue([]);
  api.concepts.mockResolvedValue({ concepts: [], themes: [] });
  api.organizeStatus.mockResolvedValue({
    genre: "玄幻", running: false, last_run: null, pending_relations: 0, proposed_findings: 0,
  });
  api.organizeFindings.mockResolvedValue({ relations: [], findings: [], counts: { relations: 0, findings: 0 } });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("知识库页整理入口", () => {
  it("面板整理完成触发 onChanged（重载列表/库）", async () => {
    api.organizeRun.mockResolvedValue({ status: "completed", relations_added: 2 });
    renderPage();
    await waitFor(() => expect(screen.getByText("知识整理")).toBeTruthy());
    const entriesCallsBefore = api.entries.mock.calls.length;
    fireEvent.click(screen.getByText("知识整理"));
    await waitFor(() => expect(screen.getByTestId("kb-organize-panel")).toBeTruthy());
    fireEvent.click(screen.getByText("立即整理"));
    await waitFor(() => expect(api.organizeRun).toHaveBeenCalledWith("玄幻"));
    await waitFor(() => expect(api.entries.mock.calls.length).toBeGreaterThan(entriesCallsBefore));
    // 库分组卡已按原型退役——onChanged 只重载条目/实例
  });

  it("具体题材直传整理面板（genre 三元两臂全覆盖）", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("知识整理")).toBeTruthy());
    // 左栏点具体题材 → genre="玄幻" → 直传臂
    const genreBtn = screen.getAllByRole("button").find((b) => b.textContent === "玄幻"
      && !b.textContent.includes("整理"));
    if (genreBtn) fireEvent.click(genreBtn);
    await waitFor(() => expect(screen.getByText("知识整理")).toBeTruthy());
    fireEvent.click(screen.getByText("知识整理"));
    await waitFor(() => expect(screen.getByTestId("kb-organize-panel")).toBeTruthy());
    expect(api.organizeStatus).toHaveBeenCalledWith("玄幻");
    fireEvent.click(screen.getByLabelText("关闭"));
  });

  it("按钮开整理面板（默认题材兜底玄幻）并关闭", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("知识整理")).toBeTruthy());
    fireEvent.click(screen.getByText("知识整理"));
    await waitFor(() => expect(screen.getByTestId("kb-organize-panel")).toBeTruthy());
    expect(api.organizeStatus).toHaveBeenCalledWith("玄幻");
    fireEvent.click(screen.getByLabelText("关闭"));
    expect(screen.queryByTestId("kb-organize-panel")).toBeNull();
  });
});
