import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PromptPackModal from "@/components/novel/license/PromptPackModal";
import { readPackDismissal } from "@/lib/packProbe";

// c-prompt-pack-onboard-modal 4.1：写作能力弹窗三模式状态机（design D7）——
// install 开窗即跑／update 确认后跑／manual 手动检查；running 轮询到终态；
// 失败态出口（重新获取/复制诊断/去升级）。§13 口径：内部术语零出现。
const tierState = {
  pack: null as unknown,
  refetch: vi.fn(),
};
vi.mock("@/hooks/useTier", () => ({
  useTier: () => ({ refetch: tierState.refetch, pack: tierState.pack }),
}));
vi.mock("@/lib/auth", () => ({
  isLoggedIn: () => true,
}));
const { apiGet, apiPost, toastState } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  toastState: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}));
vi.mock("@/lib/api", () => ({
  api: {
    get: (...a: unknown[]) => apiGet(...(a as [])),
    post: (...a: unknown[]) => apiPost(...(a as [])),
  },
}));
vi.mock("@/lib/toast", () => ({
  toast: toastState,
}));

function openPack(detail: Record<string, unknown>) {
  act(() => {
    window.dispatchEvent(new CustomEvent("pack-modal:open", { detail }));
  });
}

describe("PromptPackModal（c-prompt-pack-onboard-modal）", () => {
  beforeEach(() => {
    // shouldAdvanceTime：waitFor 内部定时器不被冻结，轮询仍可用 advanceTimersByTimeAsync 精确推进
    vi.useFakeTimers({ shouldAdvanceTime: true });
    tierState.pack = null;
    tierState.refetch.mockClear();
    apiGet.mockReset();
    apiPost.mockReset();
    apiPost.mockResolvedValue({ started: true });
    apiGet.mockResolvedValue({ phase: "syncing", step: "" });
    toastState.info.mockClear();
  });

  it("install 模式：开窗即 POST /check 触发同步并展示分步进度；ready 后转完成", async () => {
    apiGet.mockResolvedValue({ phase: "syncing", step: "download" });
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/prompt-pack/check", undefined, { quiet: true }));
    expect(screen.getByText("正在准备写作能力")).toBeTruthy();
    expect(screen.getByTestId("pack-steps")).toBeTruthy();
    // 拍板 10-07 三次：进度文案明说不能关闭此窗口＋预计耗时（首装/更新同口径）
    const note = screen.getByTestId("pack-running-note").textContent ?? "";
    expect(note).toContain("不能关闭此窗口");
    expect(note).toContain("预计");

    apiGet.mockResolvedValue({ phase: "ready", version: "6", step: "" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(screen.getByTestId("pack-done").textContent).toContain("v6");
    expect(screen.getByRole("button", { name: "开始写作" })).toBeTruthy();
    expect(tierState.refetch).toHaveBeenCalled();
  });

  it("update 模式：先确认（当前→最新），确认后才触发同步", async () => {
    render(<PromptPackModal />);
    openPack({ mode: "update", from: "5", to: "6" });
    expect(screen.getByTestId("pack-versions").textContent).toContain("5");
    expect(screen.getByTestId("pack-versions").textContent).toContain("6");
    expect(apiPost).not.toHaveBeenCalled();
    const cnote = screen.getByTestId("pack-confirm-note").textContent ?? "";
    expect(cnote).toContain("不能关闭此窗口");
    expect(cnote).toContain("预计");

    fireEvent.click(screen.getByTestId("pack-confirm-update"));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/prompt-pack/check", undefined, { quiet: true }));
    // 更新运行态标题与耗时口径（runKind=update）
    expect(screen.getByText("正在更新写作能力")).toBeTruthy();
    expect((screen.getByTestId("pack-running-note").textContent ?? "")).toContain("正在更新到最新版本");
  });

  it("manual 模式：检查更新——有新版本转确认流", async () => {
    apiGet.mockResolvedValue({ installed_version: "5", latest_version: "6", update_available: true });
    render(<PromptPackModal />);
    openPack({ mode: "manual" });
    expect(screen.getByText("写作能力")).toBeTruthy();
    fireEvent.click(screen.getByTestId("pack-check-update"));
    await waitFor(() => expect(screen.getByTestId("pack-versions")).toBeTruthy());
    expect(screen.getByTestId("pack-versions").textContent).toContain("6");
  });

  it("manual 模式：无更新 toast「已是最新」，不触发同步", async () => {
    apiGet.mockResolvedValue({ installed_version: "5", latest_version: "5", update_available: false });
    tierState.pack = { phase: "ready", version: "5" };
    render(<PromptPackModal />);
    openPack({ mode: "manual" });
    fireEvent.click(screen.getByTestId("pack-check-update"));
    await waitFor(() => expect(toastState.info).toHaveBeenCalledWith("已是最新"));
    expect(apiPost).not.toHaveBeenCalled();
  });

  it("manual 模式：未就绪转首装进度流", async () => {
    apiGet.mockImplementation((url: string) =>
      String(url).includes("/prompt-pack/probe")
        ? Promise.resolve({ installed_version: "", latest_version: "", update_available: false })
        : Promise.resolve({ phase: "missing", step: "" }),
    );
    tierState.pack = { phase: "missing" };
    render(<PromptPackModal />);
    openPack({ mode: "manual" });
    fireEvent.click(screen.getByTestId("pack-check-update"));
    await waitFor(() => expect(apiPost).toHaveBeenCalled());
    expect(screen.getByText("正在准备写作能力")).toBeTruthy();
  });

  it("running 轮询到 failed：失败态出口（重新获取/复制诊断），重试再触发", async () => {
    apiGet.mockResolvedValue({ phase: "failed", reason: "cdn_unreachable", step: "" });
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(screen.getByTestId("pack-fail-note").textContent).toContain("网络暂时连不上");
    fireEvent.click(screen.getByTestId("pack-retry"));
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(2));
    expect(screen.getByText("正在准备写作能力")).toBeTruthy();
  });

  it("tier_denied：失败态走升级出口", async () => {
    apiGet.mockResolvedValue({ phase: "tier_denied", reason: "tier", step: "" });
    tierState.pack = { phase: "tier_denied", reason: "tier" };
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(screen.getByRole("button", { name: "去升级" })).toBeTruthy();
    const body = document.body.textContent ?? "";
    for (const banned of ["提示词包", "manifest", "验签"]) {
      expect(body.includes(banned)).toBe(false);
    }
  });

  it("running 重入不降级不重跑（评审 P1-3）：进度期再广播 open 保持锁定态、不重复触发", async () => {
    apiGet.mockResolvedValue({ phase: "syncing", step: "download" });
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await waitFor(() => expect(screen.getByText("正在准备写作能力")).toBeTruthy());
    const postsBefore = apiPost.mock.calls.length;
    // 进度期重进作品页再探测的两种广播：update（会降级成可关确认弹窗）与 install（会开双链）
    openPack({ mode: "update", from: "5", to: "6" });
    openPack({ mode: "install" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1200);
    });
    expect(screen.getByText("正在准备写作能力")).toBeTruthy(); // 未降级
    expect(apiPost.mock.calls.length).toBe(postsBefore); // 不重复触发
  });

  it("轮询 180s 超时：转失败态并解锁（评审 P2-5）", async () => {
    apiGet.mockResolvedValue({ phase: "syncing", step: "download" });
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await waitFor(() => expect(screen.getByText("正在准备写作能力")).toBeTruthy());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(181_000);
    });
    expect(screen.getByTestId("pack-fail-note")).toBeTruthy();
    expect(screen.getByRole("button", { name: "重新获取" })).toHaveProperty("disabled", false);
  });

  it("失败态呈现具体原因（评审 P2-4）：cdn_unreachable 映射人话", async () => {
    apiGet.mockResolvedValue({ phase: "failed", reason: "cdn_unreachable", step: "" });
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect((screen.getByTestId("pack-fail-note").textContent ?? "")).toContain("网络暂时连不上");
  });

  it("manual：min_client 跳过不进首装流（评审 P1-2），提示先更新客户端", async () => {
    apiGet.mockImplementation((url: string) =>
      String(url).includes("/prompt-pack/probe")
        ? Promise.resolve({
            installed_version: "",
            latest_version: "6",
            update_available: false,
            reason: "min_client_version",
            source: "pack",
          })
        : Promise.resolve({ phase: "missing", step: "" }),
    );
    render(<PromptPackModal />);
    openPack({ mode: "manual" });
    fireEvent.click(screen.getByTestId("pack-check-update"));
    await waitFor(() => expect(toastState.info).toHaveBeenCalledWith("先更新客户端后可获取写作能力"));
    expect(apiPost).not.toHaveBeenCalled(); // 不进必败的首装流
    expect(screen.queryByText("正在准备写作能力")).toBeNull();
  });

  it("进度期弹窗锁定：无退出按钮，Esc 不可关，轮询继续（完成才提示可关闭）", async () => {
    apiGet.mockResolvedValue({ phase: "syncing", step: "download" });
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await waitFor(() => expect(screen.getByText("正在准备写作能力")).toBeTruthy());
    // 无「先去写作」等任何退出出口；文案不出现「可以关闭」话术
    expect(screen.queryByRole("button", { name: "先去写作" })).toBeNull();
    expect(screen.queryByRole("button", { name: "关闭" })).toHaveProperty("disabled", true);
    // 新口径（拍板 10-07 三次）：明说「不能关闭此窗口」——反向断言只禁「可以/放心关闭」话术
    const bodyText = document.body.textContent ?? "";
    expect(bodyText).toContain("不能关闭此窗口");
    expect(bodyText).not.toContain("可以关闭");
    expect(bodyText).not.toContain("放心关闭");
    // Esc 不可关（Modal locked）
    fireEvent.keyDown(window, { key: "Escape" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(screen.getByText("正在准备写作能力")).toBeTruthy();
    // 轮询仍在继续（锁定不等于停摆）
    expect(apiGet.mock.calls.filter((c) => String(c[0]).includes("status")).length).toBeGreaterThan(0);
    // ready 后解锁转完成态（此时才提示可关闭）
    apiGet.mockResolvedValue({ phase: "ready", version: "9", step: "" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(screen.getByTestId("pack-done")).toBeTruthy();
    expect(screen.getByRole("button", { name: "开始写作" })).toHaveProperty("disabled", false);
  });
});

describe("PromptPackModal 关闭记忆（c-pack-modal-dismiss）", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    tierState.pack = null;
    tierState.refetch.mockClear();
    apiGet.mockReset();
    apiPost.mockReset();
    apiPost.mockResolvedValue({ started: true });
    apiGet.mockResolvedValue({ phase: "syncing", step: "" });
    window.localStorage.clear();
  });

  async function runToFailed() {
    apiGet.mockResolvedValue({ phase: "failed", reason: "cdn_unreachable", step: "" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    expect(screen.getByText("写作能力没有就绪")).toBeTruthy();
  }

  it("首装失败态关闭（反馈#4 主场景）→ 写入首装关闭标记，不再自动弹", async () => {
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await waitFor(() => expect(screen.getByText("正在准备写作能力")).toBeTruthy());
    await runToFailed();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(readPackDismissal()).toEqual({ install: true });
  });

  it("安装成功后关闭 → 清除首装标记（自愈，spec 场景钉）", async () => {
    window.localStorage.setItem("pack-modal-dismissed", JSON.stringify({ install: true }));
    render(<PromptPackModal />);
    openPack({ mode: "install" });
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith("/prompt-pack/check", undefined, { quiet: true }));
    apiGet.mockResolvedValue({ phase: "ready", version: "6", step: "" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    await waitFor(() => expect(screen.getByTestId("pack-done")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "开始写作" }));
    expect(readPackDismissal().install).toBeFalsy();
  });

  it("更新确认态「暂不更新」→ 记版本锚（同版不重弹）", async () => {
    render(<PromptPackModal />);
    openPack({ mode: "update", from: "5", to: "6" });
    expect(screen.getByText("写作能力有更新")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "暂不更新" }));
    expect(readPackDismissal()).toEqual({ updateVersion: "6" });
  });

  it("更新流失败且包已装 → 关闭不写首装标记（包在场不该误标未装）", async () => {
    tierState.pack = { version: "5" };
    render(<PromptPackModal />);
    openPack({ mode: "update", from: "5", to: "6" });
    fireEvent.click(screen.getByTestId("pack-confirm-update"));
    await waitFor(() => expect(screen.getByText("正在更新写作能力")).toBeTruthy());
    await runToFailed();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(readPackDismissal().install).toBeFalsy();
    expect(readPackDismissal().updateVersion).toBeFalsy();
  });

  it("manual 空闲态关闭不记标记——手动检查窗不带「别再提醒」语义", async () => {
    render(<PromptPackModal />);
    openPack({ mode: "manual" });
    expect(screen.getByTestId("pack-manual-note")).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(readPackDismissal()).toEqual({});
  });
});
