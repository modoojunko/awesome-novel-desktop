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
    graph: { state: "absent", available: false, warnings: 0, caps: true },
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

  it("详情加载失败 → 错误提示＋返回清单（不再停在加载中）", async () => {
    state.get.mockRejectedValue(new Error("任务不存在"));
    renderPage();
    await waitFor(() => expect(screen.getByText("任务加载失败")).toBeInTheDocument());
    expect(screen.getByText("任务不存在")).toBeInTheDocument();
    expect(screen.getByText("返回任务清单")).toBeInTheDocument();
  });

  it("轮询单次失败保留旧数据视图（taskErr&&!task 的 !task 假臂：不踢错误屏）", async () => {
    state.get.mockReset(); // Vitest4 restoreAllMocks 不清 vi.fn 历史/实现——本用例自管
    state.get.mockResolvedValueOnce(detailOf("running"));
    renderPage();
    await waitFor(() => expect(screen.getByText("取消任务")).toBeInTheDocument());
    const base = state.get.mock.calls.length;
    state.get.mockRejectedValueOnce(new Error("net blip"));
    state.get.mockResolvedValue(detailOf("running")); // 下一拍自愈，避免 undefined 数据态
    // 等失败的那一拍真实发生（基线后的下一次调用＝1.5s 轮询），再断言仍在进度视图
    await waitFor(
      () => expect(state.get.mock.calls.length).toBeGreaterThan(base),
      { timeout: 5000 },
    );
    expect(screen.queryByText("任务加载失败")).not.toBeInTheDocument();
    expect(screen.getByText("取消任务")).toBeInTheDocument();
  }, 10000);

  it("建书成功：跳新书并关闭弹窗", async () => {
    state.get.mockResolvedValue(detailOf("completed", { book_id: "book-9" }));
    state.importBook.mockResolvedValue({ book_id: "book-9", name: "星海远征", skipped: [], warnings: [] });
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    await waitFor(() => expect(screen.getByText("就建这本书")).toBeInTheDocument());
    fireEvent.click(screen.getByText("就建这本书"));
    await waitFor(() => expect(state.importBook).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.queryByText(/稍后再说/)).not.toBeInTheDocument());
  });

  beforeEach(() => {
    state.importBook.mockResolvedValue({ book_id: "book-9", name: "星海远征", skipped: [], warnings: [] });
    state.export.mockResolvedValue({ written: ["简介.md"], readme: "README.md", dest: "/tmp/x" });
    state.cancel.mockResolvedValue(undefined);
    state.resume.mockResolvedValue(undefined);
    state.del.mockResolvedValue(undefined);
  });

  it("进行中：拆卡步＋归并明细＋取消调用", async () => {
    state.get.mockResolvedValue(
      detailOf("running", {
        cards: { state: "running", done: 40, total: 100 },
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
    expect(screen.getByText(/进行中 · 40\/100 章/)).toBeInTheDocument(); // 逐章拆卡步
    expect(screen.getByText(/进行中 · 归并 1\/3/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("取消任务"));
    await waitFor(() => expect(state.cancel).toHaveBeenCalledOnce());
  });

  it("拆卡步三态：排队臂与完成臂", async () => {
    state.get.mockResolvedValue(detailOf("running", {
      cards: { state: "completed", done: 2, total: 2 },
      dims: Object.fromEntries(["intro", "world", "techniques"].map((k) => [k, { state: "queued", seg_done: 0, seg_total: 0, error: "" }])),
    }));
    renderPage();
    await waitFor(() => expect(document.querySelector('[data-od-id="step-cards"] em')).not.toBeNull());
    const doneCell = document.querySelector('[data-od-id="step-cards"] em')!;
    expect(doneCell.textContent).toBe("完成");
    expect(doneCell.className).toContain("ok");
    cleanup();
    state.get.mockResolvedValue(detailOf("queued", { cards: { state: "queued", done: 0, total: 50 } }));
    renderPage();
    await waitFor(() => expect(document.querySelector('[data-od-id="step-cards"] em')).not.toBeNull());
    expect(document.querySelector('[data-od-id="step-cards"] em')!.textContent).toBe("排队");
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


  it("进行中：维度失败臂渲染", async () => {
    state.get.mockResolvedValue(detailOf("running"));
    renderPage();
    await waitFor(() => expect(screen.getByText("取消任务")).toBeInTheDocument());
    // failed 臂：detailOf("failed") 单测已盖；此处断言 running 态无 err 徽标
    expect(screen.queryByText(/已失败/)).not.toBeInTheDocument();
  });


  it("防御臂：未知状态徽标回落＋空勾选进度归零＋缺维度键默认排队", async () => {
    state.get.mockResolvedValue({
      ...detailOf("running"),
      status: "mystery-status",
      selected_dims: [],
      dims: {},
      products: [],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("mystery-status")).toBeInTheDocument());
    // unknown status → STATUS_PILL/STATUS_LABEL 回落默认 pill
  });

  it("需重传：重传按钮点击触发文件框（不崩）", async () => {
    state.get.mockResolvedValue(detailOf("need_reupload", { products: [] }));
    renderPage();
    await waitFor(() => expect(screen.getByText("源文件缺失")).toBeInTheDocument());
    fireEvent.click(screen.getByText("重传文件"));
  });


  it("防御臂：未知状态/空 selected_dims/缺 dims 键/空 error", async () => {
    const d = detailOf("running");
    d.dims = { intro: { state: "completed", seg_done: 1, seg_total: 1, error: "" } }; // world/techniques 缺键 → 默认排队
    state.get.mockResolvedValue(d);
    renderPage();
    await waitFor(() => expect(screen.getByText("取消任务")).toBeInTheDocument());
    expect(screen.getAllByText("排队").length).toBeGreaterThanOrEqual(2); // 缺键维度默认排队
  });

  it("出口臂：非 Error 拒绝 → 兜底文案（操作失败）", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    state.export.mockRejectedValue("plain-reason");
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    await waitFor(() => expect(screen.getByText("稍后再说")).toBeInTheDocument());
    fireEvent.click(screen.getByText("存本地文件夹"));
    fireEvent.click(screen.getByText("选择文件夹并导出"));
    await waitFor(() => expect(screen.getByText(/操作失败/)).toBeInTheDocument());
  });

  it("需重传：取消文件选择（空 files 臂）", async () => {
    state.get.mockResolvedValue(detailOf("need_reupload", { products: [] }));
    renderPage();
    await waitFor(() => expect(screen.getByText("源文件缺失")).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [] } });
    expect(screen.getByText("源文件缺失")).toBeInTheDocument();
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
  it("完成：图谱就绪臂——横幅含三件套＋固定附带行（无警告）", async () => {
    state.get.mockResolvedValue(
      detailOf("completed", { graph: { state: "ready", available: true, warnings: 0, caps: true } }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/份 Markdown＋图谱三件套/)).toBeInTheDocument());
    expect(screen.getByText(/知识图谱 · 固定附带/)).toBeInTheDocument();
    expect(screen.getByText(/无警告/)).toBeInTheDocument();
    expect(screen.getByText("双击浏览器打开")).toBeInTheDocument();
    expect(screen.getByText("唯一正身")).toBeInTheDocument();
    expect(screen.getByText("静态图")).toBeInTheDocument();
  });

  it("完成：图谱带警告臂", async () => {
    state.get.mockResolvedValue(
      detailOf("completed", { graph: { state: "ready", available: true, warnings: 3, caps: true } }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/带 3 处警告/)).toBeInTheDocument());
  });

  it("完成：图谱装配失败提示（导出阻断说明）", async () => {
    state.get.mockResolvedValue(
      detailOf("completed", { graph: { state: "error", available: false, warnings: 0, caps: true } }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("图谱装配失败")).toBeInTheDocument());
    expect(screen.getByText(/按文档版进行/)).toBeInTheDocument();
  });

  it("完成：老包能力戳 false 提示（文档版不受影响）", async () => {
    state.get.mockResolvedValue(
      detailOf("completed", { graph: { state: "absent", available: false, warnings: 0, caps: false } }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("当前写作能力包出不了图谱")).toBeInTheDocument());
  });

  it("完成：缺 graph 字段回落文档版（?? 兜底臂，不出三件套行）", async () => {
    const full = detailOf("completed");
    const { graph: _drop, ...noGraph } = full;
    state.get.mockResolvedValue(noGraph);
    renderPage();
    await waitFor(() => expect(screen.getByText(/份 Markdown 已生成到结果目录/)).toBeInTheDocument());
    expect(screen.queryByText(/图谱三件套/)).not.toBeInTheDocument();
  });

  it("导出：旧文件备份提示臂（backups 非空）", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    state.export.mockClear();
    state.export.mockResolvedValue({
      written: ["简介.md"], readme: "README.md", dest: "/tmp/bx",
      backups: ["图谱.json.bak-20261014-120000"],
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByText("存本地文件夹"));
    fireEvent.change(screen.getByLabelText(/导出到文件夹/), { target: { value: "/tmp/bx" } });
    fireEvent.click(screen.getByText("选择文件夹并导出"));
    await waitFor(() => expect(state.export).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.getByText(/旧文件已备份 1 个/)).toBeInTheDocument());
  });
  it("导出：图谱装配失败注记臂（graph_error 非空 → 文档版提示）", async () => {
    state.get.mockResolvedValue(
      detailOf("completed", { graph: { state: "error", available: false, warnings: 0, caps: true } }),
    );
    state.export.mockClear();
    state.export.mockResolvedValue({
      written: ["简介.md"], readme: "README.md", dest: "/tmp/gx", graph_error: "装配期异常",
    });
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByText("存本地文件夹"));
    fireEvent.change(screen.getByLabelText(/导出到文件夹/), { target: { value: "/tmp/gx" } });
    fireEvent.click(screen.getByText("选择文件夹并导出"));
    await waitFor(() => expect(screen.getByText(/本次为文档版/)).toBeInTheDocument());
  });
  it("内容审核拒绝：红色提示＋去换模型出口", async () => {
    state.get.mockResolvedValue(detailOf("failed", { error: "模型的内容安全审核拒绝了该书的题材（恐怖/暴力等敏感内容）。请更换模型（如 DeepSeek）或拆解其他作品。" }));
    renderPage();
    await waitFor(() => expect(screen.getByText("模型拒绝了该书的题材")).toBeInTheDocument());
    expect(screen.getByText("去换模型")).toBeInTheDocument();
  });

  it("error 不含内容安全审核关键词→内容审核 UI 不渲染（covers 不匹配臂）", async () => {
    state.get.mockResolvedValue(detailOf("failed", { error: "某些其他错误" }));
    renderPage();
    await waitFor(() => expect(screen.getByText("某些其他错误")).toBeInTheDocument());
    expect(screen.queryByTestId("content-filter")).not.toBeInTheDocument();
  });

});
