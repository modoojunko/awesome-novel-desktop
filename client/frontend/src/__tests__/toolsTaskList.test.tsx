// 任务清单页（c-deconstruct-book 5.3）：空态、六类状态行、失败错误、删除两步确认、加载失败重试。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const state = vi.hoisted(() => ({ list: vi.fn(), del: vi.fn() }));
vi.mock("@/lib/deconstructApi", () => ({
  listDeconstructTasks: state.list,
  deleteDeconstructTask: state.del,
}));

import TaskListPage from "@/components/tools/TaskListPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TaskListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const RUNNING = {
  id: "t1", status: "running", book_name: "雾都侦探手记", total_chars: 386000,
  chapter_count: 214, volume_count: 8, ai_model: "qwen3-max", created_at: "2026-10-13T14:02:00",
  finished_at: null, queued_ahead: 0, product_count: 0, error: "",
};
const DONE = {
  id: "t2", status: "completed", book_name: "星海远征", total_chars: 542000,
  chapter_count: 318, volume_count: 10, ai_model: "qwen3-max", created_at: "2026-10-12T22:10:00",
  finished_at: "2026-10-12T22:41:00", queued_ahead: 0, product_count: 10, error: "",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TaskListPage", () => {
  it("空态引导", async () => {
    state.list.mockResolvedValue({ tasks: [], heartbeat: { running: 0, queued: 0 }, badge: 0 });
    renderPage();
    await waitFor(() => expect(screen.getByText("还没有任务")).toBeInTheDocument());
    expect(screen.getAllByText("创建拆书任务").length).toBeGreaterThan(0);
  });

  it("六类状态摘要＋失败错误＋删除两步确认", async () => {
    state.list.mockResolvedValue({
      tasks: [
        RUNNING,
        DONE,
        { ...DONE, id: "t3", status: "queued", queued_ahead: 2, book_name: "排队书", finished_at: null },
        { ...DONE, id: "t4", status: "failed", book_name: "失败书", error: "模型 400", finished_at: null },
        { ...DONE, id: "t5", status: "cancelled", book_name: "取消书", created_at: null },
        { ...DONE, id: "t6", status: "need_reupload", book_name: "重传书" },
      ],
      heartbeat: { running: 1, queued: 1 },
      badge: 3,
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("雾都侦探手记")).toBeInTheDocument());
    expect(screen.getByText(/前面还有 2 个任务/)).toBeInTheDocument();
    expect(screen.getByText(/模型 400/)).toBeInTheDocument();
    expect(screen.getByText(/重新选择文件后回到原排队位次/)).toBeInTheDocument();
    fireEvent.click(screen.getAllByText("删除")[0]);
    expect(screen.getByText(/确认删除/)).toBeInTheDocument();
    state.del.mockResolvedValue(undefined);
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(state.del).toHaveBeenCalledOnce());
  });


  it("行点击与详情按钮导航；删除确认执行删除", async () => {
    state.list.mockResolvedValue({ tasks: [DONE], heartbeat: { running: 0, queued: 0 }, badge: 1 });
    state.del.mockResolvedValue(undefined);
    renderPage();
    await waitFor(() => expect(screen.getByText("星海远征")).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/查看任务 星海远征/)); // 行点击
    fireEvent.click(screen.getAllByText("删除")[0]);
    fireEvent.click(screen.getAllByText("取消")[0]); // 取消臂
    expect(screen.queryByText(/确认？/)).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByText("删除")[0]);
    state.del.mockClear(); // 清前序用例调用历史
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(state.del).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByText("详情"));
  });

  it("加载失败显重试；重试成功收起", async () => {
    state.list.mockRejectedValue(new Error("x"));
    renderPage();
    await waitFor(() => expect(screen.getByText("加载失败")).toBeInTheDocument(), { timeout: 4000 });
    state.list.mockResolvedValue({ tasks: [], heartbeat: { running: 0, queued: 0 }, badge: 0 });
    fireEvent.click(screen.getByText("重试"));
    await waitFor(() => expect(screen.getByText("还没有任务")).toBeInTheDocument());
  });

  it("删除失败双臂：Error 显文案／非 Error 兜底（评审 P3：running 409 不再静默）", async () => {
    state.list.mockResolvedValue({ tasks: [DONE], heartbeat: { running: 0, queued: 0 }, badge: 1 });
    renderPage();
    await waitFor(() => expect(screen.getByText("星海远征")).toBeInTheDocument());
    state.del.mockRejectedValueOnce(new Error("任务拆解中，请先取消再删除"));
    fireEvent.click(screen.getAllByText("删除")[0]);
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(screen.getByText(/请先取消再删除/)).toBeInTheDocument());
    state.del.mockRejectedValueOnce("boom");
    fireEvent.click(screen.getAllByText("删除")[0]);
    fireEvent.click(screen.getByText("确认删除"));
    await waitFor(() => expect(screen.getAllByText("删除失败").length).toBe(2));
  });

  it("创建时间格式化为 MM-DD HH:mm；空值留白", async () => {
    state.list.mockResolvedValue({ tasks: [RUNNING, DONE, { ...DONE, id: "t9", created_at: null }], heartbeat: { running: 1, queued: 0 }, badge: 2 });
    renderPage();
    await waitFor(() => expect(screen.getByText("10-13 14:02")).toBeInTheDocument());
    expect(screen.getAllByText("10-12 22:10").length).toBe(1);
  });
});
