import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
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
  return render(
    <MemoryRouter initialEntries={["/novels"]}>
      {ui}
      {/* 导航探针：MemoryRouter 不反映到 window.location，靠路由表断言落点 */}
      <Routes>
        <Route path="/novels" element={null} />
        <Route path="/config" element={<div data-od-id="probe-config">config-page</div>} />
      </Routes>
    </MemoryRouter>,
  );
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
    fetchMock.mockClear(); // 不清会跨用例累积（shuffle 下「called 1 times」会假红）
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

  it("409 但 detail 为空串：显示通用文案（api.ts 保证 message 非空）", async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ detail: "" }),
    });
    const alertMock = vi.fn();
    vi.stubGlobal("alert", alertMock);
    armBridge();
    await clickBackup();
    await waitFor(() => expect(alertMock).toHaveBeenCalledWith("请求失败（HTTP 409）"));
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

// ---------------------------------------------------------------------------
// 覆盖补齐（覆盖率专项）：键盘导航 / 外点 / Escape / 无壳分支 / 跳转接线
// ---------------------------------------------------------------------------

describe("AcctMenu 交互分支补齐", () => {
  afterEach(() => {
    // 统一清场：任一断言失败也不再向后续用例泄漏桥/桩/凭据
    vi.unstubAllGlobals();
    delete (window as unknown as { pywebview?: unknown }).pywebview;
    localStorage.removeItem("auth_token");
  });

  async function openMenu(over: Partial<TierState> = {}) {
    const { default: AcctMenu } = await import("@/components/AcctMenu");
    const { useTier } = await import("@/hooks/useTier");
    vi.mocked(useTier).mockReturnValue(tierState(over));
    const utils = mount(<AcctMenu />);
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);
    // 冲刷 supportUrl 等挂载期异步（否则 state 更新落在 act 外，刷屏 act 警告）
    await act(async () => {});
    return utils;
  }
  const item = (id: string) => document.querySelector(`[data-od-id="${id}"]`) as HTMLElement | null;

  it("外点关闭：mousedown 落在面板与触发钮之外 → 收起并复位轻确认", async () => {
    await openMenu();
    expect(item("acct-menu-logout")).toBeTruthy();
    fireEvent.mouseDown(document.body);
    await waitFor(() => expect(document.querySelector('[data-od-id="acct-menu-logout"]')).toBeNull());
  });

  it("Escape 关闭并阻止冒泡（不误触宿主快捷键）", async () => {
    await openMenu();
    const winSpy = vi.fn();
    window.addEventListener("keydown", winSpy);
    // 从面板内子节点派发 → 冒泡到 document 触发组件监听器；stopPropagation 应拦住继续冒泡到 window
    fireEvent.keyDown(document.querySelector('[data-od-id="acct-menu-head"]') as HTMLElement, { key: "Escape" });
    window.removeEventListener("keydown", winSpy);
    await waitFor(() => expect(document.querySelector('[data-od-id="acct-menu-logout"]')).toBeNull());
    expect(winSpy).not.toHaveBeenCalled();
  });

  it("方向键在菜单项间循环，Tab 圈不出面板（含 Shift+Tab 回绕）", async () => {
    await openMenu();
    const items = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].filter(
      (el) => !el.hasAttribute("hidden"),
    );
    expect(items.length).toBeGreaterThan(2);
    items[0].focus();
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[1]);
    items[0].focus();
    fireEvent.keyDown(document, { key: "ArrowUp" });
    expect(document.activeElement).toBe(items[items.length - 1]);
    items[items.length - 1].focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(items[0]);
    items[0].focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(items[items.length - 1]);
    // 焦点不在任何项上（idx === -1）→ 落第一项
    (document.body as HTMLElement).focus();
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[0]);
  });

  it("无壳：备份与恢复都给出桌面版提示（不静默）", async () => {
    const alertMock = vi.fn();
    vi.stubGlobal("alert", alertMock);
    delete (window as unknown as { pywebview?: unknown }).pywebview;
    await openMenu();
    fireEvent.click(item("acct-menu-backup") as HTMLElement);
    await waitFor(() => expect(alertMock).toHaveBeenCalledWith("备份功能需要桌面版应用"));
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);
    fireEvent.click(item("acct-menu-restore") as HTMLElement);
    await waitFor(() => expect(alertMock).toHaveBeenCalledWith("恢复功能需要桌面版应用"));
    vi.unstubAllGlobals();
  });

  it("用户在文件夹选择器里取消：不发请求、不提示", async () => {
    const alertMock = vi.fn();
    vi.stubGlobal("alert", alertMock);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_folder: vi.fn(async () => null) },
    };
    await openMenu();
    fireEvent.click(item("acct-menu-backup") as HTMLElement);
    await waitFor(() => expect((window as unknown as { pywebview?: { api?: { pick_folder: unknown } } }).pywebview?.api?.pick_folder).toHaveBeenCalled());
    expect(fetchMock).not.toHaveBeenCalled();
    expect(alertMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("模型配置项：关面板并跳 /config（探针路由断言落点）", async () => {
    await openMenu();
    fireEvent.click(item("acct-menu-config") as HTMLElement);
    await waitFor(() => expect(document.querySelector('[data-od-id="acct-menu-config"]')).toBeNull());
    expect(document.querySelector('[data-od-id="probe-config"]')).toBeTruthy();
  });

  it("恢复项：有壳时打开恢复弹窗；取消走 onClose 接线", async () => {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_open_file: vi.fn(async () => []) },
    };
    await openMenu();
    fireEvent.click(item("acct-menu-restore") as HTMLElement);
    await waitFor(() => expect(document.querySelector(".mcard")).toBeTruthy());
    fireEvent.click(screen.getByText("取消"));
    await waitFor(() => expect(document.querySelector(".mcard")).toBeNull());
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("恢复完成页「去检查模型配置」：关弹窗并跳 /config（onGoConfig 接线）", async () => {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_open_file: vi.fn(async () => ["/tmp/pkg.zip"]) },
    };
    const fetchMock = vi.fn().mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { books: [], config: null, warnings: [], schema_version: 1 } }) };
      }
      if (String(url).includes("/backup/import/persist")) {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { results: [{ book_id: "b1", status: "ok" }], warnings: [], reattach: { mode: "none", attached: 0 } } }) };
      }
      return { ok: true, status: 200, json: async () => [] };
    });
    vi.stubGlobal("fetch", fetchMock);
    localStorage.setItem("auth_token", "t");
    await openMenu();
    fireEvent.click(item("acct-menu-restore") as HTMLElement);
    await waitFor(() => expect(document.querySelector(".mcard")).toBeTruthy());
    fireEvent.click(screen.getAllByText("选择文件")[0]);
    await waitFor(() => expect((screen.getByText("下一步") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    fireEvent.click(screen.getByText("确认恢复"));
    await waitFor(() => expect(screen.getByText("去检查模型配置")).toBeTruthy());
    fireEvent.click(screen.getByText("去检查模型配置"));
    await waitFor(() => expect(document.querySelector(".mcard")).toBeNull());
    expect(document.querySelector('[data-od-id="probe-config"]')).toBeTruthy(); // onGoConfig 真跳转
    vi.unstubAllGlobals();
    localStorage.removeItem("auth_token");
    delete (window as unknown as { pywebview?: unknown }).pywebview;
  });

  it("无关按键不影响焦点；焦点不在项上时方向键落第一项", async () => {
    await openMenu();
    const items = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].filter(
      (el) => !el.hasAttribute("hidden"),
    );
    items[0].focus();
    fireEvent.keyDown(document, { key: "a" }); // 非 Arrow/Tab → 直接返回
    expect(document.activeElement).toBe(items[0]);
    (document.activeElement as HTMLElement | null)?.blur(); // idx === -1
    fireEvent.keyDown(document, { key: "ArrowDown" });
    expect(document.activeElement).toBe(items[0]);
  });

  it("展开态点触发钮收起面板；点「联系客服」也收起", async () => {
    await openMenu();
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);
    await waitFor(() => expect(document.querySelector('[data-od-id="acct-menu-logout"]')).toBeNull());
    // 重新展开后点客服链接（外跳由 target=_blank 承担，这里钉住 close 接线）
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);
    await waitFor(() => expect(document.querySelector('[data-od-id="acct-menu-support"]')).toBeTruthy());
    fireEvent.click(document.querySelector('[data-od-id="acct-menu-support"]') as HTMLElement);
    await waitFor(() => expect(document.querySelector('[data-od-id="acct-menu-support"]')).toBeNull());
  });

  it("面板开合不重挂恢复弹窗：预览步状态保留（单点渲染回归）", async () => {
    (window as unknown as { pywebview?: unknown }).pywebview = {
      api: { pick_open_file: vi.fn(async () => ["/tmp/pkg.zip"]) },
    };
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async (url: string) => {
      if (String(url).includes("/backup/import/parse")) {
        return { ok: true, status: 200, json: async () => ({ code: 0, data: { books: [], config: null, warnings: [], schema_version: 1 } }) };
      }
      return { ok: true, status: 200, json: async () => [] };
    }));
    await openMenu();
    fireEvent.click(item("acct-menu-restore") as HTMLElement);
    await waitFor(() => expect(document.querySelector(".mcard")).toBeTruthy());
    fireEvent.click(screen.getAllByText("选择文件")[0]);
    await waitFor(() => expect((screen.getByText("下一步") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText("下一步"));
    await waitFor(() => expect(screen.getByText("确认恢复")).toBeTruthy());
    // 开、合面板各一次：弹窗若被重挂会退回选包步（旧实现两支 return 换位 → React 重挂）
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);
    await waitFor(() => expect(document.querySelector('[data-od-id="acct-menu-head"]')).toBeTruthy());
    fireEvent.click(document.querySelector('[data-od-id="acct-trigger"]') as HTMLElement);
    expect(screen.getByText("确认恢复")).toBeTruthy(); // 仍在预览步
    vi.unstubAllGlobals();
  });

  it("面板内空白处 mousedown：不触发外点关闭（短路臂）", async () => {
    await openMenu();
    fireEvent.mouseDown(document.querySelector('[data-od-id="acct-menu"]') as HTMLElement);
    expect(document.querySelector('[data-od-id="acct-menu-head"]')).toBeTruthy(); // 仍开着
  });

  it("Shift+Tab 且焦点不在首项：回退一位（内层 cond 的另一臂）", async () => {
    await openMenu();
    const items = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].filter(
      (el) => !el.hasAttribute("hidden"),
    );
    items[1].focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(items[0]);
  });

  it("未登录态：头像降级图标、名字「未登录」、无 title、名字转 muted", async () => {
    const { getUsername } = await import("@/lib/auth");
    const mocked = getUsername as unknown as ReturnType<typeof vi.fn>;
    const prev = mocked.getMockImplementation?.();
    mocked.mockReturnValue(null);
    try {
      await openMenu();
      const head = document.querySelector('[data-od-id="acct-menu-head"]') as HTMLElement;
      const name = head.querySelector(".am-name") as HTMLElement;
      expect(name.textContent).toBe("未登录");
      expect(name.getAttribute("title")).toBeNull();
      expect(name.getAttribute("style") ?? "").toContain("muted");
      expect(head.querySelector(".avatar svg")).toBeTruthy(); // 无用户名 → Ico
      // 触发钮同样走 Ico 分支
      expect(document.querySelector('[data-od-id="acct-trigger"] .avatar svg')).toBeTruthy();
    } finally {
      mocked.mockImplementation?.(prev as never);
    }
  });

  it("档位徽章：loading 呈省略号；无档位信息时不渲染徽章", async () => {
    const first = await openMenu({ loading: true });
    expect(document.querySelector('[data-od-id="acct-badge"]')?.textContent).toBe("…");
    first.unmount();
    const second = await openMenu({ tier: undefined as unknown as TierState["tier"] });
    expect(document.querySelector('[data-od-id="acct-badge"]')).toBeNull();
    second.unmount();
  });
});
