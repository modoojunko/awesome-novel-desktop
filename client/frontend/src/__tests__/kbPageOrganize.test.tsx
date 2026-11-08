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
    },
  };
});

import KnowledgeBasePage from "@/pages/KnowledgeBasePage";

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
