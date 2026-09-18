import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
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
  // lib/api.ts 依赖 getToken 注入 Authorization（漏了这个导出 → request() 建头即抛，
  // 备份用例会以"同一个兜底文案"假绿——2026-09-18 调试实锤）
  getToken: () => localStorage.getItem("auth_token"),
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

// ---------------------------------------------------------------------------
// 备份入口（#346 起的裸 fetch 401 缺陷；评审 P1：修复点必须有守卫，否则可再次静默回归）
// ---------------------------------------------------------------------------

describe("AcctMenu 备份发起（鉴权头 + 错误文案守卫）", () => {
  const fetchMock = vi.fn();

  function armBridge() {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(async () => "/tmp/backup-out") },
    };
  }

  async function clickBackup() {
    const { default: AcctMenu } = await import("@/components/AcctMenu");
    const { useTier } = await import("@/hooks/useTier");
    vi.mocked(useTier).mockReturnValue(tierState());
    mount(<AcctMenu />);
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);
    fireEvent.click(document.querySelector('[data-od-id="acct-menu-backup"]') as HTMLElement);
  }

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("auth_token", "backup-token");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.removeItem("auth_token");
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("发起走带 Authorization 的 POST（裸 fetch 曾致 401）", async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ code: 0, data: { state: "running" } }),
    });
    const alertMock = vi.fn();
    vi.stubGlobal("alert", alertMock);
    armBridge();
    await clickBackup();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain("/api/backup/export/start");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer backup-token");
    expect(JSON.parse(String(init.body))).toMatchObject({ kind: "backup", target_dir: "/tmp/backup-out" });
    await waitFor(() => expect(alertMock).toHaveBeenCalledWith("备份已开始，完成后文件将保存在所选目录"));
  });

  it("409：按 running_kind 说人话（已有下载任务在进行中）", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: { message: "已有下载任务在进行中", running_kind: "download" } }),
    });
    const alertMock = vi.fn();
    vi.stubGlobal("alert", alertMock);
    armBridge();
    await clickBackup();
    await waitFor(() => expect(alertMock).toHaveBeenCalledWith("已有下载任务在进行中"));
  });

  it("5xx / 网络层失败：中文兜底，不漏英文 statusText", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: async () => {
        throw new Error("not json");
      },
    });
    const alertMock = vi.fn();
    vi.stubGlobal("alert", alertMock);
    armBridge();
    await clickBackup();
    await waitFor(() => expect(alertMock).toHaveBeenCalledWith("备份启动失败：请重试"));
  });
});
