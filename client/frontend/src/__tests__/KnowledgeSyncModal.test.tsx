import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import KnowledgeSyncModal from "@/components/kb/KnowledgeSyncModal";
import { readKbDismissal } from "@/lib/kbProbe";

// s-kb-signed-delivery：按题材同步弹窗——清单/配额/逐题材同步；
// update 模式自动弹、manual 自己 probe；关闭 update 记 release 版本锚。
const { syncMock, probeMock, toastState } = vi.hoisted(() => ({
  syncMock: vi.fn(),
  probeMock: vi.fn(),
  toastState: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}));
vi.mock("@/lib/kbApi", () => ({
  kbApi: {
    baselineSync: (...a: unknown[]) => syncMock(...(a as [])),
    baselineProbe: (...a: unknown[]) => probeMock(...(a as [])),
  },
}));
vi.mock("@/lib/toast", () => ({
  toast: toastState,
}));

const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);

const PROBE = {
  installed: 0,
  latest: 5,
  update_available: true,
  genres: {
    玄幻: { path: "genres/a.jsonl", sha256: SHA_A, bytes: 10, entry_count: 2 },
    都市: { path: "genres/b.jsonl", sha256: SHA_B, bytes: 10, entry_count: 1 },
  },
  installed_genres: {},
  quota: { limit: 2, used: 0, remaining: 2, reset_at: "2026-11-22T00:00:00+08:00" },
};

function openKbSync(detail: Record<string, unknown>) {
  act(() => {
    window.dispatchEvent(new CustomEvent("kb-sync-modal:open", { detail }));
  });
}

describe("KnowledgeSyncModal（s-kb-signed-delivery 按题材同步）", () => {
  beforeEach(() => {
    window.localStorage.removeItem("kb-sync-dismissed");
    syncMock.mockReset().mockResolvedValue({
      status: "synced",
      version: 5,
      genre: "玄幻",
      entries: 2,
      quota: { limit: 2, used: 1, remaining: 1, reset_at: "2026-11-22T00:00:00+08:00" },
    });
    probeMock.mockReset().mockResolvedValue(PROBE);
    toastState.info.mockClear();
    toastState.success.mockClear();
  });
  afterEach(cleanup);

  it("update 模式：清单按题材列出；点某题材才同步并扣 1 次", async () => {
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", probe: PROBE });

    expect(screen.getByText("官方知识")).toBeTruthy();
    expect(screen.getByTestId("kb-genre-row-玄幻")).toBeTruthy();
    expect(screen.getByTestId("kb-genre-row-都市")).toBeTruthy();
    expect(screen.getByTestId("kb-genre-quota").textContent).toContain("今日还可同步 2 个题材");
    expect(syncMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("kb-genre-sync-玄幻"));
    await waitFor(() => expect(syncMock).toHaveBeenCalledWith("玄幻"));
    await waitFor(() =>
      expect(screen.getByTestId("kb-genre-state-玄幻").textContent).toContain("已同步"),
    );
    expect(toastState.success).toHaveBeenCalledWith("「玄幻」已同步");
    expect(screen.getByTestId("kb-genre-quota").textContent).toContain("今日还可同步 1 个题材");
  });

  it("manual 模式无快照：先 probe 一次（免费）再出清单", async () => {
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "manual" });
    await waitFor(() => expect(probeMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId("kb-genre-list")).toBeTruthy());
  });

  it("额度用完：按钮禁用并说明明天恢复", () => {
    render(<KnowledgeSyncModal />);
    openKbSync({
      mode: "update",
      probe: {
        ...PROBE,
        quota: { limit: 2, used: 2, remaining: 0, reset_at: "2026-11-22T00:00:00+08:00" },
      },
    });
    expect(screen.getByTestId("kb-genre-quota").textContent).toContain("用完了");
    expect((screen.getByTestId("kb-genre-sync-玄幻") as HTMLButtonElement).disabled).toBe(true);
  });

  it("skipped/quota_exceeded：不谎报成功，info 说明" , async () => {
    syncMock.mockResolvedValue({ status: "skipped", reason: "quota_exceeded" });
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", probe: PROBE });
    fireEvent.click(screen.getByTestId("kb-genre-sync-玄幻"));
    await waitFor(() =>
      expect(toastState.info).toHaveBeenCalledWith("今天的题材同步次数用完了，明天再来吧。"),
    );
    expect(toastState.success).not.toHaveBeenCalled();
  });

  it("skipped/tier_denied：说明套餐不含官方知识库", async () => {
    syncMock.mockResolvedValue({ status: "skipped", reason: "tier_denied" });
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", probe: PROBE });
    fireEvent.click(screen.getByTestId("kb-genre-sync-玄幻"));
    await waitFor(() =>
      expect(toastState.info).toHaveBeenCalledWith("当前套餐不包含官方知识库。"),
    );
  });

  it("同步失败→失败态「再试一次」；重试走 probe 自查", async () => {
    syncMock.mockRejectedValueOnce(new Error("net"));
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", probe: PROBE });
    fireEvent.click(screen.getByTestId("kb-genre-sync-玄幻"));
    await waitFor(() => expect(screen.getByTestId("kb-sync-fail-note")).toBeTruthy());

    fireEvent.click(screen.getByTestId("kb-sync-retry"));
    await waitFor(() => expect(probeMock).toHaveBeenCalled());
    expect(syncMock).toHaveBeenCalledTimes(1);
  });

  it("写作提示带入 focusGenre：高亮该题材并给一句说明", () => {
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "manual", probe: PROBE, focusGenre: "玄幻" });
    expect(screen.getByTestId("kb-genre-focus-note").textContent).toContain("「玄幻」");
  });

  it("关闭 update 模式：记 release 版本锚（同版不重弹）", () => {
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", probe: PROBE });
    fireEvent.click(screen.getByTestId("kb-sync-close"));
    expect(readKbDismissal().updateVersion).toBe("5");
    expect(syncMock).not.toHaveBeenCalled();
  });

  it("进度期收到新开启事件被忽略（不降级不重开）", async () => {
    let release: (() => void) | null = null;
    syncMock.mockImplementationOnce(
      () =>
        new Promise((res) => {
          release = () =>
            res({ status: "synced", version: 5, genre: "玄幻", entries: 2 });
        }),
    );
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", probe: PROBE });
    fireEvent.click(screen.getByTestId("kb-genre-sync-玄幻"));
    await waitFor(() => expect(screen.getByText("正在同步官方知识")).toBeTruthy());
    openKbSync({ mode: "manual", probe: PROBE });
    expect(screen.getByText("正在同步官方知识")).toBeTruthy();
    await act(async () => {
      release?.();
    });
    await waitFor(() => expect(screen.getByTestId("kb-genre-list")).toBeTruthy());
  });

  it("probe 失败→失败态；不会误开清单", async () => {
    probeMock.mockRejectedValueOnce(new Error("net"));
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "manual" });
    await waitFor(() => expect(screen.getByTestId("kb-sync-fail-note")).toBeTruthy());
    expect(screen.queryByTestId("kb-genre-list")).toBeNull();
  });
});
