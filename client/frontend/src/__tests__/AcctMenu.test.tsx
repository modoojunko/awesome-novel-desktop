import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import type { TierState } from "@/components/novel/license/LicenseProvider";

const logoutMock = vi.fn((..._a: unknown[]) => {
  /* 原实现写 hash 回落地页；此处只断言调用 */
});

vi.mock("@/hooks/useTier");
vi.mock("@/lib/auth", () => ({
  getUsername: vi.fn(() => "writer01"),
  isLoggedIn: vi.fn(() => true),
  logout: (...a: unknown[]) => logoutMock(...a),
}));
vi.mock("@/lib/support", () => ({
  supportUrl: vi.fn(() => Promise.resolve("https://www.awesomenovel.com")),
}));
vi.mock("@/lib/version", () => ({
  formatVersion: (v: string | null) => v ?? "版本未知",
  useClientVersion: () => "v0.19",
}));

function tierState(over: Partial<TierState> = {}): TierState {
  return {
    tier: "pro",
    isFree: false,
    isMember: true,
    expired: false,
    expiresAt: "2126-08-01",
    isPro: true,
    trialRemainingDays: 0,
    entitlement: null,
    entitlementDegraded: false,
    syncFailed: false,
    loading: false,
    error: null,
    refetch: () => {},
    ...over,
  };
}

function mount(ui: ReactNode) {
  return render(<MemoryRouter initialEntries={["/novels"]}>{ui}</MemoryRouter>);
}

beforeEach(() => {
  logoutMock.mockClear();
});

describe("AcctMenu（控制中心面板）", () => {
  it("触发钮短档：PRO 会员 accent", async () => {
    const { default: AcctMenu } = await import("@/components/AcctMenu");
    const { useTier } = await import("@/hooks/useTier");
    vi.mocked(useTier).mockReturnValue(tierState());
    mount(<AcctMenu />);
    const badge = document.querySelector('[data-od-id="acct-badge"]');
    expect(badge?.className).toContain("badge-accent");
    expect(badge?.textContent).toBe("PRO 会员");
  });

  it("失联变色：文案保持既有档位，仅转 warn", async () => {
    const { default: AcctMenu } = await import("@/components/AcctMenu");
    const { useTier } = await import("@/hooks/useTier");
    vi.mocked(useTier).mockReturnValue(tierState({ syncFailed: true }));
    mount(<AcctMenu />);
    const badge = document.querySelector('[data-od-id="acct-badge"]');
    expect(badge?.className).toContain("badge-warn");
    expect(badge?.textContent).toBe("PRO 会员");
  });

  it("面板展开：账号区头完整档 + 承接项齐 + 退出轻确认", async () => {
    const { default: AcctMenu } = await import("@/components/AcctMenu");
    const { useTier } = await import("@/hooks/useTier");
    vi.mocked(useTier).mockReturnValue(tierState());
    mount(<AcctMenu />);
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);

    // 账号区头完整档（用户名 · 完整档文案）
    expect(document.querySelector('[data-od-id="acct-menu-head"]')?.textContent).toContain("writer01");
    expect(document.querySelector('[data-od-id="acct-menu-tier"]')?.textContent).toBe("PRO 会员");
    // 承接项
    expect(document.querySelector('[data-od-id="acct-menu-backup"]')).toBeTruthy();
    expect(document.querySelector('[data-od-id="acct-menu-restore"]')).toBeTruthy();
    expect(document.querySelector('[data-od-id="acct-menu-config"]')).toBeTruthy();
    // 客服外跳锚点（supportUrl 异步解析后渲染）
    await waitFor(() => expect(document.querySelector('[data-od-id="acct-menu-support"]')).toBeTruthy());
    const support = document.querySelector('[data-od-id="acct-menu-support"]') as HTMLAnchorElement;
    expect(support.getAttribute("target")).toBe("_blank");
    expect(support.getAttribute("href")).toBe("https://www.awesomenovel.com");
    // 版本行
    expect(document.querySelector('[data-od-id="acct-menu-version"]')?.textContent).toBe("v0.19");

    // 退出登录轻确认：第一次点击只确认，第二次执行
    const logoutBtn = document.querySelector('[data-od-id="acct-menu-logout"]') as HTMLElement;
    fireEvent.click(logoutBtn);
    expect(logoutBtn.textContent).toContain("确认退出？");
    expect(logoutMock).not.toHaveBeenCalled();
    fireEvent.click(logoutBtn);
    expect(logoutMock).toHaveBeenCalledTimes(1);
  });

  it("工作台语境注入 onBookPrefs：面板含「本书偏好」项且触发回调", async () => {
    const { default: AcctMenu } = await import("@/components/AcctMenu");
    const { useTier } = await import("@/hooks/useTier");
    vi.mocked(useTier).mockReturnValue(tierState());
    const onBookPrefs = vi.fn();
    mount(<AcctMenu onBookPrefs={onBookPrefs} />);
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);
    const item = document.querySelector('[data-od-id="acct-menu-bookprefs"]') as HTMLElement;
    expect(item).toBeTruthy();
    fireEvent.click(item);
    expect(onBookPrefs).toHaveBeenCalledTimes(1);
  });
});
