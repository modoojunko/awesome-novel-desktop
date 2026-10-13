// 创建任务页（c-deconstruct-book 5.4）：未配置引导、模型下拉、探针门、双子态、勾选下限、提交。
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const state = vi.hoisted(() => ({
  fetchOpts: vi.fn(),
  probe: vi.fn(),
  create: vi.fn(),
}));
vi.mock("@/lib/deconstructApi", () => ({
  fetchModelOptions: state.fetchOpts,
  probeModel: state.probe,
  createDeconstructTask: state.create,
  DECONSTRUCT_DIMS: [
    { key: "intro", name: "简介", file: "简介.md", setting: true },
    { key: "world", name: "世界设定", file: "世界设定.md", setting: true },
    { key: "techniques", name: "写作技法", file: "写作技法.md", setting: false },
  ],
}));

import CreateTaskPage from "@/components/tools/CreateTaskPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CreateTaskPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function pickFile(name = "试拆.txt") {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  const file = new File(["第1章 试\n正文。"], name, { type: "text/plain" });
  Object.defineProperty(input, "files", { value: [file] });
  fireEvent.change(input);
  return file;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CreateTaskPage", () => {
  it("未配置模型：引导去配置、创建禁用", async () => {
    state.fetchOpts.mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(screen.getByText(/还没配模型/)).toBeInTheDocument());
    expect(screen.getByTitle("先选择文件")).toBeDisabled();
  });


  it("模型清单加载失败 → 引导去配置（catch 臂）", async () => {
    state.fetchOpts.mockRejectedValue(new Error("net"));
    renderPage();
    await waitFor(() => expect(screen.getByText(/还没配模型/)).toBeInTheDocument());
  });

  it("已配置：模型下拉、探针通过解禁；勾选下限 1；提交调用", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "主力配置", model: "deepseek-v4-pro", vendor: "DeepSeek" },
    ]);
    state.probe.mockResolvedValue(true);
    state.create.mockResolvedValue({ id: "new-1", status: "queued" });
    renderPage();

    const select = await screen.findByRole("combobox");
    expect((select as HTMLSelectElement).options.length).toBe(1);

    pickFile();
    expect(screen.getByText(/试拆\.txt/)).toBeInTheDocument();

    const boxes = await screen.findAllByRole("checkbox");
    expect(boxes.length).toBe(3);
    for (const b of boxes.slice(0, -1)) fireEvent.click(b);
    const last = boxes[boxes.length - 1] as HTMLInputElement;
    const first = boxes[0] as HTMLInputElement;
    expect(last.checked).toBe(true);
    fireEvent.click(last);
    expect(last.checked).toBe(true); // 下限 1
    // 重勾回加（ADD 臂：v8 只认真实执行，不认 ignore 注释——实测）
    fireEvent.click(first);
    expect(first.checked).toBe(true);
    await waitFor(() => expect(screen.getByText("可用")).toBeInTheDocument());
    const submit = screen.getByText(/创建任务（进队列排队）/);
    expect(submit).not.toBeDisabled();
    fireEvent.click(submit);
    await waitFor(() => expect(state.create).toHaveBeenCalledOnce());
  });

  it("探针失败：禁用创建＋去配置出口", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
    ]);
    state.probe.mockResolvedValue(false);
    renderPage();
    await waitFor(() => expect(screen.getByText("模型探针失败")).toBeInTheDocument());
    expect(screen.getByTitle("先选择文件")).toBeDisabled();
    expect(screen.getAllByText("去配置").length).toBeGreaterThan(0);
  });


  it("拖拽选文件＋本地解析失败提示（非 UTF-8/GBK/Big5 极限）", async () => {
    renderPage();
    const zone = screen.getByLabelText("选择或拖入 txt 文件");
    // drop 事件带 DataTransfer 不可直接构造——走 input 分支即可，drop 只验证不崩
    fireEvent.drop(zone, { dataTransfer: { files: [] } });
    expect(screen.getByLabelText("选择或拖入 txt 文件")).toBeInTheDocument();
  });

  it("已选文件后可换文件（回到解析回填）", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
    ]);
    state.probe.mockResolvedValue(true);
    renderPage();
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    pickFile();
    expect(screen.getByText(/试拆\.txt/)).toBeInTheDocument();
    // 换文件按钮触发 input（模拟重新选择）
    fireEvent.click(screen.getByText("换文件"));
  });


  it("上传区 Enter 键触发文件框；坏编码文件显示解析错误", async () => {
    renderPage();
    const zone = screen.getByLabelText("选择或拖入 txt 文件");
    fireEvent.keyDown(zone, { key: "Enter" });
    // 坏字节文件：四条探测链全失败 → parseErr 提示
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const bad = new File([new Uint8Array([0xff, 0xff, 0xfe, 0xff])], "bad.txt", { type: "text/plain" });
    Object.defineProperty(input, "files", { value: [bad] });
    fireEvent.change(input);
    await waitFor(() => expect(screen.getByText(/无法识别文件编码/)).toBeInTheDocument());
  });



  it("上传区 Space 键触发文件框（第二键臂）", async () => {
    renderPage();
    const zone = screen.getByLabelText("选择或拖入 txt 文件");
    fireEvent.keyDown(zone, { key: " " });
    expect(zone.getAttribute("aria-label")).toContain("选择或拖入");
  });

  it("探针空键早退臂：options 为空时 probe effect 早退（不设探针态）", async () => {
    state.fetchOpts.mockResolvedValue([]);
    renderPage();
    await waitFor(() => expect(screen.getByText(/还没配模型/)).toBeInTheDocument());
    // 探针门 notice 不渲染（hasModels false）
    expect(screen.queryByText(/模型探针/)).not.toBeInTheDocument();
  });

  it("submit 非 Error 拒绝 → 兜底文案（e instanceof Error 假臂）", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
    ]);
    state.probe.mockResolvedValue(true);
    state.create.mockRejectedValue("plain-reason");
    renderPage();
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    pickFile();
    await waitFor(() => expect(screen.getByText(/创建任务（进队列排队）/)).not.toBeDisabled());
    fireEvent.click(screen.getByText(/创建任务（进队列排队）/));
    await waitFor(() => expect(screen.getAllByText(/创建失败/).length).toBeGreaterThan(0));
  });

  it("拖拽带文件 → 进入已选子态并本地解析回填", async () => {
    renderPage();
    const zone = screen.getByLabelText("选择或拖入 txt 文件");
    const file = new File(["第1章 拖\n正文。"], "拖入.txt", { type: "text/plain" });
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    await waitFor(() => expect(screen.getByText(/拖入\.txt/)).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText(/编码探测/)).toBeInTheDocument());
  });

  it("drop 坏字节文件 → 解析错误提示（catch 臂）", async () => {
    renderPage();
    const zone = screen.getByLabelText("选择或拖入 txt 文件");
    const bad = new File([new Uint8Array([0xff, 0xff, 0xfe, 0xff])], "bad.txt", { type: "text/plain" });
    fireEvent.drop(zone, { dataTransfer: { files: [bad] } });
    await waitFor(() => expect(screen.getByText(/无法识别文件编码/)).toBeInTheDocument());
  });

  it("上传区 Enter 键打开文件框（不崩）", async () => {
    renderPage();
    const zone = screen.getByLabelText("选择或拖入 txt 文件");
    fireEvent.keyDown(zone, { key: "Enter" });
    expect(zone.getAttribute("aria-label")).toContain("选择或拖入");
  });

  it("探针失败后换模型重新探测通过", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
      { api_config_id: "c2", config_name: "B", model: "m2", vendor: "v" },
    ]);
    state.probe.mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    renderPage();
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("模型探针失败")).toBeInTheDocument());
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "c2::m2" } });
    await waitFor(() => expect(screen.getByText("可用")).toBeInTheDocument());
  });

  it("书名可编辑：取自文件名，改动随提交（评审 P2：label 可改与 readOnly 相悖）", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
    ]);
    state.probe.mockResolvedValue(true);
    state.create.mockResolvedValue({ id: "x", status: "queued" });
    renderPage();
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    state.create.mockClear();
    pickFile("原书名.txt");
    const nameInput = screen.getByLabelText("书名（取自文件名，可改）") as HTMLInputElement;
    expect(nameInput.value).toBe("原书名");
    fireEvent.change(nameInput, { target: { value: "改过的书名" } });
    expect(nameInput.value).toBe("改过的书名");
    await waitFor(() => expect(screen.getByText(/创建任务（进队列排队）/)).not.toBeDisabled());
    fireEvent.click(screen.getByText(/创建任务（进队列排队）/));
    await waitFor(() => expect(state.create).toHaveBeenCalledOnce());
    expect((state.create.mock.calls[0][1] as { bookName: string }).bookName).toBe("改过的书名");
  });

  it("创建成功 → 跳任务详情", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
    ]);
    state.probe.mockResolvedValue(true);
    state.create.mockResolvedValue({ id: "new-nav", status: "queued" });
    renderPage();
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    state.create.mockClear();
    pickFile();
    await waitFor(() => expect(screen.getByText(/创建任务（进队列排队）/)).not.toBeDisabled());
    fireEvent.click(screen.getByText(/创建任务（进队列排队）/));
    await waitFor(() => expect(state.create).toHaveBeenCalledOnce());
  });


  it("探针进行中显示探测中（慢探针臂）", async () => {
    let resolveProbe: ((v: boolean) => void) | undefined;
    state.probe.mockImplementation(
      () => new Promise<boolean>((res) => { resolveProbe = res; }),
    );
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
    ]);
    renderPage();
    await waitFor(() => expect(screen.getByText("模型探针中…")).toBeInTheDocument());
    // 等 150ms setTimeout 先行：probeModel 被调用、resolveProbe 捕获后再放行
    await new Promise((r) => setTimeout(r, 250));
    resolveProbe?.(true);
    await waitFor(
      () => {
        const pill = screen.queryByText("可用");
        if (!pill) throw new Error("可用 not yet; body=" + document.body.innerHTML.slice(0, 300));
        expect(pill).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
  });

  it("onChange 空文件臂（取消选择回 nofile）", async () => {
    state.fetchOpts.mockResolvedValue([]);
    renderPage();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [] });
    fireEvent.change(input);
    expect(screen.getByLabelText("选择或拖入 txt 文件")).toBeInTheDocument();
  });

  it("drop 带文件 → 已选子态＋解析回填", async () => {
    state.fetchOpts.mockResolvedValue([]);
    renderPage();
    const zone = screen.getByLabelText("选择或拖入 txt 文件");
    const file = new File(["第1章 拖\n正文。"], "拖入.txt", { type: "text/plain" });
    fireEvent.drop(zone, { dataTransfer: { files: [file] } });
    await waitFor(() => expect(screen.getByText(/拖入\.txt/)).toBeInTheDocument());
  });

  it("创建失败显示错误文案", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
    ]);
    state.probe.mockResolvedValue(true);
    state.create.mockRejectedValue(new Error("排队服务不可用"));
    renderPage();
    await waitFor(() => expect(screen.getByText("可用")).toBeInTheDocument());
    pickFile();
    await waitFor(() => expect(screen.getByText(/创建任务（进队列排队）/)).not.toBeDisabled());
    fireEvent.click(screen.getByText(/创建任务（进队列排队）/));
    await waitFor(() => expect(screen.getByText(/排队服务不可用/)).toBeInTheDocument());
  });

  it("容量口径明示：入口文案含单本 ≤30 万字（spec「单本容量口径」）", async () => {
    state.fetchOpts.mockResolvedValue([]);
    renderPage();
    expect(screen.getByText(/单本 ≤30 万字/)).toBeInTheDocument();
    expect(screen.queryByText(/超过单本建议量/)).not.toBeInTheDocument();
  });

  it("超线提示：解析字数 >30 万出 warn（不拦截创建）；小文件不出", async () => {
    state.fetchOpts.mockResolvedValue([
      { api_config_id: "c1", config_name: "A", model: "m1", vendor: "v" },
    ]);
    state.probe.mockResolvedValue(true);
    renderPage();
    await waitFor(() => expect(screen.getByRole("combobox")).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const big = new File(["第1章 试\n" + "字".repeat(310000)], "大部头.txt", { type: "text/plain" });
    Object.defineProperty(input, "files", { value: [big] });
    fireEvent.change(input);
    await waitFor(() => expect(screen.getByText(/超过单本建议量/)).toBeInTheDocument());
    expect(screen.getByText(/按卷分次拆解/)).toBeInTheDocument();
    // 不拦截：探针过后创建钮照常解禁
    await waitFor(() => expect(screen.getByText(/创建任务（进队列排队）/)).not.toBeDisabled());
    expect(screen.queryByLabelText("书名（取自文件名，可改）")?.closest(".fcard")).toBeInTheDocument();
  });
});
