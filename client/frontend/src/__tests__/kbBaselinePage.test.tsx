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
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("KnowledgeBasePage · 官方精选", () => {
  it("来源筛选「官方精选」透传 src 参数", async () => {
    renderPage();
    await waitFor(() => expect(api.entries).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    await waitFor(() => {
      const calls = api.entries.mock.calls.map((c) => c[0] as { src?: string });
      expect(calls.some((c) => c.src === "官方精选")).toBe(true);
    });
  });

  it("基线条目显示「官方精选」徽章；副本＋官方新版双徽章", async () => {
    api.entries.mockResolvedValue({
      entries: [{ ...BASE_ENTRY, overlaid: true, official_update: true }],
      next_cursor: "",
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("官方精选")).toBeTruthy());
    expect(screen.getByText("我的副本")).toBeTruthy();
    expect(screen.getByText("官方有新版")).toBeTruthy();
  });

  it("抽屉里隐藏这条 → PUT hide 并刷新列表", async () => {
    renderPage();
    const row = await screen.findByText("官方手法A");
    fireEvent.click(row);
    const hide = await screen.findByTestId("kb-baseline-hide");
    api.genres.mockRejectedValueOnce(new Error("g")); // 计数刷新失败静默（catch 臂）
    fireEvent.click(hide);
    await waitFor(() => {
      expect(api.baselineOverride).toHaveBeenCalledWith("b1", "hide");
    });
    await waitFor(() => expect(api.entries.mock.calls.length).toBeGreaterThan(1));
  });

  it("有副本时显示「恢复官方版」→ DELETE 覆盖记录", async () => {
    api.entries.mockResolvedValue({
      entries: [{ ...BASE_ENTRY, overlaid: true }],
      next_cursor: "",
    });
    renderPage();
    fireEvent.click(await screen.findByText("官方手法A"));
    fireEvent.click(await screen.findByTestId("kb-baseline-restore"));
    await waitFor(() => expect(api.clearBaselineOverride).toHaveBeenCalledWith("b1"));
  });

  it("操作失败静默：抽屉不崩，可重试", async () => {
    api.baselineOverride.mockRejectedValueOnce(new Error("network"));
    renderPage();
    fireEvent.click(await screen.findByText("官方手法A"));
    fireEvent.click(await screen.findByTestId("kb-baseline-hide"));
    await waitFor(() => expect(api.baselineOverride).toHaveBeenCalled());
    // 失败不清选中、不抛：按钮恢复可用，可再点一次
    const btn = await screen.findByTestId("kb-baseline-hide");
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it("用户条目不出只读操作面", async () => {
    api.entries.mockResolvedValue({
      entries: [{ ...BASE_ENTRY, id: "u1", layer: "user" as const, src_kind: "manual" }],
      next_cursor: "",
    });
    renderPage();
    fireEvent.click(await screen.findByText("官方手法A"));
    await waitFor(() => expect(screen.getByText(/^知识定义$/)).toBeTruthy());
    expect(screen.queryByTestId("kb-baseline-hide")).toBeNull();
    expect(screen.queryByTestId("kb-baseline-restore")).toBeNull();
  });

  it("官方精选为空给重试面：同步成功后刷新列表", async () => {
    api.entries.mockResolvedValue({ entries: [], next_cursor: "" });
    renderPage();
    await waitFor(() => expect(api.entries).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    const panel = await screen.findByTestId("kb-baseline-empty");
    expect(panel.textContent).toContain("还没有同步下来");
    const before = api.entries.mock.calls.length;
    api.genres.mockRejectedValueOnce(new Error("g")); // 计数刷新失败静默（catch 臂）
    fireEvent.click(screen.getByTestId("kb-baseline-sync"));
    await waitFor(() => expect(api.baselineSync).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(api.entries.mock.calls.length).toBeGreaterThan(before));
    await waitFor(() => expect(screen.getByText("官方精选已更新")).toBeTruthy());
  });

  it("同步失败提示可重试（不抛）", async () => {
    api.entries.mockResolvedValue({ entries: [], next_cursor: "" });
    api.baselineSync.mockRejectedValueOnce(new Error("cdn"));
    renderPage();
    await waitFor(() => expect(api.entries).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    fireEvent.click(await screen.findByTestId("kb-baseline-sync"));
    await waitFor(() => expect(screen.getByText("同步没成功，稍后再试")).toBeTruthy());
  });

  it("「已隐藏」筛选可找回被隐藏条目并恢复默认（P1 回归）", async () => {
    api.entries.mockResolvedValue({
      entries: [{ ...BASE_ENTRY, hidden: true }],
      next_cursor: "",
    });
    renderPage();
    await waitFor(() => expect(api.entries).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("kb-src-已隐藏"));
    await waitFor(() => {
      const calls = api.entries.mock.calls.map((c) => c[0] as { src?: string });
      expect(calls.some((c) => c.src === "已隐藏")).toBe(true);
    });
    await waitFor(() => expect(screen.getAllByText("已隐藏").length).toBeGreaterThan(1)); // 筛选钮＋行徽章
    fireEvent.click(await screen.findByText("官方手法A"));
    fireEvent.click(await screen.findByTestId("kb-baseline-unhide"));
    await waitFor(() => expect(api.clearBaselineOverride).toHaveBeenCalledWith("b1"));
  });

  it("同步失败提示「同步没成功」而不是「没有新版本」", async () => {
    api.entries.mockResolvedValue({ entries: [], next_cursor: "" });
    api.baselineSync.mockResolvedValueOnce({ status: "failed" });
    renderPage();
    await waitFor(() => expect(api.entries).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("kb-src-官方精选"));
    fireEvent.click(await screen.findByTestId("kb-baseline-sync"));
    await waitFor(() => expect(screen.getByText("同步没成功，稍后再试")).toBeTruthy());
  });

  it("编辑＝存我的副本：草稿预填、取消可退、保存调 PUT edit 并刷新", async () => {
    api.baselineOverride.mockResolvedValue({ entry_id: "b1", action: "edit" });
    renderPage();
    fireEvent.click(await screen.findByText("官方手法A"));

    // 展开：草稿预填官方原文（用户从「看到的这条」开始改，不是从空白）
    fireEvent.click(await screen.findByTestId("kb-baseline-edit"));
    const ta = (await screen.findByTestId("kb-baseline-draft")) as HTMLTextAreaElement;
    expect(ta.value).toBe(BASE_ENTRY.instruction);

    // 取消＝收起且不发请求
    fireEvent.click(screen.getByTestId("kb-baseline-edit-cancel"));
    expect(screen.queryByTestId("kb-baseline-draft")).toBeNull();
    expect(api.baselineOverride).not.toHaveBeenCalled();

    // 再展开、改写、保存 → 只写用户副本
    fireEvent.click(screen.getByTestId("kb-baseline-edit"));
    fireEvent.change(await screen.findByTestId("kb-baseline-draft"), {
      target: { value: "我的说法：交手先让三招，再还手。" },
    });
    const before = api.entries.mock.calls.length;
    api.genres.mockRejectedValueOnce(new Error("g")); // 计数刷新失败静默（catch 臂）
    fireEvent.click(screen.getByTestId("kb-baseline-save"));
    await waitFor(() => {
      expect(api.baselineOverride).toHaveBeenCalledWith(
        "b1", "edit", "我的说法：交手先让三招，再还手。",
      );
    });
    await waitFor(() => expect(api.entries.mock.calls.length).toBeGreaterThan(before));
  });

  it("副本保存被闸门拒收：原样展示后端原因、留在抽屉可重试", async () => {
    // 后端 422 的 message＝第一条闸门原因（api.ts 不变量）——必须原样给用户
    api.baselineOverride.mockRejectedValueOnce(
      new Error("与系统固定文案撞句，请改写成自己的话"),
    );
    renderPage();
    fireEvent.click(await screen.findByText("官方手法A"));
    fireEvent.click(await screen.findByTestId("kb-baseline-edit"));
    fireEvent.click(screen.getByTestId("kb-baseline-save"));
    await waitFor(() => {
      expect(screen.getByTestId("kb-baseline-op-note").textContent).toContain("撞句");
    });
    // 不关抽屉、不清草稿：用户可改完再存；草稿限长 240（后端闸门同口径）
    const draft = screen.getByTestId("kb-baseline-draft") as HTMLTextAreaElement;
    expect(draft).toBeTruthy();
    expect(draft.getAttribute("maxLength")).toBe("240");
  });
});
