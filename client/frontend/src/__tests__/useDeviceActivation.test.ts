// 设备激活状态（hooks/useDeviceActivation.ts）契约（覆盖率专项·批 1 账号面）：
//   无 token 直接返回 · 成功置态 · 非 2xx/抛错都静默 null · showToast 四态文案。
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDeviceActivation } from "@/hooks/useDeviceActivation";
import { toast } from "@/lib/toast";

vi.mock("@/lib/toast", () => ({
  toast: { success: vi.fn(), info: vi.fn(), error: vi.fn() },
}));

const device = (over: Record<string, unknown> = {}) => ({
  enrolled: true,
  activated: true,
  device_count: 1,
  active_limit: 2,
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("auth_token", "tok-dev");
});

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.removeItem("auth_token");
});

describe("refreshStatus", () => {
  it("无 token：不发请求、返回 null（登录前不探测）", async () => {
    localStorage.removeItem("auth_token");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useDeviceActivation());
    let out: unknown;
    await act(async () => {
      out = await result.current.refreshStatus();
    });
    expect(out).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.loading).toBe(false);
  });

  it("成功：带 Bearer 请求并置 status（loading 从 true 回落 false）", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      json: async () => device({ device_name: "MacBook" }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useDeviceActivation());
    await act(async () => {
      await result.current.refreshStatus();
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/api/auth/devices/current");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer tok-dev");
    expect(result.current.status).toMatchObject({ device_name: "MacBook" });
    expect(result.current.loading).toBe(false);
  });

  it("非 2xx：静默 null、不置态", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 401 })));
    const { result } = renderHook(() => useDeviceActivation());
    let out: unknown = "sentinel";
    await act(async () => {
      out = await result.current.refreshStatus();
    });
    expect(out).toBeNull();
    expect(result.current.status).toBeNull();
    expect(result.current.loading).toBe(false);
  });

  it("网络异常：静默 null（不抛给调用方）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );
    const { result } = renderHook(() => useDeviceActivation());
    let out: unknown = "sentinel";
    await act(async () => {
      out = await result.current.refreshStatus();
    });
    expect(out).toBeNull();
    expect(result.current.loading).toBe(false);
  });
});

describe("showToast 四态", () => {
  it("已注册且已激活 → success（新设备已激活）", async () => {
    const { result } = renderHook(() => useDeviceActivation());
    act(() => result.current.showToast(device() as never));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("新设备已激活，可使用全部功能"));
  });

  it("已注册未激活 → info（免费模式）", async () => {
    const { result } = renderHook(() => useDeviceActivation());
    act(() => result.current.showToast(device({ activated: false }) as never));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("新设备已注册，当前为免费模式"));
  });

  it("未注册未激活 → info（当前设备为免费模式）", async () => {
    const { result } = renderHook(() => useDeviceActivation());
    act(() => result.current.showToast(device({ enrolled: false, activated: false }) as never));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("当前设备为免费模式"));
  });

  it("未注册但已激活 → 不提示（组合不合法，静默）", async () => {
    const { result } = renderHook(() => useDeviceActivation());
    act(() => result.current.showToast(device({ enrolled: false, activated: true }) as never));
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.info).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });
});
