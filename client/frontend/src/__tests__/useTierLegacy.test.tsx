import { beforeEach, describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { useFeature } from "@/hooks/useTier";
import { resetLicenseCache, setVerifyCache } from "@/lib/licenseCache";

/** 旧快照（S端 尚未下发 image-generate）：trial/pro/max 隐式放行，standard/过期仍锁。 */
function snapshot(tier: string, extra: Record<string, unknown> = {}) {
  setVerifyCache({
    tier,
    is_member: true,
    expired: false,
    entitlement: { v: 1, features: ["ai-model"], limits: { max_projects: null } },
    ...extra,
  });
}

const allowed = () => renderHook(() => useFeature("image-generate")).result.current;

describe("useFeature · 旧快照 image-generate 隐式放行（c-image-generation）", () => {
  beforeEach(() => resetLicenseCache());

  it("无 Provider 上下文时 trial/pro/max 与 legacy 别名放行", () => {
    for (const tier of ["trial", "pro", "max", "monthly", "quarterly", "yearly", "lifetime"]) {
      snapshot(tier);
      expect(allowed(), tier).toBe(true);
    }
  });

  it("standard 与过期档仍锁；其他旧 key 不受影响", () => {
    snapshot("standard");
    expect(allowed()).toBe(false);

    snapshot("pro", { expired: true });
    expect(allowed()).toBe(false);

    snapshot("pro");
    expect(renderHook(() => useFeature("ai-detect")).result.current).toBe(false);
  });
});
