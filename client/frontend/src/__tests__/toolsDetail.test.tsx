// 任务详情页（c-deconstruct-book 5.5）：进行中/完成（勾选＋出口）/失败/需重传 全态。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const state = vi.hoisted(() => ({
  get: vi.fn(),
  cancel: vi.fn(),
  del: vi.fn(),
  resume: vi.fn(),
  retry: vi.fn(),
  importBook: vi.fn(),
  export: vi.fn(),
}));
vi.mock("@/lib/deconstructApi", () => ({
  getDeconstructTask: state.get,
  cancelDeconstructTask: state.cancel,
  deleteDeconstructTask: state.del,
  resumeDeconstructTask: state.resume,
  retryUploadDeconstructTask: state.retry,
  importBookFromTask: state.importBook,
  exportTaskProducts: state.export,
  DECONSTRUCT_DIMS: [
    { key: "intro", name: "简介", file: "简介.md", setting: true },
    { key: "world", name: "世界设定", file: "世界设定.md", setting: true },
    { key: "techniques", name: "写作技法", file: "写作技法.md", setting: false },
  ],
}));

import TaskDetailPage from "@/components/tools/TaskDetailPage";

function detailOf(status: string, over: Record<string, unknown> = {}) {
  return {
    id: "t2",
    status,
    book_name: "星海远征",
    encoding: "utf-8",
    source_name: "星海远征.txt",
    total_chars: 542000,
    chapter_count: 318,
    volume_count: 10,
    parse_warnings: [],
    ai_model: "qwen3-max",
    api_config_id: "c1",
    selected_dims: ["intro", "world", "techniques"],
    dims: Object.fromEntries(
      ["intro", "world", "techniques"].map((k) => [k, { state: "completed", seg_done: 1, seg_total: 1, error: "" }]),
    ),
    products: [
      { filename: "简介.md", size: 100, dim: "简介" },
      { filename: "世界设定.md", size: 200, dim: "世界设定" },
      { filename: "写作技法.md", size: 300, dim: "写作技法" },
    ],
    error: "",
    book_id: null,
    created_at: null,
    finished_at: null,
    ...over,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/tools/deconstruct/t2"]}>
        <Routes>
          <Route path="/tools/deconstruct/:id" element={<TaskDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("TaskDetailPage", () => {
  beforeEach(() => {
    state.importBook.mockResolvedValue({ book_id: "book-9", name: "星海远征", skipped: [], warnings: [] });
    state.export.mockResolvedValue({ written: ["简介.md"], readme: "README.md", dest: "/tmp/x" });
    state.cancel.mockResolvedValue(undefined);
    state.resume.mockResolvedValue(undefined);
    state.del.mockResolvedValue(undefined);
  });

  it("进行中：十步明细＋取消调用", async () => {
    state.get.mockResolvedValue(
      detailOf("running", {
        dims: Object.fromEntries(
          ["intro", "world", "techniques"].map((k, i) => [
            k,
            { state: i === 0 ? "running" : i === 1 ? "completed" : "queued", seg_done: 1, seg_total: 3, error: "" },
          ]),
        ),
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("取消任务")).toBeInTheDocument());
    expect(screen.getByText(/进行中 · 段 1\/3/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("取消任务"));
    await waitFor(() => expect(state.cancel).toHaveBeenCalledOnce());
  });

  it("完成：默认全选、下限 1、导出流（含 pick 桥占位）", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    expect(screen.getByText(/已选 3\/3/)).toBeInTheDocument();
    // 下限 1
    const boxes = screen.getAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    const last = boxes[2] as HTMLInputElement;
    expect(last.checked).toBe(true);
    fireEvent.click(last);
    expect(last.checked).toBe(true);
    // 恢复全选
    for (const b of boxes) if (!(b as HTMLInputElement).checked) fireEvent.click(b);

    // 出口：导出（先测导出，建书成功导航另测）
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByText("存本地文件夹"));
    fireEvent.change(screen.getByLabelText(/导出到文件夹/), { target: { value: "/tmp/out" } });
    fireEvent.click(screen.getByText("选择文件夹并导出"));
    await waitFor(() => expect(state.export).toHaveBeenCalledOnce());
  });

  it("完成：建书失败显示错误（不导航）", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    state.importBook.mockRejectedValue(new Error("书数已达套餐上限"));
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByText("就建这本书"));
    await waitFor(() => expect(screen.getByText(/书数已达套餐上限/)).toBeInTheDocument());
  });

  it("建书失败显示错误（书满额）", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    state.importBook.mockRejectedValue(new Error("书数已达套餐上限"));
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByText("就建这本书"));
    await waitFor(() => expect(screen.getByText(/书数已达套餐上限/)).toBeInTheDocument());
  });

  it("失败：错误面板＋续拆＋删除确认", async () => {
    state.get.mockResolvedValue(detailOf("failed", { error: "模型 400" }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/模型 400/)).toBeInTheDocument());
    fireEvent.click(screen.getByText("从断点续拆"));
    await waitFor(() => expect(state.resume).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByText("删除任务及产物"));
    fireEvent.click(screen.getByText("确认删除任务及产物"));
    await waitFor(() => expect(state.del).toHaveBeenCalledOnce());
  });


  it("失败：删除确认可取消", async () => {
    state.get.mockResolvedValue(detailOf("failed", { error: "模型 400" }));
    renderPage();
    await waitFor(() => expect(screen.getByText("删除任务及产物")).toBeInTheDocument());
    state.del.mockClear();
    fireEvent.click(screen.getByText("删除任务及产物"));
    fireEvent.click(screen.getByText("取消"));
    expect(state.del).not.toHaveBeenCalled();
  });

  it("完成：解析提示（parse_warnings）与元信息渲染", async () => {
    state.get.mockResolvedValue(detailOf("completed", { parse_warnings: ["2 处章节标题未识别"] }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/已选 3\/3/)).toBeInTheDocument());
  });


  it("出口弹窗交互：切选项摘要联动、稍后再说/scrim/✕ 关闭、pick_folder 桥", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    // 无桥环境：pick_folder 按钮不炸（回落手输）
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    // 切「存本地文件夹」→ 摘要联动＋目录字段出现
    fireEvent.click(screen.getByText("存本地文件夹"));
    expect(screen.getByLabelText(/导出到文件夹/)).toBeInTheDocument();
    // scrim 点击关闭
    fireEvent.click(document.querySelector(".scrim")!);
    expect(screen.queryByText(/稍后再说/)).not.toBeInTheDocument();
    // 重开 → ✕ 关闭
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByLabelText("关闭"));
    expect(screen.queryByText(/稍后再说/)).not.toBeInTheDocument();
    // 重开 → 稍后再说关闭
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByText("稍后再说"));
    expect(screen.queryByText(/稍后再说/)).not.toBeInTheDocument();
  });

  it("失败：取消臂（删除确认后取消不删）", async () => {
    state.get.mockResolvedValue(detailOf("failed", { error: "模型 400" }));
    renderPage();
    await waitFor(() => expect(screen.getByText("删除任务及产物")).toBeInTheDocument());
    fireEvent.click(screen.getByText("删除任务及产物"));
    fireEvent.click(screen.getByText("取消"));
    expect(state.del).not.toHaveBeenCalled();
  });


  it("导出：pick_folder 桥选目录后导出", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    state.export.mockClear();
    const picked: string[] = [];
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: async () => { const d = "/tmp/picked-bridge"; picked.push(d); return d; } },
    };
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByText("存本地文件夹"));
    fireEvent.click(screen.getByText("选择文件夹"));
    await waitFor(() => expect((screen.getByLabelText(/导出到文件夹/) as HTMLInputElement).value).toBe("/tmp/picked-bridge"));
    fireEvent.click(screen.getByText("选择文件夹并导出"));
    await waitFor(() => expect(state.export).toHaveBeenCalledOnce());
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("需重传：重传按钮触发文件框（不崩）", async () => {
    state.get.mockResolvedValue(detailOf("need_reupload", { products: [] }));
    renderPage();
    await waitFor(() => expect(screen.getByText("源文件缺失")).toBeInTheDocument());
    fireEvent.click(screen.getByText("重传文件"));
  });

  it("需重传：选文件回原位次", async () => {
    state.get.mockResolvedValue(detailOf("need_reupload", { products: [] }));
    state.retry.mockResolvedValue({ status: "queued" });
    renderPage();
    await waitFor(() => expect(screen.getByText("源文件缺失")).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [new File(["x"], "星海远征.txt")] });
    fireEvent.change(input);
    await waitFor(() => expect(state.retry).toHaveBeenCalledOnce());
  });
});
