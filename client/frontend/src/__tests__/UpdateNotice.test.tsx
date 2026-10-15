import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const requestMock = vi.fn();

beforeEach(() => {
  requestMock.mockReset();
  vi.resetModules();
  vi.doMock("@/lib/api", () => ({
    request: requestMock,
    errMessage: (e: unknown, fallback?: string) =>
      fallback ?? (e instanceof Error ? e.message : String(e)),
  }));
});

function state(over: Partial<Record<string, unknown>> = {}) {
  return {
    current: "0.11",
    latest: "0.13",
    has_update: true,
    notes: "提升章纲 AI 起草的稳定性，修复若干问题",
    notes_url: "https://www.awesomenovel.com/download/v0.13/notes.html",
    download_url: "https://www.awesomenovel.com",
    ...over,
  };
}

async function mountAt(path: string, stallMs?: number) {
  const { default: UpdateNotice } = await import("@/components/UpdateNotice");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <UpdateNotice stallMs={stallMs} />
    </MemoryRouter>,
  );
}

describe("UpdateNotice", () => {
  it("有更新（自动链正常）：文案「正在自动准备」，等待期内不给手动入口", async () => {
    requestMock.mockResolvedValue(state());
    const dbg = await mountAt("/novels");

    expect(await screen.findByText(/正在自动准备新版本 v0\.13/)).toBeTruthy();
    expect(requestMock).toHaveBeenCalledWith("/update-check", { quiet: true });
    expect(screen.getByText("提升章纲 AI 起草的稳定性，修复若干问题")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "去下载" })).toBeNull();
    const notes = screen.getByRole("link", { name: "查看更新内容" }) as HTMLAnchorElement;
    expect(notes.href).toBe(
      "https://www.awesomenovel.com/download/v0.13/notes.html",
    );
    expect(screen.getByRole("button", { name: "知道了" })).toBeTruthy();
  });

  it("双轨兜底：自动链停摆（stallMs=0）→ 「去下载」出现且为外链锚点", async () => {
    requestMock.mockResolvedValue(state());
    await mountAt("/novels", 0);

    const download = (await screen.findByRole("link", {
      name: "去下载",
    })) as HTMLAnchorElement;
    expect(download.href).toBe("https://www.awesomenovel.com/");
    expect(download.target).toBe("_blank");
    expect(download.rel).toContain("noopener");
    expect(await screen.findByText(/自动准备不可用，可手动下载/)).toBeTruthy();
  });

  it("有更新但响应缺失 current：对照文案退回仅含新版本号", async () => {
    requestMock.mockResolvedValue(state({ current: "" }));
    await mountAt("/novels");
    expect(await screen.findByText(/正在自动准备新版本 v0\.13/)).toBeTruthy();
  });

  it("无更新 / 检测失败：不渲染任何更新元素", async () => {
    requestMock.mockResolvedValue(state({ has_update: false, latest: "0.11" }));
    const { container } = await mountAt("/novels");
    await waitFor(() => expect(requestMock).toHaveBeenCalled());
    expect(container.querySelector(".update-strip")).toBeNull();

    requestMock.mockRejectedValue(new Error("network down"));
    const again = await mountAt("/novels");
    await waitFor(() => expect(requestMock).toHaveBeenCalled());
    expect(again.container.querySelector(".update-strip")).toBeNull();
  });

  it("「知道了」按版本关闭：调 dismiss 且提示条立即消失", async () => {
    requestMock.mockImplementation(async (path: string) =>
      path === "/update-check" ? state() : { dismissed: "0.13" },
    );
    const { container } = await mountAt("/novels");
    await screen.findByText(/正在自动准备新版本 v0\.13/);

    fireEvent.click(screen.getByRole("button", { name: "知道了" }));
    await waitFor(() =>
      expect(requestMock).toHaveBeenCalledWith("/update-check/dismiss", {
        method: "POST",
        body: JSON.stringify({ version: "0.13" }),
        quiet: true,
      }),
    );
    expect(container.querySelector(".update-strip")).toBeNull();
  });

  it("工作台路由用沉浸全宽变体，书架用居中变体", async () => {
    requestMock.mockResolvedValue(state());
    const imm = await mountAt("/novel/abc");
    await waitFor(() => expect(imm.container.querySelector(".update-strip")).toBeTruthy());
    expect(imm.container.querySelector(".update-strip")!.className).toContain(
      "update-strip--imm",
    );

    const list = await mountAt("/config");
    await waitFor(() => expect(list.container.querySelector(".update-strip")).toBeTruthy());
    expect(list.container.querySelector(".update-strip")!.className).not.toContain(
      "update-strip--imm",
    );
  });
});

