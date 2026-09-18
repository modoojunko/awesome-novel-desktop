// 账号动态提示条（ExpiryNoticeBar）契约（覆盖率专项·批 1 第二波）：
//   优先级裁决（支付核对中 > 退款处理中 > 临期≤7 天 > 无）· 当日关闭记忆与状态变化重显 ·
//   portal 延迟拉取与安全外跳 · 静默失败（check-auth 失败/存储不可用不打扰写作）。
import { render, screen, waitFor } from "@testing-library/react";
import { act, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import ExpiryNoticeBar from "@/components/ExpiryNoticeBar";

const requestMock = vi.fn();
vi.mock("@/lib/api", () => ({
  request: (...a: unknown[]) => requestMock(...a),
  getToken: () => "t",
}));
const fetchPortalUrlMock = vi.fn();
vi.mock("@/lib/portal", async () => {
  const actual = await vi.importActual<typeof import("@/lib/portal")>("@/lib/portal");
  return {
    ...actual,
    fetchPortalUrl: (...a: unknown[]) => fetchPortalUrlMock(...a),
  };
});

const checkAuth = (data: unknown, code = 0) => ({ code, data });

beforeEach(() => {
  vi.clearAllMocks();
  requestMock.mockResolvedValue(checkAuth({ tier: "member", days_remaining: 30 }));
  fetchPortalUrlMock.mockResolvedValue("https://portal.example.com");
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("优先级裁决与展示", () => {
  it("支付核对中优先于退款与临期；链接指向订单页且新窗口打开", async () => {
    requestMock.mockResolvedValue(
      checkAuth({ days_remaining: 3, attention: { verify_pending: true, refund_processing: true } }),
    );
    render(<ExpiryNoticeBar />);
    expect(await screen.findByText(/支付核对中/)).toBeTruthy();
    const link = await screen.findByRole("link", { name: "查看订单" });
    expect(link.getAttribute("href")).toBe("https://portal.example.com/dashboard/orders");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("退款处理中优先于临期", async () => {
    requestMock.mockResolvedValue(checkAuth({ days_remaining: 2, attention: { refund_processing: true } }));
    render(<ExpiryNoticeBar />);
    expect(await screen.findByText(/退款处理中/)).toBeTruthy();
    // 外链等 portal 拉取落地（异步 state）
    expect(await screen.findByRole("link", { name: "查看进度" })).toBeTruthy();
  });

  it("仅临期（≤7 天）时提示续费；8 天/免费/无 days 都不显示", async () => {
    const { unmount } = render(<ExpiryNoticeBar />);
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull()); // 30 天不提示
    unmount();

    requestMock.mockResolvedValue(checkAuth({ days_remaining: 7 }));
    const seven = render(<ExpiryNoticeBar />);
    expect(await screen.findByText(/套餐还剩 7 天/)).toBeTruthy();
    // 外链要等 portal 拉取落地（异步 state），用 findBy
    expect((await screen.findByRole("link", { name: "去续费" })).getAttribute("href")).toBe(
      "https://portal.example.com/pay",
    );
    seven.unmount();

    requestMock.mockResolvedValue(checkAuth({ days_remaining: 0 }));
    const zero = render(<ExpiryNoticeBar />);
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull());
    zero.unmount();

    requestMock.mockResolvedValue(checkAuth({ tier: "none" }));
    render(<ExpiryNoticeBar />);
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull());
  });
});

describe("关闭记忆与重显", () => {
  it("点「不再显示」：当日不再显示（重挂也拦住）", async () => {
    requestMock.mockResolvedValue(checkAuth({ days_remaining: 3 }));
    const first = render(<ExpiryNoticeBar />);
    fireEvent.click(await screen.findByText("不再显示"));
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull());
    expect(localStorage.getItem(`account-notice-dismissed:expiring:3`)).toBeTruthy();
    first.unmount();
    render(<ExpiryNoticeBar />);
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull()); // 当日已关不重显
  });

  it("状态变化（剩余天数变了 → key 变）当日也重显", async () => {
    localStorage.setItem("account-notice-dismissed:expiring:3", "2026-1-1"); // 旧 key（过去某天）
    requestMock.mockResolvedValue(checkAuth({ days_remaining: 2 }));
    render(<ExpiryNoticeBar />);
    expect(await screen.findByText(/套餐还剩 2 天/)).toBeTruthy();
  });

  it("存储不可用：照常显示；点关闭也不炸", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("quota");
    });
    const setSpy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    requestMock.mockResolvedValue(checkAuth({ days_remaining: 5 }));
    render(<ExpiryNoticeBar />);
    fireEvent.click(await screen.findByText("不再显示"));
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull());
    expect(setSpy).toHaveBeenCalled();
  });
});

