import { describe, expect, it } from "vitest";

import { matchRegistration, registrationsForTest, threadKeyOf, validateRegistrations, type ChatPageRegistration } from "@/lib/chatRegistry";

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
      "simulate_plot",
      "draw_plot_cards",
      "review_cast",
      "fill_gaps",
      "conflict_check",
      "renwei",
      "seam",
      "zhuque",
      "settings_og_fill",
    ];
    const TABS = ["og", "prose", "settings", "relations", "hooks", "actions", "style"];
    for (const key of registrationsForTest().flatMap((r) =>
      TABS.flatMap((chapterTab) =>
        r.chips({
          view: "workbench",
          chapterRef: "vol-1-ch-1",
          volumeSelId: null,
          emptyBook: false,
          chapterTab,
        }).map((c) => c.key),
      ),
    )) {
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


describe("chatRegistry 补面（c-agent-decision-archive 覆盖债）", () => {
  const base = { chapterRef: null, volumeSelId: null, emptyBook: false };

  it("settings.chars：开场白＋起草/体检 chips", () => {
    const scope = { view: "advanced-settings" as const, ...base, settingPanel: "chars" };
    const reg = matchRegistration(scope)!;
    expect(reg.id).toBe("settings.chars");
    expect(reg.greeting(scope)).toContain("主角最终变成什么样");
    const keys = reg.chips(scope).map((c) => c.key);
    expect(keys).toContain("draft_arc");
    expect(keys).toContain("check_consistency");
  });

  it("archives.preview：预览页查知识库 chips；threadKeyOf=preview", () => {
    const scope = { view: "archives" as const, ...base };
    const reg = matchRegistration(scope)!;
    expect(reg.id).toBe("archives.preview");
    expect(reg.greeting(scope)).toBeNull();
    expect(reg.chips(scope).map((c) => c.key)).toContain("kb_search");
    expect(threadKeyOf(scope)).toBe("preview");
  });

  it("settings.default：按面板换装 chips（genre/其他面板）", () => {
    const scope = { view: "advanced-settings" as const, ...base, settingPanel: "genre" };
    const reg = matchRegistration(scope)!;
    const genreKeys = reg.chips(scope).map((c) => c.key);
    expect(genreKeys.length).toBeGreaterThan(0);
    const other = { view: "advanced-settings" as const, ...base, settingPanel: undefined };
    expect(reg.chips(other).length).toBeGreaterThan(0);
  });

  it("threadKeyOf 全视图映射（页签一线程口径）", () => {
    expect(threadKeyOf({ view: "workbench", chapterRef: "vol-1-ch-7", volumeSelId: null, emptyBook: false, chapterTab: "prose" })).toBe("ch:prose");
    expect(threadKeyOf({ view: "workbench", chapterRef: "vol-1-ch-7", volumeSelId: null, emptyBook: false })).toBe("ch:og");
    expect(threadKeyOf({ view: "workbench", chapterRef: null, volumeSelId: "v1", emptyBook: false })).toBe("vol");
    expect(threadKeyOf({ view: "advanced-settings", ...base, settingPanel: "chars" })).toBe("set:chars");
    expect(threadKeyOf({ view: "advanced-settings", ...base })).toBe("set:default");
    expect(threadKeyOf({ view: "archives", ...base })).toBe("preview");
    expect(threadKeyOf({ view: "unknown-view" as never, ...base })).toBe("v:unknown-view");
  });
});


describe("chatRegistry 兜底分支（同上补面）", () => {
  it("workbench.chapter 与 settings.default 的 greeting＝安静（null）", () => {
    const ch = { view: "workbench" as const, chapterRef: "vol-1-ch-1", volumeSelId: null, emptyBook: false, chapterTab: "og" };
    expect(matchRegistration(ch)!.greeting(ch)).toBeNull();
    const st = { view: "advanced-settings" as const, chapterRef: null, volumeSelId: null, emptyBook: false };
    expect(matchRegistration(st)!.greeting(st)).toBeNull();
  });

  it("无匹配视图 → matchRegistration 返回 null（宿主回落旧面板）", () => {
    expect(matchRegistration({ view: "unknown-view" as never, chapterRef: null, volumeSelId: null, emptyBook: false })).toBeNull();
  });

  it("validateRegistrations 负例：白名单外能力 fail loud（可注入注册表）", () => {
    const bad = [
      {
        id: "bad.page",
        label: "坏页面",
        match: () => true,
        greeting: () => null,
        chips: () => [{ key: "not_in_whitelist", label: "x", command: "" }],
      } as unknown as ChatPageRegistration,
    ];
    expect(() => validateRegistrations(bad)).toThrow(/未登记的能力/);
  });
});
