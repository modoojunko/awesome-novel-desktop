import { beforeEach, describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { useFeature } from "@/hooks/useTier";
import { resetLicenseCache, setVerifyCache } from "@/lib/licenseCache";

/** 旧快照（S端 尚未下发新 key）：按 key 最低档隐式放行，standard/过期仍锁。
 *  image-generate/deconstruct=PRO 起（trial 同权）；deconstruct-import=仅 MAX。 */
function snapshot(tier: string, extra: Record<string, unknown> = {}) {
  setVerifyCache({
    tier,
    is_member: true,
    expired: false,
    entitlement: { v: 1, features: ["ai-model"], limits: { max_projects: null } },
    ...extra,
  });
}

const allowedFor = (key: Parameters<typeof useFeature>[0]) =>
  renderHook(() => useFeature(key)).result.current;

describe("useFeature · 旧快照隐式放行（c-image-generation / c-deconstruct-tier）", () => {
  beforeEach(() => resetLicenseCache());

  it("PRO 键（image-generate/deconstruct）：trial/pro/max 与 legacy 别名放行", () => {
    for (const key of ["image-generate", "deconstruct"] as const) {
      for (const tier of ["trial", "pro", "max", "monthly", "quarterly", "yearly", "lifetime"]) {
        snapshot(tier);
        expect(allowedFor(key), `${key} @ ${tier}`).toBe(true);
      }
    }
  });

  it("MAX 键（deconstruct-import）：仅 max/lifetime 放行，trial/pro 不放行", () => {
    for (const tier of ["max", "lifetime"]) {
      snapshot(tier);
      expect(allowedFor("deconstruct-import"), tier).toBe(true);
    }
    for (const tier of ["trial", "pro", "monthly", "quarterly", "yearly", "standard"]) {
      snapshot(tier);
      expect(allowedFor("deconstruct-import"), tier).toBe(false);
    }
  });

  it("standard 与过期档仍锁；其他旧 key 不受影响", () => {
    snapshot("standard");
    expect(allowedFor("image-generate")).toBe(false);
    expect(allowedFor("deconstruct")).toBe(false);

    snapshot("pro", { expired: true });
    expect(allowedFor("image-generate")).toBe(false);
    expect(allowedFor("deconstruct")).toBe(false);

    snapshot("pro");
    expect(renderHook(() => useFeature("ai-detect")).result.current).toBe(false);
  });
});
