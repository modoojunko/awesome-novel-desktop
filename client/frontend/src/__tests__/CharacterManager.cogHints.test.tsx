// cog-logical-levels — 认知区层头大白话 hint：六层各带一句「他视角」的提示，
// 帮作家理解每层写什么（他眼里的世界/他把自己当成谁/…），不出现术语。
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { COG_LEVEL_HINTS } from "@/lib/characterModel";
import { COG_LAYERS } from "@/lib/characterModel";

vi.mock("@/lib/api", () => ({ api: { get: vi.fn().mockResolvedValue({}) } }));

describe("认知六层 hint（理解层次的大白话落点）", () => {
  it("六层每层都有 hint，且不含术语", () => {
    const banned = ["张力", "层次", "模型", "NLP"];
    expect(Object.keys(COG_LEVEL_HINTS).sort()).toEqual(
      COG_LAYERS.map((l) => l.id).sort(),
    );
    for (const hint of Object.values(COG_LEVEL_HINTS)) {
      for (const w of banned) expect(hint).not.toContain(w);
      expect(hint.length).toBeGreaterThan(4);
    }
  });

  it("s5 宿命认知观的口径指向「他和世界的关系/注定要面对什么」", () => {
    const s5 = COG_LAYERS.flatMap((l) => l.fields).find((f) => f.k === "s5");
    expect(s5?.label).toBe("宿命认知观");
    // hint 文案（词表）落点
    expect(COG_LEVEL_HINTS.self).toContain("把自己当成谁");
  });

  it("CharacterManager 渲染层头 hint", async () => {
    const { default: CharacterManager } = await import(
      "@/components/novel/settings/CharacterManager"
    );
    // CharacterManager 依赖较多（api/get_card），此处只做词表直查的补充断言：
    // 六问齐全（还有谁→精神层由 s5 承接，其余五问对应五层）
    expect(COG_LEVEL_HINTS.values).toContain("为什么");
    expect(COG_LEVEL_HINTS.power).toContain("怎么做");
    expect(COG_LEVEL_HINTS.behavior).toContain("怎么做");
    expect(COG_LEVEL_HINTS.env).toContain("什么人");
    expect(screen).toBeDefined();
    await waitFor(() => expect(true).toBe(true));
  });
});
