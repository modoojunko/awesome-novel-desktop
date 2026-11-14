import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import KnowledgeSyncModal from "@/components/kb/KnowledgeSyncModal";
import { readKbDismissal } from "@/lib/kbProbe";

// c-kb-baseline-update-ux：官方知识弹窗两模式状态机——update 开窗即确认、
// manual 检查更新；点「立即更新」await 同步直回（无轮询）；暂不更新记版本锚。
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

function openKbSync(detail: Record<string, unknown>) {
  act(() => {
    window.dispatchEvent(new CustomEvent("kb-sync-modal:open", { detail }));
  });
}

describe("KnowledgeSyncModal（c-kb-baseline-update-ux）", () => {
  beforeEach(() => {
    window.localStorage.removeItem("kb-sync-dismissed");
    syncMock.mockReset().mockResolvedValue({ status: "synced", version: 4 });
    probeMock.mockReset().mockResolvedValue({ installed: 3, latest: 3, update_available: false });
    toastState.info.mockClear();
    toastState.success.mockClear();
  });
  afterEach(cleanup);

  it("update 模式：开窗即确认（当前→最新），确认后同步直回并 toast", async () => {
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", from: 3, to: 4 });
    expect(screen.getByText("官方知识有更新")).toBeTruthy();
    const ver = screen.getByTestId("kb-sync-versions").textContent ?? "";
    expect(ver).toContain("v3");
    expect(ver).toContain("v4");
    expect(syncMock).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId("kb-sync-confirm"));
    await waitFor(() => expect(syncMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("官方知识已更新")).toBeTruthy());
    expect(screen.getByTestId("kb-sync-done").textContent).toContain("v4");
    expect(toastState.success).toHaveBeenCalledWith("官方知识已更新到 v4");
  });

  it("暂不更新：确认态关窗记版本锚（同版不重弹的锚点）", () => {
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", from: 3, to: 4 });
    fireEvent.click(screen.getByTestId("kb-sync-later"));
    expect(readKbDismissal().updateVersion).toBe("4");
    expect(syncMock).not.toHaveBeenCalled();
  });

  it("manual 模式：检查更新无新版→toast 已是最新；有新版→转确认", async () => {
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "manual" });
    expect(screen.getByText("官方知识")).toBeTruthy();
    fireEvent.click(screen.getByTestId("kb-sync-check"));
    await waitFor(() => expect(probeMock).toHaveBeenCalled());
    await waitFor(() => expect(toastState.info).toHaveBeenCalledWith("已是最新"));

    probeMock.mockResolvedValue({ installed: 3, latest: 5, update_available: true });
    fireEvent.click(screen.getByTestId("kb-sync-check"));
    await waitFor(() => expect(screen.getByText("官方知识有更新")).toBeTruthy());
    expect((screen.getByTestId("kb-sync-versions").textContent ?? "")).toContain("v5");
  });

  it("同步失败→失败态给「再试一次」，重试成功转完成", async () => {
    syncMock.mockRejectedValueOnce(new Error("cdn"));
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", from: 3, to: 4 });
    fireEvent.click(screen.getByTestId("kb-sync-confirm"));
    await waitFor(() => expect(screen.getByText("更新没有完成")).toBeTruthy());
    expect(screen.getByTestId("kb-sync-fail-note").textContent).toContain("稍后可以再试");

    fireEvent.click(screen.getByTestId("kb-sync-retry"));
    await waitFor(() => expect(screen.getByText("官方知识已更新")).toBeTruthy());
    expect(syncMock).toHaveBeenCalledTimes(2);
  });

  it("竞态下他路已装同版（status=current）同样算更新完成", async () => {
    syncMock.mockResolvedValue({ status: "current", version: 4 });
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", from: 3, to: 4 });
    fireEvent.click(screen.getByTestId("kb-sync-confirm"));
    await waitFor(() => expect(screen.getByText("官方知识已更新")).toBeTruthy());
    expect(toastState.success).toHaveBeenCalledWith("官方知识已更新到 v4");
  });

  it("进度期收到新开启事件被忽略（不降级不重开）", async () => {
    let release: (() => void) | null = null;
    syncMock.mockImplementationOnce(
      () => new Promise((res) => { release = () => res({ status: "synced", version: 4 }); }),
    );
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", from: 3, to: 4 });
    fireEvent.click(screen.getByTestId("kb-sync-confirm"));
    await waitFor(() => expect(screen.getByText("正在更新官方知识")).toBeTruthy());
    // running 期再发 manual 开启事件：不应翻回 idle
    openKbSync({ mode: "manual" });
    expect(screen.getByText("正在更新官方知识")).toBeTruthy();
    await act(async () => { release?.(); });
    await waitFor(() => expect(screen.getByText("官方知识已更新")).toBeTruthy());
  });
});

describe("失败原因细分（c-proxy-fakeip-compat）", () => {
  it("reason=proxy_fake_ip：失败态给代理 TUN 指路文案", async () => {
    syncMock.mockResolvedValue({ status: "failed", reason: "proxy_fake_ip" });
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", from: 3, to: 4 });
    fireEvent.click(screen.getByTestId("kb-sync-confirm"));
    await waitFor(() => expect(screen.getByText("更新没有完成")).toBeTruthy());
    const note = screen.getByTestId("kb-sync-fail-note").textContent ?? "";
    expect(note).toContain("TUN 模式");
    expect(note).toContain("白名单");
    expect(screen.getByTestId("kb-sync-retry")).toBeTruthy();
  });

  it("其他失败 reason：维持既有网络文案", async () => {
    syncMock.mockResolvedValue({ status: "failed", reason: "manifest_invalid" });
    render(<KnowledgeSyncModal />);
    openKbSync({ mode: "update", from: 3, to: 4 });
    fireEvent.click(screen.getByTestId("kb-sync-confirm"));
    await waitFor(() => expect(screen.getByText("更新没有完成")).toBeTruthy());
    expect(screen.getByTestId("kb-sync-fail-note").textContent).toContain("稍后可以再试");
  });
});
