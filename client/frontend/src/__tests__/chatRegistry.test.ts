import { describe, expect, it } from "vitest";

import { matchRegistration, registrationsForTest, validateRegistrations } from "@/lib/chatRegistry";

describe("chatRegistry 每页注册制", () => {
  it("工作台卷页命中 workbench.volume（卷页与书主页共用）", () => {
    expect(matchRegistration({ view: "workbench", chapterRef: null, volumeSelId: null, emptyBook: true })?.id).toBe(
      "workbench.volume",
    );
    expect(matchRegistration({ view: "workbench", chapterRef: null, volumeSelId: "v1", emptyBook: false })?.id).toBe(
      "workbench.volume",
    );
  });

  it("章级模式命中章级注册（批F-2 收编落地）", () => {
    expect(
      matchRegistration({ view: "workbench", chapterRef: "vol-1-ch-1", volumeSelId: null, emptyBook: false })?.id,
    ).toBe("workbench.chapter");
  });

  it("设定·角色面板命中专属注册", () => {
    expect(
      matchRegistration({ view: "advanced-settings", chapterRef: null, volumeSelId: null, emptyBook: false, settingPanel: "chars" })
        ?.id,
    ).toBe("settings.chars");
    expect(
      matchRegistration({ view: "advanced-settings", chapterRef: null, volumeSelId: null, emptyBook: false, settingPanel: "genre" })
        ?.id,
    ).toBe("settings.default");
  });

  it("fail loud：注册了白名单外的能力即抛错", () => {
    // 现有注册全在白名单内——校验通过即绿；白名单外 key 会在 validate 抛错
    expect(() => validateRegistrations()).not.toThrow();
    // 跨页复用同一 chip 是设计内（draft_arc 多页共通）——只校验白名单覆盖
    const whitelist = [
      "draft_volume_expand",
      "draft_chapter_split",
      "draft_chapter_plot",
      "draft_arc",
      "check_consistency",
      "draft_names",
      "diverge_character_group",
      "diverge_plot_branches",
      "ai_write",
      "kb_search",
      "plot_draw",
      "cast_review",
      "simulate",
      "fill_gaps",
      "conflict_check",
      "renwei",
      "seam",
      "zhuque",
    ];
    for (const key of registrationsForTest().flatMap((r) => r.chips().map((c) => c.key))) {
      expect(whitelist).toContain(key);
    }
  });

  it("开场白状态感知：空书与有书不同口吻", () => {
    const reg = matchRegistration({ view: "workbench", chapterRef: null, volumeSelId: null, emptyBook: true })!;
    const emptyGreeting = reg.greeting({ view: "workbench", chapterRef: null, volumeSelId: null, emptyBook: true });
    const fullGreeting = reg.greeting({ view: "workbench", chapterRef: null, volumeSelId: "v1", emptyBook: false });
    expect(emptyGreeting).toContain("第一卷");
    expect(fullGreeting).not.toBe(emptyGreeting);
  });
});
