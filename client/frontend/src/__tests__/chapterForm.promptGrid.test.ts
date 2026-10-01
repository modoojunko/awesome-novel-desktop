// c-og-slim-v2 — 章纲留存格子的纯映射测试：填值保存回读 round-trip、退役键一律不读不发、
// 存量空值不进必填缺口、字数解析与拦截、ogToForm 合并语义。
import { describe, expect, it } from "vitest";
import {
  EMPTY_OG_FORM,
  ogFormIssues,
  ogGaps,
  ogToForm,
  ogToPartial,
  type OgForm,
} from "@/components/novel/workbench/chapterForm";
import type { ChapterData } from "@/hooks/useOutline";

const FILLED: ChapterData = {
  title: "第三章",
  outline: { summary: "s", characters: ["林昭", "老方"] },
  memo: {
    payoff_plan: { must_resolve: ["玉佩来历"], must_hold: ["幕后主使"] },
    required_changes: ["与师父决裂"],
    prohibitions: ["不得提前揭玉佩"],
  },
  emotional_design: { primary_mood: "紧张" },
  micro_payoffs: [
    { kind: "clue", description: "通缉令上有旧印记" },
    { kind: "emotion", description: "妹妹的旧物" },
  ],
  ladder_exit: "他收起通缉令，转身入夜色。",
  word_target: 4000,
  challenge: "查档本身就要违规",
  plot_stage: "矛盾升级",
  plot_items: ["城门被盘查", "茶棚问路"],
} as ChapterData;

describe("ogToForm/ogToPartial round-trip（留存格子）", () => {
  it("留存字段完整回读并再次保存不丢失", () => {
    const form = ogToForm(FILLED);
    expect(form.chars).toBe("林昭\n老方");
    expect(form.mres).toBe("玉佩来历");
    expect(form.mhold).toBe("幕后主使");
    expect(form.changes).toBe("与师父决裂");
    expect(form.ban).toBe("不得提前揭玉佩");
    expect(form.payoffs).toEqual([
      { k: "clue", d: "通缉令上有旧印记" },
      { k: "emotion", d: "妹妹的旧物" },
    ]);
    expect(form.ladder).toBe("他收起通缉令，转身入夜色。");
    expect(form.wt).toBe("4000");
    expect(form.challenge).toBe("查档本身就要违规");
    expect(form.stage).toBe("矛盾升级");
    expect(form.plots).toEqual(["城门被盘查", "茶棚问路"]);

    const saved = ogToPartial(form, FILLED);
    expect(saved.outline?.summary).toBe("s");
    expect(saved.outline?.characters).toEqual(["林昭", "老方"]);
    expect(saved.memo?.payoff_plan).toEqual({
      must_resolve: ["玉佩来历"],
      must_hold: ["幕后主使"],
    });
    expect(saved.memo?.required_changes).toEqual(["与师父决裂"]);
    expect(saved.emotional_design?.primary_mood).toBe("紧张");
    expect(saved.micro_payoffs).toEqual(FILLED.micro_payoffs);
    expect(saved.ladder_exit).toBe(FILLED.ladder_exit);
    expect(saved.word_target).toBe(4000);
    expect(saved.challenge).toBe("查档本身就要违规");
    expect(saved.plot_stage).toBe("矛盾升级");
    expect(saved.plot_items).toEqual(["城门被盘查", "茶棚问路"]);
  });

  it("退役键不读回（服务端仍带这些键时表单看不到、保存也不再发）", () => {
    const legacy = {
      ...FILLED,
      outline: {
        summary: "s",
        characters: ["林昭"],
        key_points: ["上船"],
        location: "渡口",
        time: "入夜",
        narrative_pov: "第三人称",
        perspective_guidance: "贴主角",
      },
      memo: {
        reader_expectation: { strategy: "顺推", detail: "压悬念" },
        payoff_plan: { must_resolve: [], must_hold: [], partial_advance: ["身世"] },
      },
      emotional_design: {
        primary_mood: "紧张",
        mood_progression: "松→紧",
        emotional_hook: "脚步声",
        intensity_peak: "对峙",
        intensity_level: 7,
      },
      segments: [{ summary: "潜入", target_words: 800 }],
      scene_cards: [{ scene_name: "城门", weight: "high" }],
      chapter_acts: ["她翻墙进库房"],
    } as unknown as ChapterData;
    const form = ogToForm(legacy);
    expect(Object.keys(form).sort()).toEqual(Object.keys(EMPTY_OG_FORM).sort());
    expect("keys" in form).toBe(false);
    expect("segs" in form).toBe(false);
    expect("scenes" in form).toBe(false);
    expect("acts" in form).toBe(false);

    const saved = ogToPartial(form, legacy) as Record<string, unknown>;
    for (const dead of ["segments", "scene_cards", "chapter_acts"]) {
      expect(dead in saved).toBe(false);
    }
    const outline = saved.outline as Record<string, unknown>;
    for (const dead of ["key_points", "location", "time", "narrative_pov", "perspective_guidance"]) {
      // 扩展键透传例外：既有 outline 里的未知键随 ...existing 保留（后端 forward-compat），
      // 但表单自身不再覆写它们
      expect(outline[dead]).toBe(legacy.outline![dead as keyof typeof legacy.outline]);
    }
    const emotional = saved.emotional_design as Record<string, unknown>;
    // 同上：...existing 透传（表单自身只覆写 primary_mood，不再读写退役键）
    expect("mood_progression" in emotional).toBe(true);
    expect("intensity_level" in emotional).toBe(true);
  });

  it("空描述读者获得不保存；未填位置档不再发键", () => {
    const form: OgForm = {
      ...EMPTY_OG_FORM,
      payoffs: [{ k: "twist", d: " " }],
    };
    expect(ogToPartial(form).micro_payoffs).toEqual([]);
  });

  it("word_target 非法/未填 → null，不改写为 0", () => {
    expect(ogToPartial({ ...EMPTY_OG_FORM, wt: "abc" }).word_target).toBeNull();
    expect(ogToPartial({ ...EMPTY_OG_FORM, wt: "" }).word_target).toBeNull();
    expect(ogToPartial({ ...EMPTY_OG_FORM, wt: "2500" }).word_target).toBe(2500);
  });

  it("word_target 越界值兜底 clamp 到 500-6000（正常路径由 ogFormIssues 拦截）", () => {
    expect(ogToPartial({ ...EMPTY_OG_FORM, wt: "100" }).word_target).toBe(500);
    expect(ogToPartial({ ...EMPTY_OG_FORM, wt: "99999" }).word_target).toBe(6000);
  });

  it("存量非法枚举值回读兜底（读者获得 kind 回落 clue）", () => {
    const legacy = {
      ...FILLED,
      micro_payoffs: [{ kind: "unknown", description: "d", location: "结尾" }],
    } as ChapterData;
    const form = ogToForm(legacy);
    expect(form.payoffs[0].k).toBe("clue");
    expect("l" in form.payoffs[0]).toBe(false);
  });
});

