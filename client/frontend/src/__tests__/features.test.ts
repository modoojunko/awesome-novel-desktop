import { describe, it, expect } from "vitest";
import { FEATURES, isMemberFeature, minTierOf, tierLabel, tierRank, upgradeHintOf, type FeatureKey, type TierKey } from "@/lib/features";

const FREE_FEATURES: FeatureKey[] = [
  "tree-crud",
  "prose-edit",
  "version-history",
  "archive",
  "volume-chapter-config",
  "advanced-config-entry",
  "settings-7-items",
  "ai-model",
];

// 三档会员（2026-11-25）：PRO=AI 写手（旧 standard AI keys + 旧 PRO + 官方库）；
// MAX=写作秘书（人味/图像/建书/发散/推演/蒸馏）。
const PRO_FEATURES: FeatureKey[] = [
  "settings-ai-fields",
  "assistant-execute",
  "outline-advanced-fields",
  "ai-plan",
  "chapter-review",
  "style-suggest",
  "ai-generate",
  "prompt-panel",
  "ai-detect",
  "deconstruct",
  "kb-official",
];

const MAX_FEATURES: FeatureKey[] = [
  "image-generate",
  "human-taste",
  "ai-plot",
  "style-quant",
  "deconstruct-import",
  "assistant-diverge",
];

describe("档位名与锁文案单源（三档会员）", () => {
  it("tierLabel 是档位名唯一来源；upgradeHintOf 与它同源", () => {
    expect(tierLabel("free")).toBe("标准");
    expect(tierLabel("standard")).toBe("标准会员（旧）");
    expect(tierLabel("pro")).toBe("PRO");
    expect(tierLabel("max")).toBe("MAX");
    const pairs: Array<[FeatureKey, TierKey]> = [
      ["ai-plan", "pro"],
      ["ai-detect", "pro"],
      ["human-taste", "max"],
    ];
    for (const [key, tier] of pairs) {
      expect(minTierOf(key), key).toBe(tier);
      expect(upgradeHintOf(key), key).toContain(tierLabel(tier));
    }
  });
});

describe("minTierOf — 三档功能矩阵（2026-11-25 拍板）", () => {
  it("标准（免费）只有基础能力", () => {
    for (const key of FREE_FEATURES) {
      expect(minTierOf(key), key).toBe("free");
    }
  });

  it("PRO=AI 写手（规划/章纲/正文/执行 + 官方库 + 拆书 + 朱雀）", () => {
    for (const key of PRO_FEATURES) {
      expect(minTierOf(key), key).toBe("pro");
    }
  });

  it("MAX=写作秘书（人味/图像/建书/发散/推演/蒸馏）", () => {
    for (const key of MAX_FEATURES) {
      expect(minTierOf(key), key).toBe("max");
    }
  });

  it("清单键与三档分组完全覆盖（无遗漏无多键）", () => {
    const keys = Object.keys(FEATURES) as FeatureKey[];
    expect(keys.length).toBe(FREE_FEATURES.length + PRO_FEATURES.length + MAX_FEATURES.length);
    for (const key of keys) {
      const group = [FREE_FEATURES, PRO_FEATURES, MAX_FEATURES].find((g) => g.includes(key));
      expect(group, key).toBeDefined();
    }
  });

  it("tierRank 序：free < standard(legacy) < pro < max；未知档回落 free", () => {
    expect(tierRank("free")).toBeLessThan(tierRank("standard"));
    expect(tierRank("standard")).toBeLessThan(tierRank("pro"));
    expect(tierRank("pro")).toBeLessThan(tierRank("max"));
    expect(tierRank("unknown" as TierKey)).toBe(0);
  });

  it("isMemberFeature 兼容派生：minTier>free 即会员功能", () => {
    for (const key of FREE_FEATURES) expect(isMemberFeature(key), key).toBe(false);
    for (const key of [...PRO_FEATURES, ...MAX_FEATURES]) {
      expect(isMemberFeature(key), key).toBe(true);
    }
  });
});
