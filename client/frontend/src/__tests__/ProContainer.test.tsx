import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import {
  TierContext,
  type TierState,
} from "@/components/novel/license/LicenseProvider";
import { useNovelState } from "@/hooks/useNovelState";

// ---------------------------------------------------------------------------
// TE-29 — ProContainer 两态渲染：免费态整棵子树不渲染、零 phase-status 请求；
//   PRO 态渲染并发出 phase-status 请求（N14 / P0 断点 1 第 8 条）
// ---------------------------------------------------------------------------

const apiState = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  fetchPhaseStatus: vi.fn(),
}));

vi.mock("@/lib/api", () => ({ api: apiState }));

beforeEach(() => {
  apiState.get.mockReset();
  apiState.post.mockReset();
  apiState.put.mockReset();
  apiState.patch.mockReset();
  apiState.delete.mockReset();
  apiState.fetchPhaseStatus.mockReset();
});

async function importProContainer() {
  return await import("@/components/novel/ProContainer");
}

function TestTierProvider({
  tier,
  isMember,
  expired = false,
  children,
}: {
  tier: string;
  isMember?: boolean;
  expired?: boolean;
  children: ReactNode;
}) {
  const member = isMember ?? tier !== "none";
  const value: TierState = {
    tier,
    isFree: !member,
    isMember: member,
    expired,
    expiresAt: "",
    isPro: member,
    trialRemainingDays: 0,
    entitlement: null,
    entitlementDegraded: false,
  syncFailed: false,
    loading: false,
    error: null,
    refetch: () => {},
  };
  return <TierContext.Provider value={value}>{children}</TierContext.Provider>;
}

/** 挂在 ProContainer 内的探针：调用 useNovelState（免费态不应挂载）。 */
function PhaseProbe() {
  const { phaseStatus } = useNovelState("p1");
  return <div>{phaseStatus ? "阶段状态已载入" : "阶段状态无"}</div>;
}

describe("ProContainer", () => {
  it("免费态整棵子树不渲染（null），零 phase-status 请求", async () => {
    const ProContainer = (await importProContainer()).default;
    render(
      <TestTierProvider tier="none">
        <ProContainer>
          <PhaseProbe />
        </ProContainer>
      </TestTierProvider>,
    );
    // 探针未挂载 → 其内部 hook 未执行 → 无任何 api.get 请求
    expect(screen.queryByText(/阶段状态/)).toBeNull();
    expect(apiState.get).not.toHaveBeenCalled();
  });

  it("免费态包任意子内容也不渲染", async () => {
    const ProContainer = (await importProContainer()).default;
    render(
      <TestTierProvider tier="none">
        <ProContainer>
          <button>PRO 专属按钮</button>
        </ProContainer>
      </TestTierProvider>,
    );
    expect(screen.queryByText("PRO 专属按钮")).toBeNull();
  });

  it("付费态透传渲染，phase-status 请求发出", async () => {
    apiState.get.mockResolvedValue({
      phases: {
        settings: "pending",
        outline: "pending",
        prompt: "pending",
        write: "pending",
        archive: "pending",
      },
      warnings: [],
    });
    const ProContainer = (await importProContainer()).default;
    render(
      <TestTierProvider tier="monthly">
        <ProContainer>
          <PhaseProbe />
        </ProContainer>
      </TestTierProvider>,
    );
    await waitFor(() =>
      expect(apiState.get).toHaveBeenCalledWith(
        "/novels/p1/workflow/phase-status",
      ),
    );
    expect(await screen.findByText("阶段状态已载入")).toBeDefined();
  });

  it("过期会员降为免费待遇：子树不渲染（与后端 tier_bypass 口径一致）", async () => {
    const ProContainer = (await importProContainer()).default;
    render(
      <TestTierProvider tier="monthly" isMember={false} expired>
        <ProContainer>
          <button>PRO 专属按钮</button>
        </ProContainer>
      </TestTierProvider>,
    );
    expect(screen.queryByText("PRO 专属按钮")).toBeNull();
  });
});
