// 升级引导弹窗的目标档选择（tier_required）：出口带被点那行的 feature key → 出该档口径；
// 全局入口不带 key → 回退「当前档的下一档」；已含该能力的档位不重复喊同一档。
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import UpgradeModal from "@/components/novel/UpgradeModal";
import { TierContext, type TierState } from "@/components/novel/license/LicenseProvider";
import { resetVerifyCache, setVerifyCache } from "@/lib/licenseCache";
import type { FeatureKey } from "@/lib/features";

// 权益快照（useFeature 走缓存兜底）＋档位上下文（ownRank 判定用）
const V2_PRO = ["ai-plan", "chapter-review", "settings-ai-fields", "style-suggest",
  "outline-advanced-fields", "ai-model", "ai-generate", "prompt-panel", "ai-detect"];

function seed(features: string[], tier = features.length ? "pro" : "free") {
  setVerifyCache({
    tier,
    is_member: features.length > 0,
    entitlement: { v: 2, features, limits: { max_projects: null } },
  });
}

function tierValue(tier: string): TierState {
  return {
    tier,
    isFree: tier === "none" || tier === "free",
    isMember: tier !== "none" && tier !== "free",
    expired: false,
    expiresAt: "",
    isStandard: tier === "standard",
    isPro: tier === "pro" || tier === "max",
    isMax: tier === "max",
    trialRemainingDays: 0,
    entitlement: null,
    entitlementDegraded: false,
    syncFailed: false,
    pack: null,
    loading: false,
    error: null,
    refetch: () => {},
  };
}

function renderModal(extra: { required?: FeatureKey } = {}, tier = "free") {
  return render(
    <TierContext.Provider value={tierValue(tier)}>
      <UpgradeModal open onClose={vi.fn()} {...extra} />
    </TierContext.Provider>,
  );
}

describe("UpgradeModal · 目标档（tier_required）", () => {
  it("出口带 ai-plan（标准档件）：免费用户看到标准档口径", () => {
    resetVerifyCache();
    seed([]);
    renderModal({ required: "ai-plan" });
    expect(screen.getByText("升级标准 · 解锁 AI 能力")).toBeTruthy();
    expect(screen.getByText(/大纲到章纲的 AI 流程/)).toBeTruthy(); // 标准档权益行
    expect(screen.queryByText(/AI 生成正文（流式输出）/)).toBeNull();
  });

  it("出口带 ai-detect（PRO 档件）：标准用户看到 PRO 档口径", () => {
    seed(["ai-plan", "chapter-review", "settings-ai-fields", "style-suggest",
      "outline-advanced-fields", "ai-model"], "standard");
    renderModal({ required: "ai-detect" }, "standard");
    expect(screen.getByText("升级 PRO · 解锁 AI 能力")).toBeTruthy();
    expect(screen.getByText(/AI 生成正文（流式输出）/)).toBeTruthy();
  });

  it("全局入口不带 key：免费→PRO；已有 PRO→MAX（不重复喊 PRO）", () => {
    resetVerifyCache();
    seed([]);
    const free = renderModal();
    expect(screen.getByText("升级 PRO · 解锁 AI 能力")).toBeTruthy();
    free.unmount();

    seed(V2_PRO);
    renderModal({}, "pro");
    expect(screen.getByText("升级 MAX · 解锁剧情推演与去 AI 味")).toBeTruthy();
    expect(screen.getByText(/去AI味/)).toBeTruthy();
    expect(screen.queryByText(/AI 生成正文（流式输出）/)).toBeNull();
  });

  it("试用档（PRO 同权，ownRank 需认 hasPro）：被点件若已含 → 走下一档不重复喊", () => {
    seed(V2_PRO, "trial");
    renderModal({ required: "ai-plan" }, "trial");
    // trial 已含 ai-plan（标准件）→ 不出「升级标准」，按下一档＝MAX
    expect(screen.getByText("升级 MAX · 解锁剧情推演与去 AI 味")).toBeTruthy();
    expect(screen.queryByText("升级标准 · 解锁 AI 能力")).toBeNull();
  });

  it("防御：required 不是登记 key（如误把事件对象传进来）→ 按无 key 回退，不炸", () => {
    resetVerifyCache();
    seed([]);
    renderModal({ required: {} as unknown as FeatureKey });
    expect(screen.getByText("升级 PRO · 解锁 AI 能力")).toBeTruthy();
  });
});
