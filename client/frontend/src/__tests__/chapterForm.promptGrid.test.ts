// ai-prompt-crafting 6.1 — 章纲新格子（场景卡 weight/focus、读者获得、
// 章末落点、目标字数）的纯映射测试：填值保存回读 round-trip、存量空值
// 不进必填缺口、枚举非法值兜底、空行过滤与字数解析。
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
  outline: { summary: "s", characters: ["林昭"] },
  memo: {},
  emotional_design: { primary_mood: "紧张" },
  segments: [{ summary: "a", target_words: 800 }],
  scene_cards: [
    {
      scene_name: "城门",
      goal: "入城",
      obstacle: "盘查",
      hook: "通缉令",
      weight: "high",
      focus: "核心冲突",
    },
    { scene_name: "茶棚", goal: "问路", obstacle: "", hook: "", weight: "low" },
  ],
  micro_payoffs: [
    { kind: "clue", description: "通缉令上有旧印记", location: "前段" },
    { kind: "emotion", description: "妹妹的旧物" },
  ],
  ladder_exit: "他收起通缉令，转身入夜色。",
  word_target: 4000,
} as ChapterData;

describe("ogToForm/ogToPartial round-trip（章纲新格子）", () => {
  it("新格子字段完整回读并再次保存不丢失", () => {
    const form = ogToForm(FILLED);
    expect(form.scenes).toEqual([
      { n: "城门", g: "入城", o: "盘查", h: "通缉令", w: "high", f: "核心冲突" },
      { n: "茶棚", g: "问路", o: "", h: "", w: "low", f: "" },
    ]);
    expect(form.payoffs).toEqual([
      { k: "clue", d: "通缉令上有旧印记", l: "前段" },
      { k: "emotion", d: "妹妹的旧物", l: "" },
    ]);
    expect(form.ladder).toBe("他收起通缉令，转身入夜色。");
    expect(form.wt).toBe("4000");

    const saved = ogToPartial(form, FILLED);
    expect(saved.scene_cards).toEqual(FILLED.scene_cards);
    expect(saved.micro_payoffs).toEqual(FILLED.micro_payoffs);
    expect(saved.ladder_exit).toBe(FILLED.ladder_exit);
    expect(saved.word_target).toBe(4000);
  });

  it("场景名空行不保存；未选的 weight/focus/location 省略键", () => {
    const form: OgForm = {
      ...EMPTY_OG_FORM,
      scenes: [
        { n: "  ", g: "x", o: "", h: "", w: "", f: "" }, // 空场景名 → 过滤
        { n: "渡口", g: "", o: "", h: "", w: "", f: "" }, // 无枚举 → 键省略
      ],
      payoffs: [{ k: "twist", d: " ", l: "" }], // 空描述 → 过滤
    };
    const saved = ogToPartial(form);
    expect(saved.scene_cards).toEqual([{ scene_name: "渡口", goal: "", obstacle: "", hook: "" }]);
    expect(saved.micro_payoffs).toEqual([]);
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

  it("存量非法枚举值回读兜底（weight/focus 清空，kind 回落 clue）", () => {
    const legacy = {
      ...FILLED,
      scene_cards: [{ scene_name: "x", weight: "超高", focus: "不知道" }],
      micro_payoffs: [{ kind: "unknown", description: "d", location: "结尾" }],
    } as ChapterData;
    const form = ogToForm(legacy);
    expect(form.scenes[0].w).toBe("");
    expect(form.scenes[0].f).toBe("");
    expect(form.payoffs[0].k).toBe("clue");
    expect(form.payoffs[0].l).toBe("");
  });
});

describe("存量章纲空值不警告", () => {
  it("新格子全空的存量章不进必填缺口（c-og-fields-slim 后口径四项）", () => {
    const form = ogToForm(FILLED);
    const gaps = ogGaps(form).map((g) => g.key);
    // 四项必填（预期策略/必须完成的变化/主情绪/段落规划）；新格子不新增缺口
    expect(gaps).toEqual(["rstrat", "changes"]);
    expect(gaps).not.toContain("scenes");
    expect(gaps).not.toContain("payoffs");
    expect(gaps).not.toContain("ladder");
    expect(gaps).not.toContain("wt");
  });

  it("无任何新格子字段的旧章 → 空数组/空串，不抛错", () => {
    const form = ogToForm({
      title: "旧章",
      outline: { summary: "s" },
      memo: {},
      segments: [],
    } as unknown as ChapterData);
    expect(form.scenes).toEqual([]);
    expect(form.payoffs).toEqual([]);
    expect(form.ladder).toBe("");
    expect(form.wt).toBe("");
  });
});

describe("ogFormIssues（保存前拦截校验）", () => {
  it("场景行有内容但缺场景名 → 报告行号", () => {
    const issues = ogFormIssues({
      ...EMPTY_OG_FORM,
      scenes: [
        { n: "城门", g: "入城", o: "", h: "", w: "", f: "" },
        { n: "", g: "逃亡", o: "追兵", h: "", w: "high", f: "" },
      ],
    });
    expect(issues).toEqual(["场景卡第 2 行填写了内容但缺少场景名"]);
  });

  it("整行空白（无名称也无内容）不报；仅填场景名不报", () => {
    expect(
      ogFormIssues({
        ...EMPTY_OG_FORM,
        scenes: [
          { n: "", g: "", o: "", h: "", w: "", f: "" },
          { n: "渡口", g: "", o: "", h: "", w: "", f: "" },
        ],
      }),
    ).toEqual([]);
  });

  it("目标字数越界/非数字 → 报告；空串与区间内不报", () => {
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "100" })).toEqual([
      "本章目标字数需在 500-6000 之间（留空默认 2500）",
    ]);
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "6001" }).length).toBe(1);
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "abc" }).length).toBe(1);
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "" })).toEqual([]);
    expect(ogFormIssues({ ...EMPTY_OG_FORM, wt: "6000" })).toEqual([]);
  });
});

describe("AI 起草回填映射（outline-ai-draft）", () => {
  it("草稿覆盖章纲格子，服务端非章纲字段保留、title 不被草稿改写", () => {
    const server = {
      ...FILLED,
      title: "第三章（作者定名）",
      scene_cards: [{ scene_name: "旧场景" }],
      word_target: 3000,
    } as ChapterData;
    const draft = {
      outline: { summary: "夜探账房" },
      memo: {},
      segments: [{ summary: "潜入", target_words: 800 }],
      scene_cards: [
        { scene_name: "账房", goal: "取证", obstacle: "守夜", hook: "暗格" },
      ],
      word_target: 4000,
    };
    const form = ogToForm({ ...server, ...draft } as ChapterData);
    expect(form.title).toBe("第三章（作者定名）"); // title 保留服务端值
    expect(form.summary).toBe("夜探账房");
    expect(form.scenes).toEqual([
      { n: "账房", g: "取证", o: "守夜", h: "暗格", w: "", f: "" },
    ]); // 草稿场景卡覆盖服务端旧卡
    expect(form.wt).toBe("4000");
    // 展开语义：草稿缺的键保留服务端值；真实后端草稿恒为全字段形状（sanitize 兜底）
    expect(form.ladder).toBe("他收起通缉令，转身入夜色。");
  });
});
