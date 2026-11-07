// 知识库载荷字段中文标签（c-kb-field-labels）：通用字典/概念消歧/枚举值/回退原键。
import { describe, expect, it } from "vitest";

import { kbFieldDesc, kbFieldLabel, kbValueLabel } from "@/lib/kbFieldLabels";

describe("kbFieldLabel", () => {
  it("角色档案/认知格复用角色域同源标签", () => {
    expect(kbFieldLabel("角色设定", "gender")).toBe("性别");
    expect(kbFieldLabel("角色设定", "look")).toBe("外貌标签");
    expect(kbFieldLabel("角色设定", "w5")).toBe("核心认知盲区");
    expect(kbFieldLabel("角色设定", "archetype")).toBe("名字");
    expect(kbFieldLabel("角色设定", "plot")).toBe("剧情定位");
  });

  it("同键按概念消歧（role：角色＝定位、文风＝声音角色）", () => {
    expect(kbFieldLabel("角色设定", "role")).toBe("定位");
    expect(kbFieldLabel("文风", "role")).toBe("声音角色");
  });

  it("跨概念通用键（世界/手法/文笔）", () => {
    expect(kbFieldLabel("世界设定", "part")).toBe("分区");
    expect(kbFieldLabel("手法", "instruction")).toBe("打法");
    expect(kbFieldLabel("文笔", "banned")).toBe("禁用词");
  });

  it("未知键回退原键（不编造）", () => {
    expect(kbFieldLabel("手法", "unknown_key")).toBe("unknown_key");
    expect(kbFieldLabel("未知概念", "gender")).toBe("性别"); // 概念不在消歧表仍走通用表
  });
});

describe("kbValueLabel", () => {
  it("布尔转是/否", () => {
    expect(kbValueLabel("hard", true)).toBe("是");
    expect(kbValueLabel("hard", false)).toBe("否");
  });

  it("枚举值转中文（世界分区/槽位/口癖严重度）", () => {
    expect(kbValueLabel("part", "stage")).toBe("世界舞台");
    expect(kbValueLabel("part", "constraint")).toBe("世界铁律");
    expect(kbValueLabel("slot", "banned_word")).toBe("禁用词");
    expect(kbValueLabel("tic_severity", "medium")).toBe("中");
  });

  it("未知枚举值与未收录字段回退原值", () => {
    expect(kbValueLabel("part", "unknown_part")).toBe("unknown_part");
    expect(kbValueLabel("gender", "女")).toBe("女");
    expect(kbValueLabel("age", 44)).toBe("44");
  });
});


describe("跨维度通用键与字段说明（2026-11-07 定稿：固定骨架＋开放内容）", () => {
  it("拆书产物键给中文标签；未知键回退原键", () => {
    expect(kbFieldLabel("手法", "need")).toBe("读者需求");
    expect(kbFieldLabel("文风", "how")).toBe("怎么写");
    expect(kbFieldLabel("角色设定", "evidence_ch")).toBe("章证据");
    expect(kbFieldLabel("手法", "repro_steps")).toBe("复现步骤");
    expect(kbFieldLabel("手法", "外星键")).toBe("外星键");
  });

  it("confidence 枚举转中文", () => {
    expect(kbValueLabel("confidence", "high")).toBe("高");
    expect(kbValueLabel("confidence", "mid")).toBe("中");
    expect(kbValueLabel("confidence", "low")).toBe("低");
  });

  it("kbFieldDesc：收录键给作家语言说明；未收录返空串", () => {
    expect(kbFieldDesc("how")).toContain("写");
    expect(kbFieldDesc("evidence_ch")).toContain("章");
    expect(kbFieldDesc("不存在键")).toBe("");
  });
});
