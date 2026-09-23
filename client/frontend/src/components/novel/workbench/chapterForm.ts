// 章纲表单模型（OgPane / ChapterWorkspace 共用）：
// 扁平 OgForm ↔ 后端 ChapterData 的纯映射 + 必填缺口计算。
// 必填口径 = 后端 gate_chapter_ready 六项（与 book.html REQUIRED 一致）。
// ai-prompt-crafting：新增提示词格子（场景卡 weight/focus、读者获得、章末落点、
// 目标字数）——全部可空，不进必填缺口。
import type { ChapterData } from "@/hooks/useOutline";

export interface OgSeg {
  s: string;
  w: number;
}

export interface OgScene {
  n: string; // scene_name 场景名
  g: string; // goal 目标
  o: string; // obstacle 阻碍
  h: string; // hook 钩子
  w: "" | "high" | "mid" | "low"; // 权重（高/中/低）
  f: "" | "核心冲突" | "人物情绪" | "信息差"; // 焦点
}

export interface OgPayoff {
  k: string; // kind 类型枚举（PAYOFF_KINDS 的 key）
  d: string; // description 一句话描述
  l: "" | "前段" | "中段" | "后段"; // location
}

export const SCENE_WEIGHTS = [
  { value: "high", label: "高" },
  { value: "mid", label: "中" },
  { value: "low", label: "低" },
] as const;

export const SCENE_FOCUS = ["核心冲突", "人物情绪", "信息差"] as const;

export const PAYOFF_KINDS = [
  { value: "clue", label: "线索" },
  { value: "reveal", label: "真相揭示" },
  { value: "twist", label: "反转" },
  { value: "emotion", label: "情绪共鸣" },
  { value: "power", label: "实力成长" },
  { value: "relation", label: "关系进展" },
  { value: "relief", label: "压力释放" },
] as const;

export const PAYOFF_LOCATIONS = ["前段", "中段", "后段"] as const;

export interface OgForm {
  title: string;
  summary: string;
  keys: string; // 一行一个 → outline.key_points[]
  chars: string; // 一行一个 → outline.characters[]
  loc: string;
  time: string;
  pov: string;
  pguid: string;
  task: string; // * → memo.current_task
  rstate: string; // * → memo.reader_expectation.state
  rstrat: string; // * → memo.reader_expectation.strategy
  rdetail: string; // → memo.reader_expectation.detail
  mres: string; // 一行一个 → memo.payoff_plan.must_resolve[]
  mhold: string; // 一行一个 → memo.payoff_plan.must_hold[]
  padv: string; // 一行一个 → memo.payoff_plan.partial_advance[]
  changes: string; // * 一行一个 → memo.required_changes[]
  ban: string; // 一行一个 → memo.prohibitions[]
  mood: string; // * → emotional_design.primary_mood
  segs: OgSeg[]; // * → segments[{summary,target_words}]
  // ── 提示词格子（ai-prompt-crafting，全可空）──
  scenes: OgScene[]; // → scene_cards[]
  payoffs: OgPayoff[]; // → micro_payoffs[]
  ladder: string; // → ladder_exit 章末落点
  wt: string; // → word_target 本章目标字数（500-6000）
  // ── 拆章五段（c-chapter-plan-ai；非必填，但**必须整表回传**——缺键即清空）──
  challenge: string; // → challenge 碰到的挑战
  acts: string; // → chapter_acts 本章行动（一行一条 ≤4×60）
  stage: string; // → plot_stage 阶段（六档闭集）
}

export const REQ_FIELDS: { key: keyof OgForm; label: string }[] = [
  { key: "task", label: "核心任务" },
  { key: "rstate", label: "读者当前状态" },
  { key: "rstrat", label: "预期策略" },
  { key: "changes", label: "必须完成的变化" },
  { key: "mood", label: "主情绪" },
  { key: "segs", label: "段落规划" },
];

export const EMPTY_OG_FORM: OgForm = {
  challenge: "",
  acts: "",
  stage: "开局铺垫",
  title: "",
  summary: "",
  keys: "",
  chars: "",
  loc: "",
  time: "",
  pov: "",
  pguid: "",
  task: "",
  rstate: "",
  rstrat: "",
  rdetail: "",
  mres: "",
  mhold: "",
  padv: "",
  changes: "",
  ban: "",
  mood: "",
  segs: [{ s: "", w: 800 }],
  scenes: [],
  payoffs: [],
  ladder: "",
  wt: "",
};

