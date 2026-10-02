// 登录页（LoginPage）契约（覆盖率专项·批 1 收尾）：
//   静默检测三态（成功自动登录/失败落卡片/manual_logout 与 401 反弹熔断跳过）·
//   会话失效提示（初读 + 事件补读）· 慢检测提示 · 浏览器授权三态（已有会话/缺地址/轮询成功）·
//   轮询超时与「重新检测」· 异常文案。
import { act, render, screen, waitFor } from "@testing-library/react";
import { fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/pages/LoginPage";
import { toast } from "@/lib/toast";
import { api } from "@/lib/api";

const requestMock = vi.fn();
vi.mock("@/lib/api", () => ({
  request: (...a: unknown[]) => requestMock(...a),
  api: { get: vi.fn(), post: vi.fn() },
}));
vi.mock("@/lib/toast", () => ({ toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() } }));
type DevStatus = { enrolled: boolean; activated: boolean; device_count: number; active_limit: number } | null;
const refreshStatusMock = vi.fn(async (): Promise<DevStatus> => ({ enrolled: true, activated: true, device_count: 1, active_limit: 2 }));
const showToastMock = vi.fn();
vi.mock("@/hooks/useDeviceActivation", () => ({
  useDeviceActivation: () => ({ refreshStatus: refreshStatusMock, showToast: showToastMock, loading: false, status: null }),
}));
vi.mock("@/lib/brand", () => ({ BRAND: { name: "爱小说" } }));

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={["/login"]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/novels" element={<div data-testid="shelf" />} />
      </Routes>
    </MemoryRouter>,
  );

const okAuth = (over: Record<string, unknown> = {}) => ({ code: 0, data: { token: "tok-1", username: "u1", ...over } });
const noAuth = { code: 1, data: null };

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  requestMock.mockResolvedValue(noAuth);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  localStorage.clear();
  sessionStorage.clear();
});

describe("静默检测", () => {
  it("已登录：写凭据 + toast + 设备状态 + 跳书架", async () => {
    requestMock.mockResolvedValue(okAuth());
    renderPage();
    await waitFor(() => expect(screen.getByTestId("shelf")).toBeTruthy());
    expect(localStorage.getItem("auth_token")).toBe("tok-1");
    expect(localStorage.getItem("auth_username")).toBe("u1");
    expect(toast.success).toHaveBeenCalledWith("自动登录成功");
    expect(refreshStatusMock).toHaveBeenCalled();
    expect(showToastMock).toHaveBeenCalled();
  });

  it("未登录：落登录卡片（不发凭据、不跳转）", async () => {
    requestMock.mockResolvedValue(noAuth);
    renderPage();
    expect(await screen.findByText("打开浏览器登录")).toBeTruthy();
    expect(localStorage.getItem("auth_token")).toBeNull();
    expect(screen.queryByTestId("shelf")).toBeNull();
  });

  it("dev-token 不当作已登录（本地开发占位）", async () => {
    requestMock.mockResolvedValue(okAuth({ token: "dev-token" }));
    renderPage();
    expect(await screen.findByText("打开浏览器登录")).toBeTruthy();
  });

  it("check-auth 抛错：静默落卡片", async () => {
    requestMock.mockRejectedValue(new Error("offline"));
    renderPage();
    expect(await screen.findByText("打开浏览器登录")).toBeTruthy();
  });

  it("刚手动退出：跳过自动检测并清标记", async () => {
    sessionStorage.setItem("manual_logout", "1");
    renderPage();
    expect(await screen.findByText("打开浏览器登录")).toBeTruthy();
    expect(requestMock).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("manual_logout")).toBeNull();
  });

  it("3 秒内被 401 踢出：跳过自动登录（反弹熔断，防互踢成环）", async () => {
    sessionStorage.setItem("last_auth_kick_at", String(Date.now()));
    renderPage();
    expect(await screen.findByText("打开浏览器登录")).toBeTruthy();
    expect(requestMock).not.toHaveBeenCalled();
  });

  it("慢检测：2 秒后出现云端唤醒提示", async () => {
    vi.useFakeTimers();
    requestMock.mockReturnValue(new Promise(() => {})); // 永不 resolve
    renderPage();
    expect(screen.queryByText(/正在唤醒云端服务/)).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(screen.getByText(/正在唤醒云端服务/)).toBeTruthy();
  });
});

describe("会话失效提示", () => {
  it("初读 sessionStorage 并在展示后清除", async () => {
    sessionStorage.setItem("auth_notice", "账号已注销");
    renderPage();
    expect(await screen.findByText("账号已注销")).toBeTruthy();
    expect(sessionStorage.getItem("auth_notice")).toBeNull();
  });

  it("挂载后由 auth-notice-updated 事件补读（heal 晚于本页写入）", async () => {
    renderPage();
    await screen.findByText("打开浏览器登录");
    await act(async () => {
      sessionStorage.setItem("auth_notice", "登录已失效，请重新登录");
      window.dispatchEvent(new Event("auth-notice-updated"));
    });
    expect(screen.getByText("登录已失效，请重新登录")).toBeTruthy();
  });
});

