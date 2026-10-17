import { describe, expect, it } from "vitest";

import { withAlpha } from "@/lib/color";

describe("withAlpha（旧内核可渲染的内联色）", () => {
  it("hex 三/六/八位", () => {
    expect(withAlpha("#000", 0.14)).toBe("rgba(0, 0, 0, 0.14)");
    expect(withAlpha("#112233", 0.5)).toBe("rgba(17, 34, 51, 0.5)");
    expect(withAlpha("#11223380", 0.5)).toBe("rgba(17, 34, 51, 0.251)");
  });

  it("rgb/rgba 与百分比 alpha", () => {
    expect(withAlpha("rgb(10, 20, 30)", 0.4)).toBe("rgba(10, 20, 30, 0.4)");
    expect(withAlpha("rgba(10, 20, 30, 0.5)", 0.5)).toBe("rgba(10, 20, 30, 0.25)");
    expect(withAlpha("rgb(10 20 30 / 50%)", 0.5)).toBe("rgba(10, 20, 30, 0.25)");
  });

  it("无法解析的形态回落设计令牌", () => {
    expect(withAlpha("var(--badge)", 0.14)).toBe("var(--fg-soft)");
    expect(withAlpha("not-a-color", 0.14)).toBe("var(--fg-soft)");
  });
});
