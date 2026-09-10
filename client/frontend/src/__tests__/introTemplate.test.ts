import { describe, it, expect } from "vitest";
import {
  INTRO_SEGMENTS,
  INTRO_FORMULA,
  TABOO_RULES,
  DONT_DO,
  INTRO_MAX_LEN,
} from "@/lib/introTemplate";

// 简介六段模板单源（genre-signup-redesign tasks 3.1 / D5/D14）
describe("introTemplate 六段模板单源", () => {
  it("六段名与顺序逐字一致", () => {
    expect(INTRO_SEGMENTS.map((s) => s.name)).toEqual([
      "主角身份",
      "本来的生活",
      "突发状况",
      "必须面对的矛盾",
      "不做的后果",
      "做了的可能结局",
    ]);
  });

  it("每段都有成书视角解释与例句（六段同书贯穿）", () => {
    for (const s of INTRO_SEGMENTS) {
      expect(s.why.length).toBeGreaterThan(0);
      expect(s.example.length).toBeGreaterThan(0);
    }
    // 例句同书贯穿：林拾 / 宗门
    expect(INTRO_SEGMENTS[0].example).toContain("林拾");
    expect(INTRO_SEGMENTS[2].example).toContain("修为漏洞");
  });

  it("六段公式由段名拼接（面板底部展示）", () => {
    expect(INTRO_FORMULA).toBe(
      "主角身份 + 本来的生活 + 突发状况 + 必须面对的矛盾 + 不做的后果 + 做了的可能结局",
    );
  });

  it("最后一格固定「可能」结局（指方向、不写死）", () => {
    expect(INTRO_SEGMENTS[5].name).toContain("可能");
  });

  it("禁忌三元＝设定集腔/作者自白/剧透（体检扫描规则）", () => {
    expect([...TABOO_RULES]).toEqual(["设定集腔", "作者自白", "剧透"]);
  });

  it("别踩三条第三项＝写死结局（与禁忌「剧透」不同，勿合并）", () => {
    expect(DONT_DO).toHaveLength(3);
    expect(DONT_DO[2]).toContain("写死结局");
    expect([...TABOO_RULES]).not.toContain("写死结局");
  });

  it("简介上限 500（前后端同源）", () => {
    expect(INTRO_MAX_LEN).toBe(500);
  });
});
