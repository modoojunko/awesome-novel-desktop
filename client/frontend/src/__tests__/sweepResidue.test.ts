import { describe, expect, it } from "vitest";
// 脚本是 .mjs（无类型声明，TS 按 JS 推断）；这里只测它的纯函数口径
import { isTestName } from "../../scripts/sweep-e2e-residue.mjs";

// e2e 残留清理的命名守卫（2026-09-10）：
// 只有「测试命名约定」的书/配置/用户才会被扫，真书真配置一律不碰。
describe("sweep-e2e-residue.isTestName", () => {
  it("测试书命名 → 命中（短词+数字 / e2e- / probe-）", () => {
    for (const n of [
      "题材1234",
      "落点28751",
      "预览读78194",
      "e2e-oad-起草-1789033069016",
      "probe_1789023432129",
    ]) {
      expect(isTestName(n), n).toBe(true);
    }
  });

  it("e2e 用户 id（mm_/shot_ 前缀）不按书规则命中——用户那条走 TEST_USER_RE", () => {
    // 书规则只认短词+数字/e2e-/probe-；mm_/shot_ 是会话用户名（用户清扫另一条规则）
    expect(isTestName("mm_1789016506294_d7e1fb")).toBe(false);
    expect(isTestName("shot_1789033069_ab12cd")).toBe(false);
  });

  it("真书名 → 不命中（绝不能被扫）", () => {
    for (const n of [
      "我在夜晚打吸血鬼",
      "验收-第二本-entitlement-sync",
      "佣兵传奇",
      "星海拾遗",
      "深空信标",
      "第2章", // 中文数字混排但结尾不是纯数字段 → 保守放过
    ]) {
      expect(isTestName(n), n).toBe(false);
    }
  });

  it("空值不炸", () => {
    expect(isTestName("")).toBe(false);
    expect(isTestName(null as unknown as string)).toBe(false);
  });
});
