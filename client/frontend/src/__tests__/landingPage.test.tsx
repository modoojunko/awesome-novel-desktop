// 静态首页（LandingPage）契约（覆盖率专项·批 1 第二波）：
//   未登录入口卡三段（品牌/口号/行动路径）· 版本胶囊读烘包版本（dev 不展示、失败静默）·
//   教程外链新窗口 · 登录入口两处。
import { act, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LandingPage from "@/pages/LandingPage";

const requestMock = vi.fn();
vi.mock("@/lib/api", () => ({
  request: (...a: unknown[]) => requestMock(...a),
  getToken: () => null,
}));
vi.mock("@/lib/brand", () => ({ BRAND: { name: "爱小说" } }));

const renderPage = () =>
  render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  requestMock.mockResolvedValue({ current: "0.22" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("LandingPage", () => {
  it("品牌名与版本胶囊：烘包版本以 v 前缀展示", async () => {
    renderPage();
    expect(screen.getByText("AWESOME-NOVEL")).toBeTruthy();
    expect(screen.getByText("爱小说")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("v0.22")).toBeTruthy());
    expect(requestMock).toHaveBeenCalledWith("/update-check", { quiet: true });
  });

  it("dev 构建与非 dev 空值都不展示版本胶囊", async () => {
    requestMock.mockResolvedValue({ current: "dev" });
    const first = renderPage();
    await waitFor(() => expect(screen.getByText("爱小说")).toBeTruthy());
    expect(screen.queryByText("vdev")).toBeNull();
    first.unmount();

    requestMock.mockResolvedValue(null);
    const second = renderPage();
    await waitFor(() => expect(screen.getByText("爱小说")).toBeTruthy());
    expect(second.container.querySelector(".brand-ver")).toBeNull();
  });

  it("版本请求失败：静默无胶囊（deferred reject + 正同步点，失败即红）", async () => {
    let rejectFn: ((e: Error) => void) | undefined;
    requestMock.mockReturnValue(
      new Promise((_res, rej) => {
        rejectFn = rej;
      }),
    );
    const { container } = renderPage();
    await waitFor(() => expect(requestMock).toHaveBeenCalled());
    await act(async () => {
      rejectFn?.(new Error("offline"));
    });
    expect(container.querySelector(".brand-ver")).toBeNull(); // 拒绝之后仍无胶囊（catch 写值即红）
    expect(screen.getByText("人铸灵魂")).toBeTruthy();
  });

  it("行动路径：直接开写/直接登录 → /login；教程 → GitHub 新窗口（noopener）", () => {
    renderPage();
    const start = document.querySelector('[data-od-id="btn-free-start"]') as HTMLAnchorElement;
    expect(start.getAttribute("href")).toBe("/login");
    expect(screen.getByText("直接登录").getAttribute("href")).toBe("/login");
    const tutorial = document.querySelector('[data-od-id="btn-tutorial"]') as HTMLAnchorElement;
    expect(tutorial.getAttribute("target")).toBe("_blank");
    expect(tutorial.getAttribute("rel")).toContain("noopener");
    expect(tutorial.getAttribute("href")).toContain("github.com");
    expect(screen.getByText(/免费版可创建/)).toBeTruthy();
  });
});
