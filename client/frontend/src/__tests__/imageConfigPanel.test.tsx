import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ImageConfigPanel from "@/components/image/ImageConfigPanel";

const cfg = {
  id: "i1", name: "封面主力", provider: "volcengine",
  base_url: "https://ark.test/api/v3", api_key_masked: "sk-****1",
  default_model: "doubao-seedream", models: ["doubao-seedream"],
  declared_capabilities: {}, is_default: true, status: "active" as const,
};

const api = vi.hoisted(() => ({
  listConfigs: vi.fn(async () => [cfg]),
  createConfig: vi.fn(async () => ({ ...cfg, id: "i2", name: "新配置", is_default: false })),
  updateConfig: vi.fn(async () => cfg),
  deleteConfig: vi.fn(async () => ({ id: "i1", status: "deleted", default_image_config_id: null })),
  restoreConfig: vi.fn(async () => cfg),
}));

vi.mock("@/lib/imageApi", () => ({ imageApi: api, IMAGE_PROVIDERS: [] }));
vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("ImageConfigPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("列出配置并可新增", async () => {
    render(<ImageConfigPanel />);
    await waitFor(() => expect(screen.getByText("封面主力")).toBeTruthy());
    fireEvent.click(screen.getByText("添加图像模型"));
    await waitFor(() => expect(screen.getByRole("heading", { name: "添加图像模型" })).toBeTruthy());
    fireEvent.change(screen.getByPlaceholderText("例如：封面主力 · 火山"), { target: { value: "新配置" } });
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("保存"));
    await waitFor(() => expect(api.createConfig).toHaveBeenCalled());
    expect(
      (api.createConfig.mock.calls[0] as unknown as [Record<string, unknown>])[0].name,
    ).toBe("新配置");
  });

  it("删除后出现撤销入口并调用恢复", async () => {
    render(<ImageConfigPanel />);
    await waitFor(() => expect(screen.getByText("封面主力")).toBeTruthy());
    fireEvent.click(screen.getByText("删除"));
    await waitFor(() => expect(screen.getByText("删除图像模型")).toBeTruthy());
    fireEvent.click(within(document.querySelector(".mcard-foot") as HTMLElement).getByText("删除"));
    await waitFor(() => expect(api.deleteConfig).toHaveBeenCalledWith("i1"));
    await waitFor(() => expect(screen.getByText(/已删除「封面主力」/)).toBeTruthy());
    fireEvent.click(screen.getByText("撤销"));
    await waitFor(() => expect(api.restoreConfig).toHaveBeenCalledWith("i1"));
  });
});