describe("浏览器授权", () => {
  it("已有会话：直接写凭据 + 跳转（不开浏览器）", async () => {
    requestMock.mockImplementation(async (path: string) => (path === "/auth/browser-auth" ? okAuth({ token: "tok-2" }) : noAuth));
    const openSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    renderPage();
    fireEvent.click(await screen.findByText("打开浏览器登录"));
    await waitFor(() => expect(screen.getByTestId("shelf")).toBeTruthy());
    expect(localStorage.getItem("auth_token")).toBe("tok-2");
    expect(openSpy).not.toHaveBeenCalled();
  });

  it("缺授权地址：给出可读错误", async () => {
    requestMock.mockImplementation(async (path: string) =>
      path === "/auth/browser-auth" ? { code: 0, data: {} } : noAuth,
    );
    renderPage();
    fireEvent.click(await screen.findByText("打开浏览器登录"));
    expect(await screen.findByText("未能获取授权地址，请稍后重试")).toBeTruthy();
  });

  it("有授权地址：开浏览器 + 轮询到成功即跳转", async () => {
    vi.useFakeTimers();
    const openSpy = vi.fn();
    vi.stubGlobal("open", openSpy);
    let checkAuthCalls = 0;
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/auth/browser-auth") return { code: 0, data: { auth_url: "https://portal.example.com/oauth" } };
      checkAuthCalls += 1;
      // 第 1 次是挂载时的静默检测（失败），轮询里的第 2 次起成功
      return checkAuthCalls <= 1 ? noAuth : okAuth({ token: "tok-poll" });
    });
    renderPage();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByText("打开浏览器登录"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(openSpy).toHaveBeenCalledWith("https://portal.example.com/oauth", "_blank");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100); // 等一轮轮询
    });
    expect(localStorage.getItem("auth_token")).toBe("tok-poll");
    expect(toast.success).toHaveBeenCalledWith("登录成功");
  });

  it("轮询超时：报超时并给出「重新检测」；重检成功即跳转", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("open", vi.fn());
    let allowSuccess = false; // 超时前一律 noAuth；点「重新检测」后才放行
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/auth/browser-auth") return { code: 0, data: { auth_url: "https://portal.example.com/oauth" } };
      return allowSuccess ? okAuth({ token: "tok-retry" }) : noAuth;
    });
    renderPage();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByText("打开浏览器登录"));
    // 推进到超时（60 轮 × 2s + 余量）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 * 62);
    });
    expect(screen.getByText(/授权超时/)).toBeTruthy();
    allowSuccess = true;
    fireEvent.click(screen.getByText("重新检测"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(localStorage.getItem("auth_token")).toBe("tok-retry");
  });

  it("重新检测未通过：给出未检测到提示", async () => {
    requestMock.mockImplementation(async (path: string) =>
      path === "/auth/browser-auth" ? { code: 0, data: { auth_url: "https://portal.example.com/oauth" } } : noAuth,
    );
    vi.stubGlobal("open", vi.fn());
    vi.useFakeTimers();
    renderPage();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByText("打开浏览器登录"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 * 62);
    });
    fireEvent.click(screen.getByText("重新检测"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByText("尚未检测到登录，请确认浏览器已完成后重试")).toBeTruthy();
  });

  it("发起授权请求抛错：报「登录失败」", async () => {
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/auth/browser-auth") throw new Error("boom");
      return noAuth;
    });
    renderPage();
    fireEvent.click(await screen.findByText("打开浏览器登录"));
    expect(await screen.findByText("登录失败")).toBeTruthy();
  });
});

