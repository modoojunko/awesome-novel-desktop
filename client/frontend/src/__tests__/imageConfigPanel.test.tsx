import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ImageConfigPanel from "@/components/image/ImageConfigPanel";

const cfg = {
  id: "i1", name: "封面主力", provider: "volcengine",
  base_url: "https://ark.test/api/v3", api_key_masked: "sk-****1",
  default_model: "doubao-seedream", models: ["doubao-seedream"],
  declared_capabilities: {}, is_default: true, status: "active" as const,
  last_test_status: null as string | null,
  last_test_error: null as string | null,
};

const api = vi.hoisted(() => ({
  listConfigs: vi.fn(async () => [cfg]),
  createConfig: vi.fn(async () => ({ ...cfg, id: "i2", name: "新配置", is_default: false })),
  updateConfig: vi.fn(async () => cfg),
  deleteConfig: vi.fn(async () => ({ id: "i1", status: "deleted", default_image_config_id: null })),
  restoreConfig: vi.fn(async () => cfg),
  testConfig: vi.fn(async (): Promise<{
    ok: boolean; model: string; elapsed_ms: number;
    error?: { kind: string; message: string } | null;
  }> => ({ ok: true, model: "doubao-seedream", elapsed_ms: 1200 })),
}));

vi.mock("@/lib/imageApi", () => ({ imageApi: api, IMAGE_PROVIDERS: [] }));
vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

function openAddDialog() {
  fireEvent.click(screen.getByText("添加图像模型"));
  return waitFor(() => expect(screen.getByRole("heading", { name: "添加图像模型" })).toBeTruthy());
}

describe("ImageConfigPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("列出配置并可新增", async () => {
    render(<ImageConfigPanel />);
    await waitFor(() => expect(screen.getByText("封面主力")).toBeTruthy());
    await openAddDialog();
    fireEvent.change(screen.getByPlaceholderText("例如：封面主力 · 火山"), { target: { value: "新配置" } });
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("保存"));
    await waitFor(() => expect(api.createConfig).toHaveBeenCalled());
    expect(
      (api.createConfig.mock.calls[0] as unknown as [Record<string, unknown>])[0].name,
    ).toBe("新配置");
  });

  it("表单为单模型格：无「模型清单」输入，提交不带 models", async () => {
    render(<ImageConfigPanel />);
    await waitFor(() => expect(screen.getByText("封面主力")).toBeTruthy());
    await openAddDialog();
    expect(screen.getByText("模型")).toBeTruthy();
    expect(screen.queryByText("模型清单")).toBeNull();
    expect(screen.queryByText(/后续版本开放/)).toBeNull();
    fireEvent.change(screen.getByPlaceholderText("例如：封面主力 · 火山"), { target: { value: "新配置" } });
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("保存"));
    await waitFor(() => expect(api.createConfig).toHaveBeenCalled());
    const body = (api.createConfig.mock.calls[0] as unknown as [Record<string, unknown>])[0];
    expect("models" in body).toBe(false);
    expect(body.default_model).toBeDefined();
  });

  it("编辑保存同样不带 models（清单由后端派生）", async () => {
    render(<ImageConfigPanel />);
    await waitFor(() => expect(screen.getByText("封面主力")).toBeTruthy());
    fireEvent.click(screen.getByText("编辑"));
    await waitFor(() => expect(screen.getByRole("heading", { name: "编辑图像模型" })).toBeTruthy());
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("保存"));
    await waitFor(() => expect(api.updateConfig).toHaveBeenCalled());
    const [, body] = api.updateConfig.mock.calls[0] as unknown as [string, Record<string, unknown>];
    expect("models" in body).toBe(false);
  });

  it("测试连接成功：呈现通过与耗时，不落清单格", async () => {
    render(<ImageConfigPanel />);
    await waitFor(() => expect(screen.getByText("封面主力")).toBeTruthy());
    await openAddDialog();
    fireEvent.change(screen.getByPlaceholderText("模型 id"), { target: { value: "m-1" } });
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("测试连接"));
    await waitFor(() => expect(api.testConfig).toHaveBeenCalled());
    const body = (api.testConfig.mock.calls[0] as unknown as [Record<string, unknown>])[0];
    expect(body.default_model).toBe("m-1");
    expect("config_id" in body).toBe(false); // 新建态不落库
    const res = await waitFor(() => document.querySelector(".tresult.ok") as HTMLElement);
    expect(res.textContent).toContain("测试通过");
    expect(res.textContent).toContain("1.2s");
  });

  it("测试连接失败：呈现供应商错误摘要", async () => {
    api.testConfig.mockResolvedValueOnce({
      ok: false, model: "m-1", elapsed_ms: 300,
      error: { kind: "auth", message: "API Key 无效或无权限" },
    });
    render(<ImageConfigPanel />);
    await waitFor(() => expect(screen.getByText("封面主力")).toBeTruthy());
    await openAddDialog();
    fireEvent.change(screen.getByPlaceholderText("模型 id"), { target: { value: "m-1" } });
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("测试连接"));
    await waitFor(() => expect(screen.getByText(/测试失败/)).toBeTruthy());
    expect(screen.getByText(/API Key 无效或无权限/)).toBeTruthy();
  });

  it("测试过于频繁（429）：呈现节流提示而非裸报错", async () => {
    api.testConfig.mockRejectedValueOnce(new Error("测试过于频繁，请 31 秒后再试"));
    render(<ImageConfigPanel />);
    await waitFor(() => expect(screen.getByText("封面主力")).toBeTruthy());
    await openAddDialog();
    fireEvent.change(screen.getByPlaceholderText("模型 id"), { target: { value: "m-1" } });
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("测试连接"));
    await waitFor(() => expect(screen.getByText(/测试过于频繁/)).toBeTruthy());
  });

  it("卡片：模型单行显示＋测试状态胶囊（通过/失败/未测试）", async () => {
    // listConfigs 的 useEffect 只在挂载时跑：换 key 强制重挂来消费下一个 mock 值
    const { rerender } = render(<ImageConfigPanel key="v0" />);
    await waitFor(() => expect(screen.getByText("模型：doubao-seedream")).toBeTruthy());
    expect(document.querySelector(".m-chip")).toBeNull();
    expect(screen.getByText("未测试")).toBeTruthy();

    api.listConfigs.mockResolvedValueOnce([{ ...cfg, last_test_status: "ok" }]);
    rerender(<ImageConfigPanel key="v1" />);
    await waitFor(() => expect(screen.getByText("测试通过")).toBeTruthy());

    api.listConfigs.mockResolvedValueOnce([
      { ...cfg, last_test_status: "failed", last_test_error: "Key 无效" },
    ]);
    rerender(<ImageConfigPanel key="v2" />);
    await waitFor(() => expect(screen.getByText("测试失败")).toBeTruthy());
    expect((screen.getByTitle("Key 无效")).textContent).toBe("测试失败");
  });
});
