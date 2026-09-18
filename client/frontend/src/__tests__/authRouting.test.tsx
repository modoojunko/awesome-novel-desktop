// 认证路由契约（App.tsx + components/auth/AuthGuard.tsx）（覆盖率专项·批 1）：
//   `/` 分流（未登录→落地页 / 已登录→书架）· 旧路由 301（/books、/project/:id）·
//   受保护路由的门禁（无 token → 落登录页）· 未知地址兜底不白屏。
//   子页面全部桩化——这里只钉路由表与门禁，不碰页面实现。
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
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
    <div data-testid="novel-layout">
      <div data-testid="novel-layout-child" />
    </div>
  ),
}));
vi.mock("@/components/novel/NovelWorkspace", () => ({ default: () => <div data-testid="workspace" /> }));

const at = (path: string) => render(<App />, { wrapper: ({ children }) => <MemoryRouter initialEntries={[path]}>{children}</MemoryRouter> });

beforeEach(() => {
  authState.loggedIn = false;
  authState.token = null;
});

describe("AuthGuard", () => {
  it("无 token：重定向到登录路由", () => {
    render(
      <MemoryRouter initialEntries={["/secret"]}>
        <AuthGuard>
          <div data-testid="inner" />
        </AuthGuard>
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("inner")).toBeNull();
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

  it("/login 与 /config 无需登录即可达", () => {
    const first = at("/login").unmount;
    expect(screen.getByTestId("login")).toBeTruthy();
    first();
    at("/config");
    expect(screen.getByTestId("config")).toBeTruthy();
  });

  it("旧路由 301：/books → 书架；/project/:id → /novel/:id", () => {
    authState.token = "tok";
    const { unmount } = at("/books");
    expect(screen.getByTestId("shelf")).toBeTruthy();
    unmount();
    at("/project/abc");
    expect(screen.getByTestId("novel-layout")).toBeTruthy();
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
