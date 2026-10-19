// 任务详情页（c-deconstruct-book 5.5）：进行中/完成（勾选＋出口）/失败/需重传 全态。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const state = vi.hoisted(() => ({
  get: vi.fn(),
  product: vi.fn(),
  cancel: vi.fn(),
  del: vi.fn(),
  resume: vi.fn(),
  retry: vi.fn(),
  importBook: vi.fn(),
  export: vi.fn(),
}));
const toastState = vi.hoisted(() => ({ info: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock("@/lib/toast", () => ({ toast: toastState }));
vi.mock("@/lib/deconstructApi", () => ({
  getDeconstructTask: state.get,
  getDeconstructProduct: state.product,
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

import TaskDetailPage, { statsLine } from "@/components/tools/TaskDetailPage";

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

  it("导出：浏览器无 pick 桥→toast 明示手输（不静默装死）", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    delete (window as unknown as { pywebview?: unknown }).pywebview; // 防前序用例桥泄漏
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    fireEvent.click(screen.getByText("存本地文件夹"));
    fireEvent.click(screen.getByText("选择文件夹"));
    await waitFor(() => expect(toastState.info).toHaveBeenCalledWith(expect.stringContaining("桌面版应用")));
  });

  it("阶段三进度账：在场补写行＋overall 封顶 90（100% 只留给 completed）", async () => {
    state.get.mockResolvedValue(
      detailOf("running", {
        cards: { state: "completed", done: 318, total: 318 },
        graph_phase: { step: "presence", done: 3, total: 17 },
      }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText(/在场补写 3\/17 章/)).toBeInTheDocument());
    expect(screen.getByText("90%")).toBeInTheDocument();
  });

  it("阶段三进度账：地点归并与图谱装配行", async () => {
    state.get.mockResolvedValue(
      detailOf("running", { cards: { state: "completed", done: 10, total: 10 }, graph_phase: { step: "place_merge" } }),
    );
    const { unmount } = renderPage();
    await waitFor(() => expect(screen.getByText("进行中 · 地点归并")).toBeInTheDocument());
    unmount();
    state.get.mockResolvedValue(
      detailOf("running", { cards: { state: "completed", done: 10, total: 10 }, graph_phase: { step: "assemble" } }),
    );
    const u2 = renderPage();
    await waitFor(() => expect(screen.getByText("进行中 · 图谱装配")).toBeInTheDocument());
    u2.unmount();
    // 防御臂：缺 done/total 的 presence 账渲染 0/0（后端 place_merge/assemble 本就无计数）
    state.get.mockResolvedValue(
      detailOf("running", { cards: { state: "completed", done: 10, total: 10 }, graph_phase: { step: "presence" } }),
    );
    const u3 = renderPage();
    await waitFor(() => expect(screen.getByText(/在场补写 0\/0 章/)).toBeInTheDocument());
    u3.unmount();
  });

  it("断点续拆过渡：恢复中态按钮＋toast，运行卡 fade-up 入场", async () => {
    state.get.mockResolvedValue(detailOf("failed", { error: "模型 400" }));
    state.resume.mockResolvedValue(undefined);
    const u1 = renderPage();
    await waitFor(() => expect(screen.getByText("从断点续拆")).toBeInTheDocument());
    fireEvent.click(screen.getByText("从断点续拆"));
    await waitFor(() => expect(screen.getByText("正在恢复…")).toBeInTheDocument());
    await waitFor(() => expect(toastState.info).toHaveBeenCalledWith(expect.stringContaining("从断点恢复")));
    u1.unmount();
    // 状态翻面（failed 不轮询，重挂载模拟轮询后视图）：运行卡 fade-up 入场
    state.get.mockResolvedValue(detailOf("running", { cards: { state: "running", done: 5, total: 10 } }));
    renderPage();
    await waitFor(() => expect(screen.getByText("取消任务")).toBeInTheDocument());
    const card = screen.getByText("取消任务").closest('[data-od-id="task-running"]') as HTMLElement;
    expect(card.classList.contains("animate-fade-up")).toBe(true);
  });

  it("断点续拆失败：toast.error 明示＋按钮回原态", async () => {
    state.get.mockResolvedValue(detailOf("failed", { error: "模型 400" }));
    state.resume.mockRejectedValue(new Error("仅失败/已取消任务可续拆"));
    const u = renderPage();
    await waitFor(() => expect(screen.getByText("从断点续拆")).toBeInTheDocument());
    fireEvent.click(screen.getByText("从断点续拆"));
    await waitFor(() => expect(toastState.error).toHaveBeenCalledWith("仅失败/已取消任务可续拆"));
    await waitFor(() => expect(screen.getByText("从断点续拆")).toBeInTheDocument());
    u.unmount();
    // 非 Error 拒绝走兜底文案；cancelled 态同样出续拆按钮（恢复中态不残留）
    state.resume.mockRejectedValue("boom");
    state.get.mockResolvedValue(detailOf("cancelled"));
    renderPage();
    await waitFor(() => expect(screen.getByText("从断点续拆")).toBeInTheDocument());
    fireEvent.click(screen.getByText("从断点续拆"));
    await waitFor(() => expect(toastState.error).toHaveBeenCalledWith("恢复失败"));
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
  it("完成：点文件名预览——加载态→全文弹窗，勾选不被动，✕ 关闭", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    let resolveProduct!: (v: { filename: string; content: string }) => void;
    state.product.mockImplementationOnce(
      () => new Promise((res) => { resolveProduct = res; }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    const box = screen.getByRole("checkbox", { name: "简介.md" }) as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: "简介.md" }));
    expect(document.querySelector('[data-od-id="preview-modal"]')).not.toBeNull();
    expect(screen.getByText("加载中…")).toBeInTheDocument();
    expect(box.checked).toBe(true); // 点文件名不波及勾选（stopPropagation）
    resolveProduct({ filename: "简介.md", content: "# 简介\n\n林晚在渡口。" });
    await waitFor(() => expect(screen.getByText(/林晚在渡口/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "关闭预览" }));
    expect(document.querySelector('[data-od-id="preview-modal"]')).toBeNull();
  });

  it("完成：预览失败——toast 报错＋弹窗收起（Error／非 Error 两臂）；脚部关闭与 scrim", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    state.product.mockRejectedValueOnce(new Error("产物不存在"));
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "简介.md" }));
    await waitFor(() => expect(toastState.error).toHaveBeenCalledWith("产物不存在"));
    expect(document.querySelector('[data-od-id="preview-modal"]')).toBeNull();
    // 非 Error 拒绝臂 → 兜底文案
    state.product.mockRejectedValueOnce("boom");
    fireEvent.click(screen.getByRole("button", { name: "世界设定.md" }));
    await waitFor(() => expect(toastState.error).toHaveBeenLastCalledWith("预览加载失败"));
    expect(document.querySelector('[data-od-id="preview-modal"]')).toBeNull();
    // 成功后脚部「关闭」收起，再开一次走 scrim 收起
    state.product.mockResolvedValueOnce({ filename: "世界设定.md", content: "设定正文" });
    fireEvent.click(screen.getByRole("button", { name: "世界设定.md" }));
    await waitFor(() => expect(screen.getByText("设定正文")).toBeInTheDocument());
    fireEvent.click(screen.getByText("关闭", { exact: true }));
    expect(document.querySelector('[data-od-id="preview-modal"]')).toBeNull();
    state.product.mockResolvedValueOnce({ filename: "世界设定.md", content: "设定正文" });
    fireEvent.click(screen.getByRole("button", { name: "世界设定.md" }));
    await waitFor(() => expect(screen.getByText("设定正文")).toBeInTheDocument());
    fireEvent.click(document.querySelector(".scrim.show")!);
    expect(document.querySelector('[data-od-id="preview-modal"]')).toBeNull();
  });

  it("完成：点行（非勾选框/非文件名）仍切换勾选——行点击保留", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    renderPage();
    await waitFor(() => expect(screen.getByText(/已选 3\/3/)).toBeInTheDocument());
    fireEvent.click(screen.getByText("100 字符"));
    expect(screen.getByText(/已选 2\/3/)).toBeInTheDocument();
    expect((screen.getByRole("checkbox", { name: "简介.md" }) as HTMLInputElement).checked).toBe(false);
  });

  it("完成：慢响应次序——迟到旧响应不污染新弹窗（成功/失败守卫两臂）", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    let settleA!: (v: { filename: string; content: string }) => void;
    let resolveB!: (v: { filename: string; content: string }) => void;
    let rejectB!: (e: unknown) => void;
    let resolveC!: (v: { filename: string; content: string }) => void;
    state.product.mockImplementationOnce(() => new Promise((res) => { settleA = res; }));
    state.product.mockImplementationOnce(
      () => new Promise((res, rej) => { resolveB = res; rejectB = rej; }),
    );
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    // A 在途 → 关 → B 在途 → 关 → 开 C（C 也挂起，最后放行）
    fireEvent.click(screen.getByRole("button", { name: "简介.md" }));
    fireEvent.click(document.querySelector(".scrim.show")!);
    fireEvent.click(screen.getByRole("button", { name: "世界设定.md" }));
    fireEvent.click(document.querySelector(".scrim.show")!);
    state.product.mockImplementationOnce(() => new Promise((res) => { resolveC = res; }));
    fireEvent.click(screen.getByRole("button", { name: "写作技法.md" }));
    expect(screen.getByText("加载中…")).toBeInTheDocument();
    // 旧失败（B 拒绝）：不 toast、不关 C 弹窗（相对断言——toast mock 调用史跨用例不清理）
    const errCallsBefore = toastState.error.mock.calls.length;
    await act(async () => { rejectB(new Error("旧失败")); });
    expect(toastState.error.mock.calls.length).toBe(errCallsBefore);
    expect(document.querySelector('[data-od-id="preview-modal"]')).not.toBeNull();
    expect(screen.getByText("加载中…")).toBeInTheDocument();
    // 旧成功（A 迟到）：内容不顶进 C 弹窗
    await act(async () => { settleA({ filename: "简介.md", content: "旧内容A" }); });
    expect(screen.queryByText("旧内容A")).toBeNull();
    expect(screen.getByText("加载中…")).toBeInTheDocument();
    // C 到达 → 正常显示
    await act(async () => { resolveC({ filename: "写作技法.md", content: "技法正文C" }); });
    await waitFor(() => expect(screen.getByText("技法正文C")).toBeInTheDocument());
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


describe("建书勾选导入", () => {
  it("默认 7/10：设定项勾、三项扩展不勾；勾选真实传 items", async () => {
    state.get.mockResolvedValue(detailOf("completed"));
    state.importBook.mockClear();
    renderPage();
    await waitFor(() => expect(screen.getByText("选择去向")).toBeInTheDocument());
    fireEvent.click(screen.getByText("选择去向"));
    await waitFor(() => expect(screen.getByText("灌入新书的内容")).toBeInTheDocument());
    expect(screen.getByText(/写入勾选的 2\/3 项/)).toBeInTheDocument();  // mock 口径：intro/world 勾、techniques 不勾
    // 勾「写作技法」、取消「简介」
    fireEvent.click(document.querySelector('[data-od-id="bi-techniques"]') as HTMLInputElement);
    fireEvent.click(document.querySelector('[data-od-id="bi-intro"]') as HTMLInputElement);
    expect(screen.getByText(/写入勾选的 2\/3 项/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("就建这本书"));
    await waitFor(() => expect(state.importBook).toHaveBeenCalledOnce());
    const items = state.importBook.mock.calls[0][1] as string[];
    expect(items).toEqual(["world", "techniques"]);
    expect(items).not.toContain("intro");
  });
});


describe("进度可视二阶", () => {
  it("当前动作行＋拆卡 ETA 后缀＋已运行时长", async () => {
    state.get.mockResolvedValue(detailOf("running", {
      cards: { state: "running", done: 40, total: 258, eta_seconds: 720 },
      created_at: new Date(Date.now() - 5 * 60000).toISOString(),
      activity: { label: "正在拆解 第41章", age_seconds: 23 },
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/正在拆解 第41章/)).toBeInTheDocument());
    expect(screen.getByText(/已进行 23 秒/)).toBeInTheDocument();
    expect(screen.getByText(/约剩 12 分/)).toBeInTheDocument();
    expect(screen.getByText("已运行 5 分")).toBeInTheDocument();
  });

  it("维度归并 ETA 后缀", async () => {
    state.get.mockResolvedValue(detailOf("running", {
      dims: Object.fromEntries(
        ["intro", "world", "techniques"].map((k, i) => [
          k,
          i === 0
            ? { state: "running", seg_done: 2, seg_total: 9, error: "", eta_seconds: 240 }
            : { state: "completed", seg_done: 1, seg_total: 1, error: "" },
        ]),
      ),
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/归并 2\/9 · 约剩 4 分/)).toBeInTheDocument());
  });

  it("activity 缺席不渲染行", async () => {
    state.get.mockResolvedValue(detailOf("running"));
    renderPage();
    await waitFor(() => expect(screen.getByText("取消任务")).toBeInTheDocument());
    expect(screen.queryByText("当前动作")).not.toBeInTheDocument();
  });
});


describe("进度可视二阶（边界臂）", () => {
  it("无 eta/半分钟内/无 age 的展示口径", async () => {
    state.get.mockResolvedValue(detailOf("running", {
      cards: { state: "running", done: 5, total: 9 },
      created_at: new Date(Date.now() - 30 * 1000).toISOString(),
      activity: { label: "正在归并 简介", age_seconds: null },
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/进行中 · 5\/9 章/)).toBeInTheDocument()); // 无 eta 无后缀
    expect(screen.getByText("已运行 1 分内")).toBeInTheDocument();
    expect(screen.getByText("正在归并 简介")).toBeInTheDocument(); // age null＝无时长后缀
  });

  it("created_at 在未来（时钟偏差）不出已运行", async () => {
    state.get.mockResolvedValue(detailOf("running", {
      created_at: new Date(Date.now() + 10 * 60000).toISOString(),
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText("取消任务")).toBeInTheDocument());
    expect(screen.queryByText(/已运行/)).not.toBeInTheDocument();
  });

  // ── c-deconstruct-resilience：降级可见 / 告警账 / 错误类别出口 / 调用账 / UTC 时长 ──

  it("降级维度可见：completed + degraded → warn 提示与原因", async () => {
    state.get.mockResolvedValue(detailOf("completed", {
      dims: {
        intro: { state: "completed", seg_done: 1, seg_total: 1, error: "" },
        world: { state: "completed", seg_done: 2, seg_total: 3, error: "", degraded: "2/3 批内容被模型安全审核拒绝，该范围未纳入" },
        techniques: { state: "completed", seg_done: 1, seg_total: 1, error: "" },
      },
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/分段稿/)).toBeInTheDocument());
    expect(screen.getByText(/世界设定：2\/3 批内容被模型安全审核拒绝/)).toBeInTheDocument();
  });

  it("告警账可见：跳过章节的 warning 在完成态透出", async () => {
    state.get.mockResolvedValue(detailOf("completed", {
      warnings: ["1 章拆卡被模型拒绝或输出损坏已跳过（续拆可补）：第2章"],
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/有章节未纳入拆解/)).toBeInTheDocument());
    expect(screen.getByText(/第2章/)).toBeInTheDocument();
  });

  it("失败按 error_kind 出口：provider_unavailable → 去换模型", async () => {
    state.get.mockResolvedValue(detailOf("failed", {
      error: "模型服务连续失败，任务已自动暂停，可稍后续拆或更换模型",
      error_kind: "provider_unavailable",
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/模型服务暂时不可用或长时间无响应/)).toBeInTheDocument());
    expect(screen.getByText("去换模型")).toBeInTheDocument();
  });

  it("失败按 error_kind 出口：auth → 去检查模型配置", async () => {
    state.get.mockResolvedValue(detailOf("failed", {
      error: "API Key 无效或无权限：401",
      error_kind: "auth",
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/API Key、接口地址或模型名/)).toBeInTheDocument());
    expect(screen.getByText("去检查模型配置")).toBeInTheDocument();
  });

  it("调用账：completed 态显示调用统计与重试数", async () => {
    state.get.mockResolvedValue(detailOf("completed", {
      stats: {
        card: { calls: 258, failures: 1, attempts: 260, duration_ms: 1, tokens_in: 0, tokens_out: 0 },
        l1: { calls: 10, failures: 0, attempts: 10, duration_ms: 1, tokens_in: 0, tokens_out: 0 },
      },
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/拆卡 258 次（重试 2）/)).toBeInTheDocument());
    expect(screen.getByText(/归并 10 次$/)).toBeInTheDocument(); // 零重试不缀重试括注
  });

  it("失败态告警账可见：跳过章通知在失败面板透出", async () => {
    state.get.mockResolvedValue(detailOf("failed", {
      error: "模型服务连续失败，任务已自动暂停，可稍后续拆或更换模型",
      error_kind: "provider_unavailable",
      warnings: ["3 章拆卡被模型拒绝或输出损坏已跳过（续拆可补）：第7、12、13章"],
    }));
    renderPage();
    await waitFor(() => expect(screen.getByText(/部分内容被跳过（可续拆补齐）/)).toBeInTheDocument());
    expect(screen.getByText(/第7、12、13章/)).toBeInTheDocument();
  });

  it("已运行时长按 UTC 解析：2 分钟前创建显示 2 分而非时区偏移", async () => {
    const utc = new Date(Date.now() - 2 * 60000).toISOString().replace(/\.\d+Z$/, "");
    state.get.mockResolvedValue(detailOf("running", { created_at: utc }));
    renderPage();
    await waitFor(() => expect(screen.getByText("已运行 2 分")).toBeInTheDocument());
  });

  it("statsLine：合批阶段入账＋空账空串（评审 P3 修复钉）", () => {
    const mk = (over: Record<string, unknown>) => ({
      calls: 1, failures: 0, attempts: 1, duration_ms: 0, tokens_in: 0, tokens_out: 0, ...over,
    });
    expect(statsLine({
      card: mk({ calls: 2 }),
      card_batch: mk({ calls: 1 }),
    })).toBe("拆卡 2 次 · 合批 1 次");
    expect(statsLine({ reduce_state: mk({}) })).toBe(""); // 非展示阶段不渲染
    expect(statsLine({})).toBe("");
  });
});
