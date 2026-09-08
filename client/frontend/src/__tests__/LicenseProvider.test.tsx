import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

const apiPostMock = vi.fn();
const apiGetMock = vi.fn();

beforeEach(() => {
  apiPostMock.mockReset();
  apiGetMock.mockReset();
  apiGetMock.mockResolvedValue({ code: 1 }); // 两跳刷新的 check-auth 调用默认不命中
  vi.resetModules();
  vi.doMock("@/lib/api", () => ({ api: { post: apiPostMock, get: apiGetMock } }));
});

async function mountUseTier() {
  const { LicenseProvider } = await import(
    "@/components/novel/license/LicenseProvider"
  );
  const { useTier } = await import("@/hooks/useTier");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <MemoryRouter initialEntries={["/"]}>
      <LicenseProvider>{children}</LicenseProvider>
    </MemoryRouter>
  );
  return { renderHook: () => renderHook(() => useTier(), { wrapper }) };
}

describe("LicenseProvider", () => {
  it("挂载时 /auth/verify 仅调一次并下发套餐状态", async () => {
    apiPostMock.mockResolvedValue({
      tier: "monthly",
      is_member: true,
      expired: false,
      expires_at: "2027-01-01",
      trial_remaining_days: 30,
    });
    const m = await mountUseTier();
    const { result } = m.renderHook();
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(apiPostMock).toHaveBeenCalledTimes(1);
    expect(apiPostMock).toHaveBeenCalledWith("/auth/verify");
    expect(result.current.tier).toBe("monthly");
    expect(result.current.isMember).toBe(true);
    expect(result.current.isFree).toBe(false);
    expect(result.current.isPro).toBe(true);
    expect(result.current.trialRemainingDays).toBe(30);
  });

  it("免费套餐 isFree=true", async () => {
    apiPostMock.mockResolvedValue({
      tier: "none",
      is_member: false,
      expired: false,
      trial_remaining_days: 0,
    });
    const m = await mountUseTier();
    const { result } = m.renderHook();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.isFree).toBe(true);
    expect(result.current.isMember).toBe(false);
    expect(result.current.isPro).toBe(false);
  });

  it("过期会员降为免费待遇：isFree=true、expired=true、isPro=false", async () => {
    apiPostMock.mockResolvedValue({
      tier: "monthly",
      is_member: false,
      expired: true,
      expires_at: "2026-01-01",
      trial_remaining_days: 0,
    });
    const m = await mountUseTier();
    const { result } = m.renderHook();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.tier).toBe("monthly");
    expect(result.current.isMember).toBe(false);
    expect(result.current.isFree).toBe(true);
    expect(result.current.expired).toBe(true);
    expect(result.current.isPro).toBe(false);
  });

  it("verify 首次失败：不抛异常，走免费防御态并置失联标志", async () => {
    apiPostMock.mockRejectedValue(new Error("network"));
    const m = await mountUseTier();
    const { result } = m.renderHook();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.tier).toBe("none");
    expect(result.current.isFree).toBe(true);
    expect(result.current.error).toBeTruthy();
    expect(result.current.syncFailed).toBe(true);
  });

  it("已有判定后 verify 失败：保留上次档位不清缓存，仅置失联标志（c-account-control-center 失联口径）", async () => {
    apiPostMock.mockResolvedValue({
      tier: "monthly",
      is_member: true,
      expired: false,
      trial_remaining_days: 30,
    });
    const m = await mountUseTier();
    const { result } = m.renderHook();
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.tier).toBe("monthly");

    // 后续刷新失败：档位文案不变、不清缓存，仅失联标志
    apiPostMock.mockRejectedValue(new Error("network"));
    await result.current.refetch();
    await waitFor(() => expect(result.current.syncFailed).toBe(true));
    expect(result.current.tier).toBe("monthly");
    expect(result.current.isMember).toBe(true);
    expect(result.current.isFree).toBe(false);
  });

  it("两跳刷新 check-auth 失败置失联，档位文案不变（路由 /novels 触发）", async () => {
    apiPostMock.mockResolvedValue({
      tier: "monthly",
      is_member: true,
      expired: false,
      trial_remaining_days: 30,
    });
    apiGetMock.mockRejectedValueOnce(new Error("offline"));
    const { LicenseProvider } = await import(
      "@/components/novel/license/LicenseProvider"
    );
    const { useTier } = await import("@/hooks/useTier");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter initialEntries={["/novels"]}>
        <LicenseProvider>{children}</LicenseProvider>
      </MemoryRouter>
    );
    const { result } = renderHook(() => useTier(), { wrapper });
    await waitFor(() => expect(result.current.syncFailed).toBe(true));
    expect(result.current.tier).toBe("monthly"); // 档位文案不变
  });

  it("两跳刷新 check-auth 成功保持常规色（syncFailed=false）", async () => {
    apiPostMock.mockResolvedValue({
      tier: "monthly",
      is_member: true,
      expired: false,
      trial_remaining_days: 30,
    });
    apiGetMock.mockResolvedValue({ code: 0 });
    const { LicenseProvider } = await import(
      "@/components/novel/license/LicenseProvider"
    );
    const { useTier } = await import("@/hooks/useTier");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter initialEntries={["/novels"]}>
        <LicenseProvider>{children}</LicenseProvider>
      </MemoryRouter>
    );
    const { result } = renderHook(() => useTier(), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.syncFailed).toBe(false);
    expect(result.current.tier).toBe("monthly");
  });

  it("重挂载复用 module 缓存，不再请求", async () => {
    apiPostMock.mockResolvedValue({ tier: "monthly", trial_remaining_days: 30 });
    const m = await mountUseTier();

    const first = m.renderHook();
    await waitFor(() => expect(first.result.current.loading).toBe(false));
    expect(apiPostMock).toHaveBeenCalledTimes(1);

    // 第二个 Provider 实例：缓存命中，0 次新请求
    const second = m.renderHook();
    await waitFor(() => expect(second.result.current.loading).toBe(false));
    expect(apiPostMock).toHaveBeenCalledTimes(1);
    expect(second.result.current.tier).toBe("monthly");
  });
});
