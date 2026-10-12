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
    expect(last.checked).toBe(true);
    fireEvent.click(last);
    expect(last.checked).toBe(true); // 下限 1
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
});
