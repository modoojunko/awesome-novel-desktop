import { describe, expect, it } from "vitest";
import {
  THEMES,
  subThemeEntry,
  subTypesOf,
  themeEntry,
  themeLabel,
} from "@/lib/themeCatalog";

// 题材目录（genre-signup-redesign 6.16/6.17）：
// 每项都要有解读与案例；子类可选，缺子类时展示名就是大类本身。
describe("题材目录", () => {
  it("21 个大类，每个都有解读与至少一个子类", () => {
    expect(THEMES).toHaveLength(21);
    for (const t of THEMES) {
      expect(t.desc.trim()).not.toBe("");
      expect(t.subTypes.length).toBeGreaterThan(0);
    }
  });

  it("每个子类都有解读与案例（缺一不可）", () => {
    for (const t of THEMES) {
      for (const s of t.subTypes) {
        expect(s.desc.trim(), `子类「${s.name}」缺解读`).not.toBe("");
        expect(s.example.trim(), `子类「${s.name}」缺案例`).not.toBe("");
      }
    }
  });

  it("子类必须属于所选大类（换类查不到旧子类）", () => {
    expect(subTypesOf("仙侠/修真").map((s) => s.name)).toEqual([
      "古典仙侠",
      "凡人流",
      "仙魔大战",
      "种田修仙",
    ]);
    expect(subTypesOf("科幻").map((s) => s.name)).not.toContain("凡人流");
    expect(subTypesOf("不存在的题材")).toEqual([]);
  });

  it("解读/案例查得到", () => {
    expect(themeEntry("仙侠/修真")?.desc).toContain("修行阶次");
    expect(subThemeEntry("仙侠/修真", "凡人流")?.desc).toContain("资质平平");
    expect(subThemeEntry("仙侠/修真", "凡人流")?.example).toContain("凡人修仙传");
    expect(subThemeEntry("仙侠/修真", "科幻专属")).toBeUndefined();
  });
});

describe("themeLabel（书卡胶囊 / 书内标签）", () => {
  it("展示位只大类：选了子类也只显示大类（用户 2026-09-10 拍板）", () => {
    expect(themeLabel("仙侠/修真", "凡人流")).toBe("仙侠/修真");
    expect(themeLabel("谍战", "")).toBe("谍战");
    expect(themeLabel("架空古王朝", null)).toBe("架空古王朝");
    expect(themeLabel(" 悬疑 ", undefined)).toBe("悬疑");
  });

  it("两者皆空 → 空串（调用方以「待定题材」占位）", () => {
    expect(themeLabel("", "")).toBe("");
    expect(themeLabel(null, null)).toBe("");
  });
});
