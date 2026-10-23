import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ImageWorkshopModal from "@/components/image/ImageWorkshopModal";

const candidate = {
  asset_id: "a-candidate", url: "/api/image-assets/a-candidate?variant=full",
  thumb_url: "/api/image-assets/a-candidate?variant=thumb", width: 768, height: 1024,
  version: 1, source: "upload", status: "candidate" as const, novel_id: "n1",
  kind: "cover" as const, mime: "image/webp", bytes: 10, expires_at: null,
  undo_expires_at: null,
};

const api = vi.hoisted(() => ({
  mediaUrl: (p: string) => p,
  refreshLinks: vi.fn(async () => ({ links: { full: "/f", thumb: "/t" }, url_expires_at: "" })),
  listAssets: vi.fn(async () => [candidate]),
  getBookSettings: vi.fn(async () => ({
    novel_id: "n1", style_key: "ink", cover_prompt: "", cover_seed: null,
    image_config_id: null, image_model: "", effective_image_config_id: null,
    effective_image_model: "seedream", effective_source: "default" as const,
  })),
  getCharacterSettings: vi.fn(),
  coverPrompt: vi.fn(async () => ({
    kind: "cover", prompt: "prompt", negative_prompt: "negative", prompt_hash: "h",
    prompt_template_version: 3, style_key: "ink", size: { width: 768, height: 1024 },
    seed: 1, candidate_seeds: [1, 2], model: "seedream", model_unbound: false,
    provider: "volcengine", capabilities: {}, sources: {},
  })),
  avatarPrompt: vi.fn(),
  uploadAsset: vi.fn(async () => candidate),
  adoptAsset: vi.fn(async () => ({ ...candidate, status: "current", undo_token: "tok", undo_expires_at: new Date(Date.now() + 8000).toISOString() })),
  undoAsset: vi.fn(async () => ({ restored_asset_id: null, removed_asset_id: "a-candidate" })),
  deleteAsset: vi.fn(async () => ({ deleted_asset_id: "a-candidate" })),
  patchBookSettings: vi.fn(async () => ({})),
  patchCharacterSettings: vi.fn(async () => ({})),
}));

vi.mock("@/lib/imageApi", () => ({ imageApi: api, IMAGE_PROVIDERS: [] }));
vi.mock("@/hooks/useTier", () => ({ useTier: () => ({ isPro: false, tier: "free", isFree: true }) }));
vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("ImageWorkshopModal（上传型工坊）", () => {
  beforeEach(() => vi.clearAllMocks());

  it("上传候选图并采用后给出撤销入口", async () => {
    const onChanged = vi.fn();
    render(
      <ImageWorkshopModal open novelId="n1" kind="cover" onClose={() => {}} onChanged={onChanged} />,
    );
    await waitFor(() => expect(screen.getByText("候选图")).toBeTruthy());
    expect(screen.getByText("使用")).toBeTruthy();

    fireEvent.click(screen.getByText("使用"));
    await waitFor(() => expect(api.adoptAsset).toHaveBeenCalledWith("a-candidate"));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());

    // 采用后列表仍是候选（mock 未变），但撤销条已出现
    await waitFor(() => expect(screen.getByText(/秒内可撤销/)).toBeTruthy());
    fireEvent.click(screen.getByText("撤销"));
    await waitFor(() => expect(api.undoAsset).toHaveBeenCalledWith("a-candidate", "tok"));
  });

  it("上传文件调用 XHR 上传入口", async () => {
    const onChanged = vi.fn();
    render(
      <ImageWorkshopModal open novelId="n1" kind="cover" onClose={() => {}} onChanged={onChanged} />,
    );
    await waitFor(() => expect(screen.getByText("上传封面")).toBeTruthy());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["x"], "a.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(api.uploadAsset).toHaveBeenCalledWith(
      "n1", file, "cover", undefined, expect.any(Function),
    ));
  });
});