describe("UpdateNotice silent-upgrade 三态（P1 第二片）", () => {
  const toastMock = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
  const quitMock = vi.fn();

  beforeEach(() => {
    requestMock.mockReset();
    vi.resetModules();
    vi.doMock("@/lib/api", () => ({
      request: requestMock,
      errMessage: (e: unknown, fallback?: string) =>
        fallback ?? (e instanceof Error ? e.message : String(e)),
    }));
    vi.doMock("@/lib/toast", () => ({ toast: toastMock }));
    delete (window as unknown as { __updateAppliedSeen?: string }).__updateAppliedSeen;
    delete (window as unknown as { pywebview?: unknown }).pywebview;
    quitMock.mockClear();
    toastMock.success.mockClear();
    toastMock.error.mockClear();
    toastMock.info.mockClear();
  });

  afterEach(() => {
    vi.doUnmock("@/lib/toast");
    vi.restoreAllMocks();
  });

  it("staged：就绪横幅＋「重启更新」走 /apply → 桥 quit_app；不给「去下载」", async () => {
    requestMock.mockImplementation(async (path: string) =>
      path === "/update-check"
        ? state({ auto: { state: "staged", version: "0.13" } })
        : { ok: true });
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { quit_app: quitMock },
    };
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { container } = await mountAt("/novels");

    expect(await screen.findByText(/新版本 v0\.13 已就绪/)).toBeTruthy();
    expect(container.querySelector('a[rel]')).toBeNull(); // 手动「去下载」不出现
    fireEvent.click(screen.getByRole("button", { name: "重启更新" }));
    await waitFor(() =>
      expect(requestMock).toHaveBeenCalledWith("/update-check/apply", {
        method: "POST",
        quiet: true,
      }),
    );
    await waitFor(() => expect(quitMock).toHaveBeenCalled());
  });

  it("staged 但 /apply 失败：error toast＋按钮恢复（不关窗）", async () => {
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/update-check") {
        return state({ auto: { state: "staged", version: "0.13" } });
      }
      throw new Error("apply refused");
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await mountAt("/novels");
    fireEvent.click(await screen.findByRole("button", { name: "重启更新" }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalled());
    expect(
      (await screen.findByRole("button", { name: "重启更新" })) as HTMLButtonElement,
    ).not.toBeDisabled();
    expect(quitMock).not.toHaveBeenCalled();
  });

  it("「暂不」＝auto-skip（删暂存、本版本不再自动），横幅整体消失", async () => {
    requestMock.mockImplementation(async (path: string) =>
      path === "/update-check"
        ? state({ auto: { state: "staged", version: "0.13" } })
        : { skipped: "0.13" },
    );
    const { container } = await mountAt("/novels");
    fireEvent.click(await screen.findByRole("button", { name: "暂不" }));
    await waitFor(() =>
      expect(requestMock).toHaveBeenCalledWith("/update-check/auto-skip", {
        method: "POST",
        body: JSON.stringify({ version: "0.13" }),
        quiet: true,
      }),
    );
    // 「暂不」＝横幅整体消失（同时关闭记忆面：不再闪回「正在自动准备」假话）
    await waitFor(() => expect(container.querySelector(".update-strip")).toBeNull());
  });

  it("downloading：只说后台准备中，无任何动作钮", async () => {
    requestMock.mockResolvedValue(
      state({ has_update: true, auto: { state: "downloading", version: "0.13" } }),
    );
    const { container } = await mountAt("/novels");
    expect(await screen.findByText(/新版本 v0\.13 正在后台下载/)).toBeTruthy();
    expect(container.querySelector("a[rel]")).toBeNull();
    expect(container.querySelector("button")).toBeNull();
  });

  it("applied：一次笛「已自动更新」，同会话同版本不重弹", async () => {
    requestMock.mockResolvedValue(
      state({ has_update: false, latest: "0.11", auto: { state: "applied", version: "0.13" } }),
    );
    await mountAt("/novels");
    await waitFor(() => expect(toastMock.success).toHaveBeenCalledTimes(1));
    expect(toastMock.success).toHaveBeenCalledWith("已自动更新到 v0.13");
    await mountAt("/novels");
    await waitFor(() => expect(requestMock).toHaveBeenCalledTimes(2));
    expect(toastMock.success).toHaveBeenCalledTimes(1); // 去重
  });
});