describe("存量章纲空值不警告", () => {
  it("留存格子全空的存量章只报两项必填缺口", () => {
    const form = ogToForm(FILLED);
    const gaps = ogGaps(form).map((g) => g.key);
    // 必填两项（必须完成的变化/主情绪）；其余留存格子不新增缺口
    expect(gaps).toEqual([]);
    const empty = ogGaps(ogToForm({ title: "旧章", outline: {}, memo: {} } as ChapterData));
    expect(empty.map((g) => g.key)).toEqual(["changes", "mood"]);
  });

  it("退役键不进缺口清单", () => {
    const gaps = ogGaps(ogToForm(FILLED)).map((g) => g.key);
    for (const dead of ["rstrat", "rdetail", "segs", "keys", "loc", "time", "pov", "pguid", "padv", "acts", "scenes"]) {
      expect(gaps).not.toContain(dead);
    }
  });

  it("无任何留存字段的旧章 → 空数组/空串，不抛错", () => {
    const form = ogToForm({
      title: "旧章",
      outline: { summary: "s" },
      memo: {},
      segments: [],
    } as unknown as ChapterData);
    expect(form.payoffs).toEqual([]);
    expect(form.plots).toEqual([]);
    expect(form.ladder).toBe("");
    expect(form.wt).toBe("");
    expect(form.challenge).toBe("");
  });
});

describe("ogFormIssues（保存前拦截校验）", () => {
  it("目标字数越界/非数字 → 报告；空串与区间内不报", () => {
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "100" })).toEqual([
      "本章目标字数需在 500-6000 之间（留空默认 2500）",
    ]);
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "6001" }).length).toBe(1);
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "abc" }).length).toBe(1);
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "" })).toEqual([]);
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "6000" })).toEqual([]);
  });

  it("退役字段不再产生保存拦截（场景名门槛随场景卡退役）", () => {
    // 留存格子填满 + 空字数 → 无问题
    expect(
      ogFormIssues({
        ...EMPTY_OG_FORM,
        summary: "s",
        changes: "c",
        mood: "紧张",
        challenge: "墙",
      }),
    ).toEqual([]);
  });
});

describe("ogToForm 合并语义（服务端数据为底、后到键覆盖）", () => {
  it("覆盖留存格子，服务端非章纲字段保留、title 不被覆盖键改写", () => {
    const server = {
      ...FILLED,
      title: "第三章（作者定名）",
      word_target: 3000,
    } as ChapterData;
    const patch = {
      outline: { summary: "夜探账房", characters: ["林昭"] },
      memo: { required_changes: ["拿到账册"] },
      emotional_design: { primary_mood: "紧绷" },
      micro_payoffs: [{ kind: "reveal", description: "账册是假的" }],
      challenge: "库房有人守",
      plot_stage: "重要转折",
      word_target: 4000,
    };
    const form = ogToForm({ ...server, ...patch } as ChapterData);
    expect(form.title).toBe("第三章（作者定名）"); // title 保留服务端值
    expect(form.summary).toBe("夜探账房");
    expect(form.changes).toBe("拿到账册");
    expect(form.mood).toBe("紧绷");
    expect(form.payoffs).toEqual([{ k: "reveal", d: "账册是假的" }]);
    expect(form.wt).toBe("4000");
    // 展开语义：覆盖键缺的格子保留服务端值（AI 产物回填的既有口径，fill-gaps 同族）
    expect(form.ladder).toBe("他收起通缉令，转身入夜色。");
    expect(form.plots).toEqual(["城门被盘查", "茶棚问路"]); // AI 产物不动剧情
  });
});
