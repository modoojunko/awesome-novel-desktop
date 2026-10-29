import { describe, expect, it } from "vitest";

import { beatOf, isOverlong, segmentPlan } from "@/lib/volumePacing";

/** 与后端 tests/test_volume_pacing.py 同表驱动（parity：公式必须同输出）。 */
describe("volumePacing 镜像公式", () => {
  it("段表：末段吸收余数（40÷3→13 段，末段 37–40）", () => {
    expect(segmentPlan(40, 3)).toEqual({
      n: 13,
      rem: 1,
      last_from: 37,
      last_to: 40,
    });
  });

  it("段表：整除无余数", () => {
    expect(segmentPlan(40, 4)).toEqual({
      n: 10,
      rem: 0,
      last_from: 37,
      last_to: 40,
    });
  });

  it("段表：目标 0＝1 段占位", () => {
    expect(segmentPlan(0, 3)).toEqual({
      n: 1,
      rem: 0,
      last_from: 1,
      last_to: 0,
    });
  });

  const config = {
    steps_len: 3,
    steps: [
      { n: "遇麻烦", t: "" },
      { n: "用金手指解决", t: "" },
      { n: "变强收尾", t: "" },
    ],
  };

  it("拍位：第 5 章＝段2·第2步", () => {
    expect(beatOf(5, config, 40)).toEqual({
      seg: 2,
      step_idx: 2,
      step_name: "用金手指解决",
    });
  });

  it("拍位：未配置/越界/无目标 → null", () => {
    expect(beatOf(5, null, 40)).toBeNull();
    expect(beatOf(5, config, null)).toBeNull();
    expect(beatOf(41, config, 40)).toBeNull();
    expect(beatOf(0, config, 40)).toBeNull();
  });

  it("拖沓提醒阈值（升级套路 ≥6 章黄牌）", () => {
    expect(isOverlong(5, 6)).toBe(false);
    expect(isOverlong(6, 6)).toBe(true);
  });
});