describe("UpdateNotice 评审补臂（可见性/安全网/防御）", () => {
  beforeEach(() => {
    requestMock.mockReset();
    vi.resetModules();
    vi.doMock("@/lib/api", () => ({
      request: requestMock,
      errMessage: (e: unknown, fallback?: string) =>
        fallback ?? (e instanceof Error ? e.message : String(e)),
    }));
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  afterEach(() => {
    vi.doUnmock("@/lib/toast");
    vi.restoreAllMocks();
  });

  it("下载百分比：received/total 渲染百分比，received=0 不闪 0%", async () => {
    requestMock.mockResolvedValue(
      state({ has_update: true, auto: { state: "downloading", version: "0.13", received: 45, total: 100 } }),
    );
    await mountAt("/novels");
    expect(await screen.findByText(/正在后台下载 45%/)).toBeTruthy();
  });

  it("下载无进度（received=0）：退化为无百分比文案，不闪 0%", async () => {
    requestMock.mockResolvedValue(
      state({ has_update: true, auto: { state: "downloading", version: "0.13", received: 0, total: 100 } }),
    );
    await mountAt("/novels");
    const el = await screen.findByText(/正在后台下载，就绪后一键安装/);
    expect(el.textContent).not.toContain("0%");
  });

  it("拒绝臂：/apply 失败 toast 带可点击「去下载」出口", async () => {
    const toastMock2 = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
    vi.doMock("@/lib/toast", () => ({ toast: toastMock2 }));
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/update-check") {
        return state({ auto: { state: "staged", version: "0.13" } });
      }
      const err = new Error("auto updates disabled") as Error & { status?: number };
      err.status = 409;
      throw err;
    });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await mountAt("/novels");
    fireEvent.click(await screen.findByRole("button", { name: "重启更新" }));
    await waitFor(() => expect(toastMock2.error).toHaveBeenCalled());
    const call = toastMock2.error.mock.calls[0];
    expect(String(call[0])).toContain("可先手动下载");
    const opts = call[1] as { action?: { label: string } };
    expect(opts.action?.label).toBe("去下载");
    vi.doUnmock("@/lib/toast");
  });

  it("confirm 取消：不调 /apply 不关窗", async () => {
    const applyMock = vi.fn();
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/update-check") {
        return state({ auto: { state: "staged", version: "0.13" } });
      }
      applyMock();
      return { ok: true };
    });
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await mountAt("/novels");
    fireEvent.click(await screen.findByRole("button", { name: "重启更新" }));
    await waitFor(() => expect(applyMock).not.toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "重启更新" })).toBeTruthy();
  });

  it("横幅根节点带 role=status（读屏可播报状态翻转）", async () => {
    requestMock.mockResolvedValue(state());
    const { container } = await mountAt("/novels");
    await waitFor(() => expect(container.querySelector('[role="status"]')).toBeTruthy());
  });
});

describe("UpdateNotice 4c.4 缓修", () => {
  beforeEach(() => {
    requestMock.mockReset();
    vi.resetModules();
    vi.doMock("@/lib/api", () => ({
      request: requestMock,
      errMessage: (e: unknown, fallback?: string) =>
        fallback ?? (e instanceof Error ? e.message : String(e)),
    }));
    delete (window as unknown as { __updateAppliedSeen?: string }).__updateAppliedSeen;
  });

  afterEach(() => {
    vi.doUnmock("@/lib/toast");
  });

  it("StrictMode 双挂载下 applied toast 仍恰一次（effect 承载）", async () => {
    const toastMock3 = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
    vi.doMock("@/lib/toast", () => ({ toast: toastMock3 }));
    requestMock.mockResolvedValue(
      state({ has_update: false, latest: "0.11", auto: { state: "applied", version: "0.13" } }),
    );
    const first = await mountAt("/novels");
    await waitFor(() => expect(toastMock3.success).toHaveBeenCalledTimes(1));
    const second = await mountAt("/novels");
    await waitFor(() => expect(requestMock).toHaveBeenCalledTimes(2));
    expect(toastMock3.success).toHaveBeenCalledTimes(1);
    first.unmount();
    second.unmount();
    vi.doUnmock("@/lib/toast");
  });
});
