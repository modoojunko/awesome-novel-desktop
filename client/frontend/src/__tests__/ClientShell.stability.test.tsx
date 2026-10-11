import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
  vi.doMock("@/lib/auth", () => ({
    isLoggedIn: () => authState.loggedIn,
    // 顶栏上移壳层后随居挂载：账户胶囊要.getUsername/logout（仅挂载读取，点击才用 logout）
    getUsername: () => (authState.loggedIn ? "tester" : ""),
    logout: () => {},
  }));
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

/** 顶栏（Navbar）上移壳层后随居挂载，其账户胶囊走 react-query——harness 补 Provider。 */
function makeClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function Harness() {
  const [, tick] = useState(0);
  const [client] = useState(makeClient);
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/novels"]}>
        <button onClick={() => tick((n) => n + 1)}>re-render</button>
        <ClientShellOnce />
      </MemoryRouter>
    </QueryClientProvider>
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

    const ui = render(
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter initialEntries={["/novels"]}>
          <mod.default>
            <div data-testid="kid">内容</div>
          </mod.default>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(ui.getByTestId("kid")).toBeTruthy();
    // 未登录不挂 Provider 取数路径：不发 verify / 不发两跳 check-auth
    await new Promise((r) => setTimeout(r, 20));
    expect(apiPostMock).not.toHaveBeenCalled();
    expect(apiGetMock).not.toHaveBeenCalled();
  });

  // ── c-update-strip-below-appbar：提示条挂顶栏之下，不把顶栏推离窗口顶 ──

  it("常规屏 DOM 序：顶栏 → 更新条 → 到期条 → 页面内容", async () => {
    const mod = await import("@/components/ClientShell");
    const ui = render(
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter initialEntries={["/novels"]}>
          <mod.default>
            <div data-testid="kid">内容</div>
          </mod.default>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const appbar = ui.container.querySelector(".appbar");
    const update = ui.getByTestId("update-notice");
    const expiry = ui.getByTestId("expiry-bar");
    const kid = ui.getByTestId("kid");
    expect(appbar).toBeTruthy();
    // compareDocumentPosition(a) 的 FOLLOWING 位：a 在参照节点之后 → 参照在前
    expect(appbar!.compareDocumentPosition(update) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(update.compareDocumentPosition(expiry) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(expiry.compareDocumentPosition(kid) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("书内态（/novel/*）：壳层顶栏与两条提示条整组让位", async () => {
    const mod = await import("@/components/ClientShell");
    const ui = render(
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter initialEntries={["/novel/b1"]}>
          <mod.default>
            <div data-testid="kid">内容</div>
          </mod.default>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(ui.container.querySelector(".appbar")).toBeNull();
    expect(ui.queryByTestId("update-notice")).toBeNull();
    expect(ui.queryByTestId("expiry-bar")).toBeNull();
    expect(ui.getByTestId("kid")).toBeTruthy();
  });
});
