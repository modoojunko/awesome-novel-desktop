// 认证路由契约（App.tsx + components/auth/AuthGuard.tsx）（覆盖率专项·批 1）：
//   `/` 分流（未登录→落地页 / 已登录→书架）· 旧路由 301（/books、/project/:id）·
//   受保护路由的门禁（无 token → 落登录页）· 未知地址兜底不白屏。
//   子页面全部桩化——这里只钉路由表与门禁，不碰页面实现。
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import AuthGuard from "@/components/auth/AuthGuard";

const authState = { loggedIn: false, token: null as string | null };

vi.mock("@/lib/auth", () => ({
  isLoggedIn: () => authState.loggedIn,
  getToken: () => authState.token,
  getUsername: () => "tester",
  logout: vi.fn(),
}));
vi.mock("@/components/ClientShell", () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="shell">{children}</div>,
}));
vi.mock("@/components/Navbar", () => ({ default: () => <div data-testid="navbar" /> }));
vi.mock("@/components/novel/license/MemberBlockPrompt", () => ({ default: () => null }));
vi.mock("@/pages/LandingPage", () => ({ default: () => <div data-testid="landing" /> }));
vi.mock("@/pages/LoginPage", () => ({ default: () => <div data-testid="login" /> }));
vi.mock("@/pages/ApiKeyConfigPage", () => ({ default: () => <div data-testid="config" /> }));
vi.mock("@/pages/NovelListPage", () => ({ default: () => <div data-testid="shelf" /> }));
vi.mock("@/pages/NovelLayout", () => ({
  default: () => (
    <div data-testid="novel-layout" />
  ),
}));
vi.mock("@/components/novel/NovelWorkspace", () => ({ default: () => <div data-testid="workspace" /> }));

/**
 * 路由抖环探测：App 的 `*` 兜底与 AuthGuard 重定向若被改错会互相喂成死循环
 * （渲染期同步自旋，vitest 的 testTimeout 触发不了 → 挂死到 CI 超时）。
 * 在渲染里计跳数，超阈值直接抛错，把「挂死」变成「红」。
 */
let hops = 0;
function HopGuard() {
  useLocation();
  hops += 1;
  if (hops > 12) throw new Error("路由抖环：重定向目标与兜底路由互相喂（检查 AuthGuard 的 to 与 App 的 * 路由）");
  return null;
}

const at = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <HopGuard />
      <App />
    </MemoryRouter>,
  );

beforeEach(() => {
  authState.loggedIn = false;
  authState.token = null;
  hops = 0;
});

describe("AuthGuard", () => {
  it("无 token：重定向**落到登录页**（断言落点而非 children 为空——否则目标写错只会挂死）", () => {
    render(
      <MemoryRouter initialEntries={["/secret"]}>
        <Routes>
          <Route
            path="/secret"
            element={
              <AuthGuard>
                <div data-testid="inner" />
              </AuthGuard>
            }
          />
          {/* 目标必须是这个探针：AuthGuard 若改成别的路径，这里不渲染 → 用例红 */}
          <Route path="/login" element={<div data-testid="login-slot" />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("inner")).toBeNull();
    expect(screen.getByTestId("login-slot")).toBeTruthy();
  });

  it("有 token：放行 children", () => {
    authState.token = "tok";
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AuthGuard>
          <div data-testid="inner" />
        </AuthGuard>
      </MemoryRouter>,
    );
    expect(screen.getByTestId("inner")).toBeTruthy();
  });
});

describe("App 路由表", () => {
  it("未登录访问 /：显落地页（不进书架）", () => {
    at("/");
    expect(screen.getByTestId("landing")).toBeTruthy();
    expect(screen.queryByTestId("shelf")).toBeNull();
    expect(screen.getByTestId("shell")).toBeTruthy();
    expect(screen.getByTestId("navbar")).toBeTruthy();
  });

  it("已登录访问 /：直落书架（不再看入口卡）", () => {
    authState.loggedIn = true;
    authState.token = "tok";
    at("/");
    expect(screen.getByTestId("shelf")).toBeTruthy();
    expect(screen.queryByTestId("landing")).toBeNull();
  });

  it("/login 与 /config 不受**路由级**门禁（/config 页面自身再跳登录，见 config-page.spec.ts）", () => {
    const first = at("/login").unmount;
    expect(screen.getByTestId("login")).toBeTruthy();
    first();
    at("/config");
    expect(screen.getByTestId("config")).toBeTruthy();
  });

  it("旧地址不白屏：/books 与未知地址都落书架（行为等价，渲染层无法区分 301 与兜底）", () => {
    authState.token = "tok";
    const { unmount } = at("/books");
    expect(screen.getByTestId("shelf")).toBeTruthy();
    unmount();
  });

  it("/project/:id → /novel/:id 且**保留 id**（location 探针断言最终路径）", () => {
    authState.token = "tok";
    let path = "";
    function Probe() {
      path = useLocation().pathname;
      return null;
    }
    render(
      <MemoryRouter initialEntries={["/project/abc"]}>
        <Probe />
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("novel-layout")).toBeTruthy();
    expect(path).toBe("/novel/abc"); // 目标 id 写死也会被这条抓住
  });

  it("受保护路由：无 token 访问 /novels 与 /novel/x 都被门禁挡住（落登录页）", () => {
    const { unmount } = at("/novels");
    expect(screen.queryByTestId("shelf")).toBeNull();
    expect(screen.getByTestId("login")).toBeTruthy();
    unmount();
    at("/novel/abc");
    expect(screen.queryByTestId("novel-layout")).toBeNull();
    expect(screen.getByTestId("login")).toBeTruthy();
  });

  it("未知地址：兜底落书架（不白屏）", () => {
    authState.token = "tok";
    at("/no/such/page");
    expect(screen.getByTestId("shelf")).toBeTruthy();
  });
});
