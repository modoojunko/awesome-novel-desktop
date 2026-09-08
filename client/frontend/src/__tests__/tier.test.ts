import { describe, expect, it } from "vitest";
import { tierLabel, tierShort } from "../lib/tier";

describe("tierShort（触发钮短档四态）", () => {
  it("PRO 会员：accent", () => {
    expect(tierShort({ tier: "pro", is_member: true, expired: false, trial_remaining_days: 0 })).toEqual({
      text: "PRO 会员",
      tone: "accent",
    });
  });

  it("试用充裕：muted 带天数", () => {
    expect(tierShort({ tier: "trial", is_member: false, expired: false, trial_remaining_days: 12 })).toEqual({
      text: "试用 · 剩 12 天",
      tone: "muted",
    });
  });

  it("试用临期 ≤3 天（含 0 天）：warn", () => {
    expect(tierShort({ tier: "trial", expired: false, trial_remaining_days: 2 })?.tone).toBe("warn");
    expect(tierShort({ tier: "trial", expired: false, trial_remaining_days: 0 })?.tone).toBe("warn");
    expect(tierShort({ tier: "trial", expired: false, trial_remaining_days: 0 })?.text).toBe("试用 · 剩 0 天");
  });

  it("已过期与从未付费同为免费版（合并单档，muted）", () => {
    expect(tierShort({ tier: "pro", is_member: false, expired: true })).toEqual({ text: "免费版", tone: "muted" });
    expect(tierShort({ tier: "none", is_member: false, expired: false })).toEqual({ text: "免费版", tone: "muted" });
  });

  it("无判定数据返回 null（不硬造档位）", () => {
    expect(tierShort(null)).toBeNull();
  });
});

describe("tierLabel（面板头完整档）", () => {
  it("判定优先级：expired 先于 is_member/trial", () => {
    expect(tierLabel({ tier: "pro", is_member: true, expired: true })).toBe("套餐已过期 · 免费待遇");
  });

  it("试用无天数不硬造「剩 0 天」", () => {
    expect(tierLabel({ tier: "trial", expired: false })).toBe("试用中");
  });

  it("会员文案统一「PRO 会员」（归一 BookPrefsModal 旧「PRO 版 · AI 能力已解锁」）", () => {
    expect(tierLabel({ tier: "pro", is_member: true, expired: false })).toBe("PRO 会员");
    expect(tierLabel({ tier: "none", is_member: false, expired: false })).toBe("免费版 · 单机使用");
  });
});
