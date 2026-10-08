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
  // 模型配置＝人工路径能力：免费版也能配（D4/7.1）
  "ai-model",
];

// 四档 AI 矩阵（2026-10-05 拍板）：标准=管流程；PRO=正文＋朱雀；MAX=推演/去AI味/蒸馏
const STANDARD_FEATURES: FeatureKey[] = [
  "settings-ai-fields",
  "outline-advanced-fields",
  "ai-plan",
  "chapter-review",
  "style-suggest",
];

const PRO_FEATURES: FeatureKey[] = ["ai-generate", "prompt-panel", "ai-detect"];

const MAX_FEATURES: FeatureKey[] = ["ai-plot", "ai-polish", "style-quant"];

describe("档位名与锁文案单源（c-rail-tier-badge）", () => {
  it("tierLabel 是档位名唯一来源；upgradeHintOf 与它同源（徽标不会与行内 hint 说两套）", () => {
    expect(tierLabel("free")).toBe("免费");
    expect(tierLabel("standard")).toBe("标准");
    expect(tierLabel("pro")).toBe("PRO");
    expect(tierLabel("max")).toBe("MAX");
    const pairs: Array<[FeatureKey, TierKey]> = [
      ["ai-plan", "standard"],
      ["ai-detect", "pro"],
      ["ai-polish", "max"],
    ];
    for (const [key, tier] of pairs) {
      expect(minTierOf(key), key).toBe(tier);
      expect(upgradeHintOf(key), key).toContain(tierLabel(tier)); // 长口径里必含短名
    }
  });
});

describe("minTierOf — 四档功能矩阵（2026-10-05 拍板）", () => {
  it("人工写作能力免费完整可用", () => {
    for (const key of FREE_FEATURES) {
      expect(minTierOf(key), key).toBe("free");
    }
  });

  it("标准档=AI 管流程＋设定域 AI＋文风建议（正文自己写）", () => {
    for (const key of STANDARD_FEATURES) {
      expect(minTierOf(key), key).toBe("standard");
    }
  });

  it("PRO=正文 AI＋提示词＋朱雀（留 PRO，trial 同权）", () => {
    for (const key of PRO_FEATURES) {
      expect(minTierOf(key), key).toBe("pro");
    }
  });

  it("MAX=剧情推演＋去AI味＋文风蒸馏（style-quant 与 style-suggest 拆 key）", () => {
    for (const key of MAX_FEATURES) {
      expect(minTierOf(key), key).toBe("max");
    }
  });

  it("清单键与四档分组完全覆盖（无遗漏无多键）", () => {
    const keys = Object.keys(FEATURES) as FeatureKey[];
    expect(keys.length).toBe(
      FREE_FEATURES.length + STANDARD_FEATURES.length + PRO_FEATURES.length + MAX_FEATURES.length,
    );
    for (const key of keys) {
      const group = [FREE_FEATURES, STANDARD_FEATURES, PRO_FEATURES, MAX_FEATURES].find((g) =>
        g.includes(key),
      );
      expect(group, key).toBeDefined();
    }
  });

  it("tierRank 序：free < standard < pro < max；未知档回落 free", () => {
    expect(tierRank("free")).toBeLessThan(tierRank("standard"));
    expect(tierRank("standard")).toBeLessThan(tierRank("pro"));
    expect(tierRank("pro")).toBeLessThan(tierRank("max"));
    expect(tierRank("unknown" as TierKey)).toBe(0);
  });

  it("isMemberFeature 兼容派生：minTier>free 即会员功能", () => {
    for (const key of FREE_FEATURES) expect(isMemberFeature(key), key).toBe(false);
    for (const key of [...STANDARD_FEATURES, ...PRO_FEATURES, ...MAX_FEATURES]) {
      expect(isMemberFeature(key), key).toBe(true);
    }
  });
});
