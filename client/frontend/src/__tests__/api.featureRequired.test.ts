import { describe, it, expect, vi } from "vitest";

describe("api.feature_required 分支覆盖（tier-plan-four-tiers）", () => {
  function stub403(detail: unknown) {
    const dispatch = vi.fn();
    window.dispatchEvent = dispatch as unknown as typeof window.dispatchEvent;
    const origFetch = globalThis.fetch;
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail }), { status: 403 })) as typeof fetch;
    return { dispatch, restore: () => { globalThis.fetch = origFetch; } };
  }

  it("403 feature_required 广播 member-block（带 feature/tierRequired）并抛错", async () => {
    const { dispatch, restore } = stub403({
      reason: "feature_required", message: "当前套餐不含该能力",
      feature: "ai-plot", tier_required: "max",
    });
    try {
      const { api } = await import("@/lib/api");
      await expect(api.post("/x")).rejects.toThrow("当前套餐不含该能力");
      expect(dispatch).toHaveBeenCalledTimes(1);
      const ev = dispatch.mock.calls[0][0] as CustomEvent;
      expect(ev.type).toBe("member-block");
      expect(ev.detail.feature).toBe("ai-plot");
      expect(ev.detail.tierRequired).toBe("max");
    } finally {
      restore();
    }
  });

  it("无 message 走兜底文案；quiet 不广播仍抛错", async () => {
    const { dispatch, restore } = stub403({ reason: "feature_required" });
    try {
      const { api } = await import("@/lib/api");
      await expect(api.post("/x")).rejects.toThrow("当前套餐不含该能力");
      expect(dispatch).toHaveBeenCalledTimes(1);
      dispatch.mockClear();
      await expect(api.post("/x", undefined, { quiet: true })).rejects.toThrow();
      expect(dispatch).not.toHaveBeenCalled();
    } finally {
      restore();
    }
  });
});
