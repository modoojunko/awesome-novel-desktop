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
    novel_id: "n1", style_key: "ink", cover_prompt: "",
    image_config_id: null, image_model: "", effective_image_config_id: null,
    effective_image_model: "seedream", effective_source: "default" as const,
  })),
  getCharacterSettings: vi.fn(async () => ({
    character_id: "c1", avatar_prompt: "",
  })),
  extractCoverScene: vi.fn(async () => ({
    scene: "深夜站台，末班公交的剪影驶近，车灯昏黄。",
  })),
  extractAvatarLook: vi.fn(async () => ({
    look: "瘦高身形，旧斗篷领口磨亮，眼下一道浅疤。",
  })),
  uploadAsset: vi.fn(async () => candidate),
  adoptAsset: vi.fn(async () => ({ ...candidate, status: "current", undo_token: "tok", undo_expires_at: new Date(Date.now() + 8000).toISOString() })),
  undoAsset: vi.fn(async () => ({ restored_asset_id: null, removed_asset_id: "a-candidate" })),
  deleteAsset: vi.fn(async () => ({ deleted_asset_id: "a-candidate" })),
  patchBookSettings: vi.fn(async () => ({})),
  patchCharacterSettings: vi.fn(async () => ({})),
  createImageJob: vi.fn(async () => ({
    id: "job-1", status: "running" as const, purpose: "generate" as const,
    kind: "cover" as const, produced_count: 0, requested_n: 2,
    error_message: null, cancel_requested: false, items: [],
  })),
  getImageJob: vi.fn(async () => ({
    id: "job-1", status: "completed" as const, purpose: "generate" as const,
    kind: "cover" as const, produced_count: 2, requested_n: 2,
    error_message: null, cancel_requested: false, items: [],
  })),
  cancelImageJob: vi.fn(async () => ({ id: "job-1", status: "cancelled" as const })),
  retryImageJob: vi.fn(async () => ({ id: "job-1", status: "queued" as const })),
}));

const featureAllowed = vi.hoisted(() => ({ value: false }));

vi.mock("@/lib/imageApi", () => ({ imageApi: api, IMAGE_PROVIDERS: [] }));
vi.mock("@/hooks/useTier", () => ({
  useTier: () => ({ isPro: featureAllowed.value, tier: featureAllowed.value ? "pro" : "free", isFree: !featureAllowed.value }),
  useFeature: () => featureAllowed.value,
}));
vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("ImageWorkshopModal（上传型工坊）", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    featureAllowed.value = false;
  });

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

  it("免费用户生成按钮置灰；PRO 提交任务并轮询到完成", async () => {    const onChanged = vi.fn();
    const free = render(
      <ImageWorkshopModal open novelId="n1" kind="cover" onClose={() => {}} onChanged={onChanged} />,
    );
    await waitFor(() => expect(screen.getByText("AI 生成（PRO 以上）")).toBeTruthy());
    const generate = screen.getByRole("button", { name: "生成 2 张候选" }) as HTMLButtonElement;
    expect(generate.disabled).toBeTruthy();
    free.unmount();

    featureAllowed.value = true;
    render(
      <ImageWorkshopModal open novelId="n1" kind="cover" onClose={() => {}} onChanged={onChanged} />,
    );
    await waitFor(() => expect(
      (screen.getByRole("button", { name: "生成 2 张候选" }) as HTMLButtonElement).disabled,
    ).toBeFalsy());
    fireEvent.click(screen.getByRole("button", { name: "生成 2 张候选" }));
    await waitFor(() => expect(api.createImageJob).toHaveBeenCalledWith(
      "n1", { kind: "cover", character_id: undefined, n: 2, purpose: "generate" },
    ));
    await waitFor(() => expect(screen.getByText("生成中")).toBeTruthy());
    await waitFor(() => expect(api.getImageJob).toHaveBeenCalledWith("job-1"), { timeout: 3000 });
    await waitFor(() => expect(screen.getByText("已完成 2 张")).toBeTruthy());
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });

  it("取消后可重试同一任务（不再卡在已取消）", async () => {
    featureAllowed.value = true;
    const running = {
      id: "job-1", status: "running", purpose: "generate",
      kind: "cover", produced_count: 0, requested_n: 2,
      error_message: null, cancel_requested: false, items: [],
    } as unknown as Awaited<ReturnType<typeof api.getImageJob>>;
    api.getImageJob.mockImplementation(async () => running);
    render(
      <ImageWorkshopModal open novelId="n1" kind="cover" onClose={() => {}} onChanged={() => {}} />,
    );
    await waitFor(() => expect(
      (screen.getByRole("button", { name: "生成 2 张候选" }) as HTMLButtonElement).disabled,
    ).toBeFalsy());
    fireEvent.click(screen.getByRole("button", { name: "生成 2 张候选" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "取消生成" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "取消生成" }));
    await waitFor(() => expect(api.cancelImageJob).toHaveBeenCalledWith("job-1"));

    fireEvent.click(await screen.findByRole("button", { name: "重试" }));
    await waitFor(() => expect(api.retryImageJob).toHaveBeenCalledWith("job-1"));
  });

  it("AI 提取：免费置灰；PRO 调提取并把草稿填进画面描述", async () => {
    const free = render(
      <ImageWorkshopModal open novelId="n1" kind="cover" onClose={() => {}} onChanged={() => {}} />,
    );
    await waitFor(() => expect(screen.getByText("画面描述")).toBeTruthy());
    const extract = screen.getByRole("button", { name: "AI 提取" }) as HTMLButtonElement;
    expect(extract.disabled).toBeTruthy();
    free.unmount();

    featureAllowed.value = true;
    render(
      <ImageWorkshopModal open novelId="n1" kind="cover" onClose={() => {}} onChanged={() => {}} />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "AI 提取" }));
    await waitFor(() => expect(api.extractCoverScene).toHaveBeenCalledWith("n1"));
    const textarea = document.querySelector(".img-field textarea") as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toContain("末班公交"));
  });

  it("封面种子输入框与提示词预览已退役（不再出现）", async () => {
    render(
      <ImageWorkshopModal open novelId="n1" kind="cover" onClose={() => {}} onChanged={() => {}} />,
    );
    await waitFor(() => expect(screen.getByText("画面描述")).toBeTruthy());
    expect(screen.queryByText("封面种子")).toBeNull();
    expect(screen.queryByText("头像种子")).toBeNull();
    expect(screen.queryByText("提示词预览")).toBeNull();
  });

  it("头像 AI 起草：免费置灰；PRO 调起草并把草稿填进头像描述", async () => {
    featureAllowed.value = false;
    const free = render(
      <ImageWorkshopModal open novelId="n1" kind="avatar" characterId="c1" characterName="林野" onClose={() => {}} onChanged={() => {}} />,
    );
    await waitFor(() => expect(screen.getByText("头像描述")).toBeTruthy());
    const extract = screen.getByRole("button", { name: "AI 起草" }) as HTMLButtonElement;
    expect(extract.disabled).toBeTruthy();
    free.unmount();

    featureAllowed.value = true;
    render(
      <ImageWorkshopModal open novelId="n1" kind="avatar" characterId="c1" characterName="林野" onClose={() => {}} onChanged={() => {}} />,
    );
    fireEvent.click(await screen.findByRole("button", { name: "AI 起草" }));
    await waitFor(() => expect(api.extractAvatarLook).toHaveBeenCalledWith("n1", "c1"));
    const textarea = document.querySelector(".img-field textarea") as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toContain("旧斗篷"));
  });
});
