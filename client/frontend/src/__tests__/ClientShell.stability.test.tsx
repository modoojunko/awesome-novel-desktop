import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useEffect, useState, type ReactNode } from "react";

// ---------------------------------------------------------------------------
// 壳层稳定性（c-session-flip-stability）：
//   ① 登录态翻转不重挂壳层组件（UpdateNotice/ExpiryNoticeBar/StatusBar 挂载
//      计数恒 1，各自的启动请求不随翻转重复触发）
//   ② 未登录：LicenseProvider 透传渲染（上下文 null），零认证请求
// ---------------------------------------------------------------------------

const apiPostMock = vi.fn();
const apiGetMock = vi.fn();
const authState = { loggedIn: true };

const mounts = { update: 0, expiry: 0, status: 0 };

beforeEach(() => {
  apiPostMock.mockReset();
  apiGetMock.mockReset();
  apiGetMock.mockResolvedValue({ code: 1 });
  apiPostMock.mockResolvedValue({ tier: "monthly", is_member: true, expired: false });
  authState.loggedIn = true;
  mounts.update = 0;
  mounts.expiry = 0;
  mounts.status = 0;
  vi.resetModules();
  vi.doMock("@/lib/auth", () => ({ isLoggedIn: () => authState.loggedIn }));
  vi.doMock("@/lib/api", () => ({ api: { post: apiPostMock, get: apiGetMock } }));
  vi.doMock("@/hooks/useAuthHeal", () => ({ useAuthHeal: () => {} }));
  vi.doMock("@/components/UpdateNotice", () => ({
    default: () => {
      useEffectMount("update");
      return <div data-testid="update-notice" />;
    },
  }));
  vi.doMock("@/components/ExpiryNoticeBar", () => ({
    default: () => {
      useEffectMount("expiry");
      return <div data-testid="expiry-bar" />;
    },
  }));
  vi.doMock("@/components/StatusBar", () => ({
    default: () => {
      useEffectMount("status");
      return <div data-testid="status-bar" />;
    },
  }));
});

/** 挂载计数探针：每次「真挂载」（effect 运行）+1，重渲染不计数。 */
function useEffectMount(key: "update" | "expiry" | "status") {
  useEffect(() => {
    mounts[key] += 1;
  }, []);
}

function Harness() {
  const [, tick] = useState(0);
  return (
    <MemoryRouter initialEntries={["/novels"]}>
      <button onClick={() => tick((n) => n + 1)}>re-render</button>
      <ClientShellOnce />
    </MemoryRouter>
  );
}

let ClientShellOnce: () => ReactNode;

describe("ClientShell 壳层稳定性", () => {
  it("登录态翻转：壳层组件挂载次数恒 1，不随翻转重挂", async () => {
    const mod = await import("@/components/ClientShell");
    ClientShellOnce = () => <mod.default>{<div data-testid="kid">内容</div>}</mod.default>;

    const ui = render(<Harness />);
    await waitFor(() => {
      expect(ui.getByTestId("kid")).toBeTruthy();
      expect(apiPostMock).toHaveBeenCalled(); // 已登录：verify 已发
    });
    expect(mounts).toEqual({ update: 1, expiry: 1, status: 1 });

    // 翻转 false → true（驱动多次重渲染），壳层组件不重挂
    authState.loggedIn = false;
    await act(async () => {
      ui.getByRole("button", { name: "re-render" }).click();
    });
    authState.loggedIn = true;
    await act(async () => {
      ui.getByRole("button", { name: "re-render" }).click();
    });
    await act(async () => {
      ui.getByRole("button", { name: "re-render" }).click();
    });
    expect(mounts).toEqual({ update: 1, expiry: 1, status: 1 });
    expect(ui.getByTestId("kid")).toBeTruthy(); // 子树存活（未重挂）
  });

  it("未登录：透传渲染（子树可见）、零认证请求", async () => {
    authState.loggedIn = false;
    const mod = await import("@/components/ClientShell");
    ClientShellOnce = () => <mod.default>{<div data-testid="kid">内容</div>}</mod.default>;

    const ui = render(
      <MemoryRouter initialEntries={["/novels"]}>
        <mod.default>
          <div data-testid="kid">内容</div>
        </mod.default>
      </MemoryRouter>,
    );
    expect(ui.getByTestId("kid")).toBeTruthy();
    // 未登录不挂 Provider 取数路径：不发 verify / 不发两跳 check-auth
    await new Promise((r) => setTimeout(r, 20));
    expect(apiPostMock).not.toHaveBeenCalled();
    expect(apiGetMock).not.toHaveBeenCalled();
  });
});
