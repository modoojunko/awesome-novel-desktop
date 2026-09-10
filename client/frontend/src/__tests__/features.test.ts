import { describe, it, expect } from "vitest";
import { FEATURES, isMemberFeature, type FeatureKey } from "@/lib/features";

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

const MEMBER_FEATURES: FeatureKey[] = [
  "settings-ai-fields",
  "outline-advanced-fields",
  "ai-generate",
  "prompt-panel",
];

describe("isMemberFeature — 会员功能矩阵（2026-08-18 口径）", () => {
  it("人工写作能力非会员功能（免费完整可用）", () => {
    for (const key of FREE_FEATURES) {
      expect(isMemberFeature(key), key).toBe(false);
    }
  });

  it("AI 能力是会员功能（入口可见、使用由后端拦截）", () => {
    for (const key of MEMBER_FEATURES) {
      expect(isMemberFeature(key), key).toBe(true);
    }
  });

  it("清单键与两态分组完全覆盖（无遗漏无多键）", () => {
    const keys = Object.keys(FEATURES) as FeatureKey[];
    expect(keys.length).toBe(FREE_FEATURES.length + MEMBER_FEATURES.length);
    for (const key of keys) {
      const inFree = FREE_FEATURES.includes(key);
      const inMember = MEMBER_FEATURES.includes(key);
      expect(inFree || inMember, key).toBe(true);
      expect(FEATURES[key].memberOnly).toBe(inMember);
    }
  });
});
