/** 权益同步前端测试（c-s-entitlement-sync）：
 * - verify 透传 entitlement / entitlement_degraded
 * - useFeature 四路（快照命中/未含/无快照兜底/provider 外）
 * - 两跳刷新：路由切换 → GET /auth/check-auth → refetch(POST /auth/verify)，60s 去抖
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, renderHook, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";

const apiPostMock = vi.fn();
const apiGetMock = vi.fn();
const order: string[] = [];

beforeEach(() => {
  apiPostMock.mockReset();
  apiGetMock.mockReset();
  order.length = 0;
  apiPostMock.mockImplementation(async () => {
    order.push("post");
    return { tier: "pro", is_member: true, expired: false };
  });
  apiGetMock.mockImplementation(async () => {
    order.push("get");
    return { code: 0 };
  });
  vi.resetModules();
  vi.doMock("@/lib/api", () => ({ api: { post: apiPostMock, get: apiGetMock } }));
});

const MEMBER_ENT = {
  v: 1,
  features: ["ai-generate"],
  limits: { max_projects: null as number | null },
};

async function mountWithRouter(startPath: string, children: ReactNode) {
  const { LicenseProvider } = await import(
    "@/components/novel/license/LicenseProvider"
  );
  function Nav() {
    const navigate = useNavigate();
    return <button onClick={() => navigate("/novel/1")}>go</button>;
  }
  return render(
    <MemoryRouter initialEntries={[startPath]}>
      <LicenseProvider>
        <Routes>
          <Route path="*" element={<>{children}</>} />
        </Routes>
        <Nav />
      </LicenseProvider>
    </MemoryRouter>,
  );
}

describe("verify 透传", () => {
  it("携带 entitlement 原文与 degraded=false", async () => {
    const { LicenseProvider } = await import(
      "@/components/novel/license/LicenseProvider"
    );
    apiPostMock.mockImplementation(async () => {
      order.push("post");
      return {
        tier: "pro",
        is_member: true,
        expired: false,
        entitlement: MEMBER_ENT,
        entitlement_degraded: false,
      };
    });
    const { useTier } = await import("@/hooks/useTier");
    const { result } = renderHook(() => useTier(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <MemoryRouter initialEntries={["/"]}>
          <LicenseProvider>{children}</LicenseProvider>
        </MemoryRouter>
      ),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entitlement).toEqual(MEMBER_ENT);
    expect(result.current.entitlementDegraded).toBe(false);
  });

  it("degraded=true 时透传标志", async () => {
    const { LicenseProvider } = await import(
      "@/components/novel/license/LicenseProvider"
    );
    apiPostMock.mockImplementation(async () => {
      order.push("post");
      return {
        tier: "pro",
        is_member: true,
        expired: false,
        entitlement_degraded: true,
      };
    });
    const { useTier } = await import("@/hooks/useTier");
    const { result } = renderHook(() => useTier(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <MemoryRouter initialEntries={["/"]}>
          <LicenseProvider>{children}</LicenseProvider>
        </MemoryRouter>
      ),
    });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.entitlementDegraded).toBe(true);
    expect(result.current.entitlement).toBeNull();
  });
});

describe("useFeature", () => {
  it("快照含 key → true；不含 → false", async () => {
    const { LicenseProvider } = await import(
      "@/components/novel/license/LicenseProvider"
    );
    apiPostMock.mockImplementation(async () => {
      order.push("post");
      return { tier: "pro", is_member: true, entitlement: MEMBER_ENT };
    });
    const { useFeature } = await import("@/hooks/useTier");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter initialEntries={["/"]}>
        <LicenseProvider>{children}</LicenseProvider>
      </MemoryRouter>
    );
    const hit = renderHook(() => useFeature("ai-generate"), { wrapper });
    const miss = renderHook(() => useFeature("prompt-panel"), { wrapper });
    await waitFor(() => expect(hit.result.current).toBe(true));
    expect(miss.result.current).toBe(false);
  });

  it("无快照回退静态注册表（会员功能 false / 免费功能 true）", async () => {
    const { LicenseProvider } = await import(
      "@/components/novel/license/LicenseProvider"
    );
    const { useFeature } = await import("@/hooks/useTier");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter initialEntries={["/"]}>
        <LicenseProvider>{children}</LicenseProvider>
      </MemoryRouter>
    );
    const memberKey = renderHook(() => useFeature("ai-generate"), { wrapper });
    const freeKey = renderHook(() => useFeature("tree-crud"), { wrapper });
    await waitFor(() => expect(freeKey.result.current).toBe(true));
    expect(memberKey.result.current).toBe(false);
  });

  it("provider 外走静态兜底且不抛", async () => {
    const { useFeature } = await import("@/hooks/useTier");
    const memberKey = renderHook(() => useFeature("ai-generate"));
    const freeKey = renderHook(() => useFeature("tree-crud"));
    expect(memberKey.result.current).toBe(false);
    expect(freeKey.result.current).toBe(true);
  });
});

describe("两跳刷新（路由切换）", () => {
  it("首次切换触发 check-auth→refetch，60s 内重复切换去抖", async () => {
    apiPostMock.mockImplementation(async () => {
      order.push("post");
      return { tier: "pro", is_member: true, entitlement: MEMBER_ENT };
    });
    const m = await mountWithRouter(
      "/novels",
      <div>probe</div>,
    );
    // 挂载：mount verify(post#1) + 初始路由 /novels 触发两跳（get → post#2）
    await waitFor(() => expect(order.filter((x) => x === "get").length).toBe(1));
    await waitFor(() => expect(order.filter((x) => x === "post").length).toBe(2));
    expect(order[0]).toBe("post"); // 先挂载 verify
    expect(order[1]).toBe("get"); // 再 check-auth（写快照）
    expect(order[2]).toBe("post"); // 后 refetch（读快照）

    // 60s 内再次切换路由：去抖，不新增 get
    fireEvent.click(m.getByText("go"));
    await waitFor(() =>
      expect(order.filter((x) => x === "post").length).toBeGreaterThanOrEqual(2),
    );
    expect(order.filter((x) => x === "get").length).toBe(1);
  });

  it("非权益路由不触发", async () => {
    await mountWithRouter("/", <div>probe</div>);
    await waitFor(() => expect(order.filter((x) => x === "post").length).toBe(1));
    expect(order.filter((x) => x === "get").length).toBe(0);
  });
});