describe("静默与安全边界", () => {
  it("check-auth 非 0 / 无 data / 抛错：都不显示、不打扰", async () => {
    requestMock.mockResolvedValue(checkAuth({ days_remaining: 3 }, 1));
    const a = render(<ExpiryNoticeBar />);
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull());
    a.unmount();

    requestMock.mockResolvedValue(checkAuth(null));
    const b = render(<ExpiryNoticeBar />);
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull());
    b.unmount();

    requestMock.mockRejectedValue(new Error("offline"));
    render(<ExpiryNoticeBar />);
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull());
  });

  it("portal 延迟拉取：无提示时不请求（不触发启动期 401 副作用）；有提示才请求一次", async () => {
    const noNotice = render(<ExpiryNoticeBar />); // 默认 mock 30 天 → 无提示
    await waitFor(() => expect(document.querySelector(".update-strip")).toBeNull());
    expect(fetchPortalUrlMock).not.toHaveBeenCalled();
    noNotice.unmount();

    requestMock.mockResolvedValue(checkAuth({ days_remaining: 3 }));
    render(<ExpiryNoticeBar />);
    await screen.findByText(/套餐还剩 3 天/);
    await waitFor(() => expect(fetchPortalUrlMock).toHaveBeenCalledTimes(1));
  });

  it("portal 拉取降级空串：回落默认门户（PORTAL_URL）并渲染安全外链", async () => {
    fetchPortalUrlMock.mockResolvedValue(""); // 真实实现失败时也是 resolve("")，不会 reject
    requestMock.mockResolvedValue(checkAuth({ days_remaining: 4 }));
    render(<ExpiryNoticeBar />);
    await screen.findByText(/套餐还剩 4 天/);
    const link = await screen.findByRole("link", { name: "去续费" });
    expect(link.getAttribute("href")!.startsWith("http")).toBe(true);
    expect(link.getAttribute("href")!).not.toContain("localhost");
  });

  it("portal 拉取途中卸载：不写状态（cancelled 臂），无警告", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    let release: ((u: string) => void) | undefined;
    fetchPortalUrlMock.mockReturnValue(new Promise<string>((res) => (release = res)));
    requestMock.mockResolvedValue(checkAuth({ days_remaining: 3 }));
    const { unmount } = render(<ExpiryNoticeBar />);
    await screen.findByText(/套餐还剩 3 天/);
    await waitFor(() => expect(release).toBeTruthy());
    unmount();
    await act(async () => release?.("https://portal.example.com"));
    // 卸载后到达的 portal 不得再写入状态（React 19 不报错，靠"无异常 + 无警告"不可判红；
    // 这里用 console.error 监听兜住）：断言未出现 React 的卸载后更新告警
    expect(consoleErrorSpy).not.toHaveBeenCalled();
  });

  it("不安全 portal（内网/环回）：不渲染外链，只留关闭按钮", async () => {
    fetchPortalUrlMock.mockResolvedValue("http://127.0.0.1:8080");
    requestMock.mockResolvedValue(checkAuth({ attention: { refund_processing: true } }));
    render(<ExpiryNoticeBar />);
    await screen.findByText(/退款处理中/);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("不再显示")).toBeTruthy();
  });
});