describe("覆盖补齐（边界臂）", () => {
  it("check-auth 无 username：只写 token，不写用户名", async () => {
    requestMock.mockResolvedValue({ code: 0, data: { token: "tok-nouser" } });
    renderPage();
    await waitFor(() => expect(screen.getByTestId("shelf")).toBeTruthy());
    expect(localStorage.getItem("auth_token")).toBe("tok-nouser");
    expect(localStorage.getItem("auth_username")).toBeNull();
  });

  it("设备状态拿不到（refreshStatus 返回 null）：不弹设备提示但照常登录", async () => {
    refreshStatusMock.mockResolvedValueOnce(null);
    requestMock.mockResolvedValue(okAuth());
    renderPage();
    await waitFor(() => expect(screen.getByTestId("shelf")).toBeTruthy());
    expect(showToastMock).not.toHaveBeenCalled();
  });

  it("auth-notice-updated 事件但无提示：不误设文案（假臂）", async () => {
    renderPage();
    await screen.findByText("打开浏览器登录");
    await act(async () => {
      window.dispatchEvent(new Event("auth-notice-updated")); // sessionStorage 里没有 auth_notice
    });
    expect(document.querySelector('[role="status"]')).toBeNull(); // 不出现提示块
  });

  it("浏览器授权已有会话但设备状态拿不到：不弹提示仍跳转（devStatus 假臂）", async () => {
    refreshStatusMock.mockResolvedValueOnce(null);
    requestMock.mockImplementation(async (path: string) => (path === "/auth/browser-auth" ? okAuth({ token: "tok-3" }) : noAuth));
    renderPage();
    fireEvent.click(await screen.findByText("打开浏览器登录"));
    await waitFor(() => expect(screen.getByTestId("shelf")).toBeTruthy());
    expect(showToastMock).not.toHaveBeenCalled();
  });

  it("轮询等待途中卸载：await 之后的取消检查兜住（不再发起下一次 check-auth）", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("open", vi.fn());
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/auth/browser-auth") return { code: 0, data: { auth_url: "https://portal.example.com/oauth" } };
      return noAuth;
    });
    const { unmount } = renderPage();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByText("打开浏览器登录"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000); // 停在 await 2000ms 中间
    });
    const before = requestMock.mock.calls.length;
    unmount(); // cancelledRef = true（await 尚未返回）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100); // await 返回 → L126 分支兜住
    });
    expect(requestMock.mock.calls.length).toBe(before); // 不再发起 check-auth（若删守卫会继续涨）
  });

  it("轮询中 check 挂起时卸载：循环顶部取消检查兜住（不再发起后续 check-auth）", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("open", vi.fn());
    let releaseCheck: ((v: unknown) => void) | undefined;
    let checkCalls = 0;
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/auth/browser-auth") return { code: 0, data: { auth_url: "https://portal.example.com/oauth" } };
      checkCalls += 1;
      if (checkCalls === 1) return noAuth; // 挂载静默检测
      return new Promise((res) => {
        releaseCheck = res; // 第一次轮询的 check 挂起
      });
    });
    const { unmount } = renderPage();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByText("打开浏览器登录"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100); // 睡满 2s → checkAuthorized 挂起
    });
    const before = checkCalls;
    unmount(); // cancelledRef = true（check 仍挂起）
    await act(async () => {
      releaseCheck?.(noAuth); // check 返回失败 → 循环回顶 → L126 兜住
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 * 5);
    });
    expect(checkCalls).toBe(before); // 守卫若失效，会继续发起 check-auth
  });

  it("卸载后不再继续轮询 check-auth（取消守卫的可观测效果：请求数不再增长）", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("open", vi.fn());
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/auth/browser-auth") return { code: 0, data: { auth_url: "https://portal.example.com/oauth" } };
      return noAuth; // 永未登录 → 轮询会一直跑（若无取消守卫）
    });
    const { unmount } = renderPage();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByText("打开浏览器登录"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100); // 跑完整一轮
    });
    const before = requestMock.mock.calls.filter(([p]) => p === "/auth/check-auth").length;
    unmount(); // cancelledRef = true
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 * 10); // 再推 10 轮
    });
    const after = requestMock.mock.calls.filter(([p]) => p === "/auth/check-auth").length;
    expect(after).toBe(before); // 取消守卫若被删，这里会继续涨
  });

  it("旧库计数行：本地旧库有书时升级卡展示书数（present+book_count 分支）", async () => {
    vi.mocked(api.get).mockResolvedValue({
      code: 0,
      data: { present: true, all: [{ book_count: 5 }] }, // latest = all[0]
    });
    // 刻意不给 latest_version / download_url：覆盖 `|| undefined` 的兜底右臂
    requestMock.mockResolvedValue({ code: 3, data: { client_outdated: true } });
    renderPage();
    expect(await screen.findByTestId("upgrade-gate")).toBeTruthy();
    expect(screen.getByText(/5 本书/)).toBeTruthy(); // libraryCount 传进升级卡
    expect(screen.getByText(/0 字/)).toBeTruthy(); // words 恒 0（轻量计数口径）
  });

  it("轮询中 S端 判定客户端过期：就地升级卡并停轮询（不再发 check-auth）", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("open", vi.fn());
    let checkCalls = 0;
    requestMock.mockImplementation(async (path: string) => {
      if (path === "/auth/browser-auth") return { code: 0, data: { auth_url: "https://portal.example.com/oauth" } };
      checkCalls += 1;
      // 第 1 次是挂载静默检测（失败）；轮询里的第 2 次起返回「客户端需更新」
      return checkCalls <= 1 ? noAuth : { code: 3, data: { client_outdated: true, latest_version: "0.30" } };
    });
    renderPage();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    fireEvent.click(screen.getByText("打开浏览器登录"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0); // browser-auth 返回，进入轮询
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100); // 第一轮轮询 → outdated → 停轮询就地升级卡
    });
    expect(screen.getByTestId("upgrade-gate")).toBeTruthy();
    expect(screen.getByText("需要更新")).toBeTruthy();
    const after = checkCalls;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 * 5); // 再推 5 轮的时间
    });
    expect(checkCalls).toBe(after); // 「checked === 'outdated' 即 return」若失效会继续涨
  });

});