/** 章纲缺口标签键 → fill-gaps 白名单键（与后端 chapters/ai_draft.py _FILLABLE_KEYS 同口径）。 */
export const GAP_TO_FILL_KEY: Record<string, string> = {
  task: "current_task",
  rstate: "state",
  rstrat: "strategy",
  changes: "changes",
  mood: "mood",
  segs: "segments",
};

/** 后端 fills（白名单键）→ OgForm 补丁：未识别的键丢弃；行列表按行拼接。
 *  产物只回填表单，落库仍走既有保存链（3s 自动保存/手动保存）。 */
export function ogPatchFromFills(fills: Record<string, unknown>): Partial<OgForm> {
  const patch: Partial<OgForm> = {};
  for (const [k, v] of Object.entries(fills)) {
    if (k === "segments") {
      if (!Array.isArray(v)) continue;
      const segs: OgSeg[] = [];
      for (const it of v) {
        if (!it || typeof it !== "object") continue;
        const o = it as { summary?: unknown; target_words?: unknown };
        const text = String(o.summary ?? "").trim();
        if (!text) continue;
        const w = Number(o.target_words);
        segs.push({ s: text, w: Number.isFinite(w) && w > 0 ? w : 800 });
      }
      if (segs.length) patch.segs = segs;
      continue;
    }
    if (typeof v === "string") {
      const text = v.trim();
      if (!text) continue;
      switch (k) {
        case "summary": patch.summary = text; break;
        case "location": patch.loc = text; break;
        case "time": patch.time = text; break;
        case "current_task": patch.task = text; break;
        case "state": patch.rstate = text; break;
        case "strategy": patch.rstrat = text; break;
        case "detail": patch.rdetail = text; break;
        case "mood": patch.mood = text; break;
        default: break;
      }
      continue;
    }
    if (Array.isArray(v)) {
      const joined = v
        .map((x) => String(x).trim())
        .filter(Boolean)
        .join("\n");
      if (!joined) continue;
      switch (k) {
        case "key_points": patch.keys = joined; break;
        case "characters": patch.chars = joined; break;
        case "changes": patch.changes = joined; break;
        case "prohibitions": patch.ban = joined; break;
        default: break;
      }
    }
  }
  return patch;
}

const lines = (s: string): string[] =>
  s.split("\n").map((x) => x.trim()).filter(Boolean);

const SCENE_WEIGHT_SET = new Set<string>(SCENE_WEIGHTS.map((x) => x.value));
const SCENE_FOCUS_SET = new Set<string>(SCENE_FOCUS);
const PAYOFF_KIND_SET = new Set<string>(PAYOFF_KINDS.map((x) => x.value));
const PAYOFF_LOC_SET = new Set<string>(PAYOFF_LOCATIONS);

export function ogGaps(form: OgForm): { key: string; label: string }[] {
  const gaps: { key: string; label: string }[] = [];
  for (const { key, label } of REQ_FIELDS) {
    const v = form[key];
    const empty =
      key === "segs"
        ? (v as OgSeg[]).length === 0
        : String(v ?? "").trim() === "";
    if (empty) gaps.push({ key: String(key), label });
  }
  return gaps;
}

export function ogToForm(d: ChapterData | null | undefined): OgForm {
  const o = d?.outline ?? {};
  const m = d?.memo ?? {};
  const re = m.reader_expectation ?? {};
  const pp = m.payoff_plan ?? {};
  return {
    title: d?.title ?? "",
    summary: o.summary ?? "",
    keys: (o.key_points ?? []).join("\n"),
    chars: (o.characters ?? []).join("\n"),
    loc: o.location ?? "",
    time: o.time ?? "",
    pov: o.narrative_pov ?? "",
    pguid: o.perspective_guidance ?? "",
    task: m.current_task ?? "",
    rstate: re.state ?? "",
    rstrat: re.strategy ?? "",
    rdetail: re.detail ?? "",
    mres: (pp.must_resolve ?? []).join("\n"),
    mhold: (pp.must_hold ?? []).join("\n"),
    padv: (pp.partial_advance ?? []).join("\n"),
    changes: (m.required_changes ?? []).join("\n"),
    ban: (m.prohibitions ?? []).join("\n"),
    mood: d?.emotional_design?.primary_mood ?? "",
    segs: (d?.segments ?? []).map((s) => ({
      s: s.summary ?? "",
      w: s.target_words ?? 800,
    })),
    scenes: (d?.scene_cards ?? []).map((sc) => ({
      n: sc.scene_name ?? "",
      g: sc.goal ?? "",
      o: sc.obstacle ?? "",
      h: sc.hook ?? "",
      w: SCENE_WEIGHT_SET.has(sc.weight as OgScene["w"]) ? (sc.weight as OgScene["w"]) : "",
      f: SCENE_FOCUS_SET.has(sc.focus ?? "") ? (sc.focus as OgScene["f"]) : "",
    })),
    payoffs: (d?.micro_payoffs ?? []).map((mp) => ({
      k: PAYOFF_KIND_SET.has(mp.kind ?? "") ? (mp.kind as string) : "clue",
      d: mp.description ?? "",
      l: PAYOFF_LOC_SET.has(mp.location ?? "") ? (mp.location as OgPayoff["l"]) : "",
    })),
    ladder: d?.ladder_exit ?? "",
    challenge: d?.challenge ?? "",
    acts: (d?.chapter_acts ?? []).join("\n"),
    stage: d?.plot_stage ?? "",
    wt: d?.word_target != null ? String(d.word_target) : "",
  };
}

/** 场景名门槛 + 字数区间校验：返回用户可读问题列表，非空则保存被拦截。
 *  只拦「行内有内容但缺场景名」——整行空白仍允许（可空格子）。 */
export function ogFormIssues(form: OgForm): string[] {
  const issues: string[] = [];
  form.scenes.forEach((sc, i) => {
    const hasContent = [sc.g, sc.o, sc.h, sc.w, sc.f].some((v) => String(v ?? "").trim() !== "");
    if (!sc.n.trim() && hasContent) {
      issues.push(`场景卡第 ${i + 1} 行填写了内容但缺少场景名`);
    }
  });
  if (form.wt.trim() !== "") {
    const wt = parseInt(form.wt, 10);
    if (!Number.isFinite(wt) || wt < 500 || wt > 6000) {
      issues.push("本章目标字数需在 500-6000 之间（留空默认 2500）");
    }
  }
  return issues;
}

/** 保留 existing 中未知扩展键（后端 forward-compat），只覆写表单覆盖的字段 */
export function ogToPartial(
  form: OgForm,
  existing?: ChapterData | null,
): Partial<ChapterData> {
  const wt = parseInt(form.wt, 10);
  return {
    title: form.title,
    outline: {
      ...(existing?.outline ?? {}),
      summary: form.summary,
      key_points: lines(form.keys),
      characters: lines(form.chars),
      location: form.loc,
      time: form.time,
      narrative_pov: form.pov,
      perspective_guidance: form.pguid,
    },
    memo: {
      ...(existing?.memo ?? {}),
      current_task: form.task,
      reader_expectation: {
        ...(existing?.memo?.reader_expectation ?? {}),
        state: form.rstate,
        strategy: form.rstrat,
        detail: form.rdetail,
      },
      payoff_plan: {
        ...(existing?.memo?.payoff_plan ?? {}),
        must_resolve: lines(form.mres),
        must_hold: lines(form.mhold),
        partial_advance: lines(form.padv),
      },
      required_changes: lines(form.changes),
      prohibitions: lines(form.ban),
    },
    emotional_design: {
      ...(existing?.emotional_design ?? {}),
      primary_mood: form.mood,
    },
    segments: form.segs.map((s) => ({ summary: s.s, target_words: s.w })),
    // 提示词格子：场景卡只存非空场景名行（后端对空行 description 过滤同理）
    scene_cards: form.scenes
      .filter((sc) => sc.n.trim())
      .map((sc) => ({
        scene_name: sc.n.trim(),
        goal: sc.g.trim(),
        obstacle: sc.o.trim(),
        hook: sc.h.trim(),
        ...(sc.w ? { weight: sc.w } : {}),
        ...(sc.f ? { focus: sc.f } : {}),
      })),
    micro_payoffs: form.payoffs
      .filter((mp) => mp.d.trim())
      .map((mp) => ({
        kind: mp.k,
        description: mp.d.trim(),
        ...(mp.l ? { location: mp.l } : {}),
      })),
    ladder_exit: form.ladder.trim(),
    // 拆章三格：整表回传（缺键会被装配端写空——见 chapter-data 场景）
    challenge: form.challenge.trim(),
    chapter_acts: form.acts.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 4),
    plot_stage: form.stage.trim(),
    // 兜底 clamp（正常路径已被 ogFormIssues 拦截，此处防绕过）
    word_target: Number.isFinite(wt) && wt > 0 ? Math.min(6000, Math.max(500, wt)) : null,
  };
}
