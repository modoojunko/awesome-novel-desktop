// 章纲表单模型（OgPane / ChapterWorkspace 共用）：
// 扁平 OgForm ↔ 后端 ChapterData 的纯映射 + 必填缺口计算。
// 必填口径 = 后端 gate_chapter_ready 两项（必须完成的变化、主情绪）。
// c-og-slim-v2：字段收敛到 13 格——关键事件/地点/时间/叙事视角/视角指导/预期策略/
// 预期细节/可部分推进/段落规划/本章行动/场景卡整组退役（控件、映射、校验同批摘除）。
import type { ChapterData } from "@/hooks/useOutline";

export interface OgPayoff {
  k: string; // kind 类型枚举（PAYOFF_KINDS 的 key）
  d: string; // description 一句话描述
}

export const PAYOFF_KINDS = [
  { value: "clue", label: "线索" },
  { value: "reveal", label: "真相揭示" },
  { value: "twist", label: "反转" },
  { value: "emotion", label: "情绪共鸣" },
  { value: "power", label: "实力成长" },
  { value: "relation", label: "关系进展" },
  { value: "relief", label: "压力释放" },
] as const;

// ── 章内剧情（c-plot-split：条目=场景描述非正文）──
export const PLOT_MAX_LEN = 200;
export const PLOT_MAX_ITEMS = 12;

export interface OgForm {
  title: string;
  summary: string;
  chars: string; // 一行一个 → outline.characters[]
  mres: string; // 一行一个 → memo.payoff_plan.must_resolve[]
  mhold: string; // 一行一个 → memo.payoff_plan.must_hold[]
  changes: string; // * 一行一个 → memo.required_changes[]
  ban: string; // 一行一个 → memo.prohibitions[]
  mood: string; // * → emotional_design.primary_mood
  payoffs: OgPayoff[]; // → micro_payoffs[]
  ladder: string; // → ladder_exit 章末落点
  wt: string; // → word_target 本章目标字数（500-6000）
  // ── 章内剧情（c-plot-split；**必须整表回传**——缺键保持原样，显式 [] 清空）──
  plots: string[]; // → plot_items[]（一条=一段场景描述，≤200 字、≤12 条）
  // ── 拆章两格（c-chapter-plan-ai；非必填，但**必须整表回传**——缺键即清空）──
  challenge: string; // → challenge 碰到的挑战
  stage: string; // → plot_stage 阶段（六档闭集）
}

export const REQ_FIELDS: { key: keyof OgForm; label: string }[] = [
  { key: "changes", label: "必须完成的变化" },
  { key: "mood", label: "主情绪" },
];

export const EMPTY_OG_FORM: OgForm = {
  challenge: "",
  stage: "开局铺垫",
  title: "",
  summary: "",
  chars: "",
  mres: "",
  mhold: "",
  changes: "",
  ban: "",
  mood: "",
  payoffs: [],
  ladder: "",
  wt: "",
  plots: [],
};

/** 章纲缺口标签键 → fill-gaps 白名单键（与后端 chapters/ai_draft.py _FILLABLE_KEYS 同口径）。 */
export const GAP_TO_FILL_KEY: Record<string, string> = {
  changes: "changes",
  mood: "mood",
};

/** 后端 fills（白名单键）→ OgForm 补丁：未识别的键丢弃；行列表按行拼接。
 *  产物只回填表单，落库仍走既有保存链（自动保存/手动保存）。 */
export function ogPatchFromFills(fills: Record<string, unknown>): Partial<OgForm> {
  const patch: Partial<OgForm> = {};
  for (const [k, v] of Object.entries(fills)) {
    if (typeof v === "string") {
      const text = v.trim();
      if (!text) continue;
      switch (k) {
        case "summary": patch.summary = text; break;
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

const PAYOFF_KIND_SET = new Set<string>(PAYOFF_KINDS.map((x) => x.value));

export function ogGaps(form: OgForm): { key: string; label: string }[] {
  const gaps: { key: string; label: string }[] = [];
  for (const { key, label } of REQ_FIELDS) {
    if (String(form[key] ?? "").trim() === "") gaps.push({ key: String(key), label });
  }
  return gaps;
}

export function ogToForm(d: ChapterData | null | undefined): OgForm {
  const o = d?.outline ?? {};
  const m = d?.memo ?? {};
  const pp = m.payoff_plan ?? {};
  return {
    title: d?.title ?? "",
    summary: o.summary ?? "",
    chars: (o.characters ?? []).join("\n"),
    mres: (pp.must_resolve ?? []).join("\n"),
    mhold: (pp.must_hold ?? []).join("\n"),
    changes: (m.required_changes ?? []).join("\n"),
    ban: (m.prohibitions ?? []).join("\n"),
    mood: d?.emotional_design?.primary_mood ?? "",
    payoffs: (d?.micro_payoffs ?? []).map((mp) => ({
      k: PAYOFF_KIND_SET.has(mp.kind ?? "") ? (mp.kind as string) : "clue",
      d: mp.description ?? "",
    })),
    ladder: d?.ladder_exit ?? "",
    challenge: d?.challenge ?? "",
    stage: d?.plot_stage ?? "",
    wt: d?.word_target != null ? String(d.word_target) : "",
    plots: (d?.plot_items ?? []).map((s) => String(s)),
  };
}

/** 字数区间校验：返回用户可读问题列表，非空则保存被拦截。 */
export function ogFormIssues(form: OgForm): string[] {
  const issues: string[] = [];
  if (form.wt.trim() !== "") {
    const wt = parseInt(form.wt, 10);
    if (!Number.isFinite(wt) || wt < 500 || wt > 6000) {
      issues.push("本章目标字数需在 500-6000 之间（留空默认 2500）");
    }
  }
  return issues;
}

/** AI 起草覆盖确认判定：留存章纲格子有内容即需二次确认。
 *  **不含剧情 plots**——AI 起草只覆盖章纲格子，剧情列表不参与也不被动。 */
export function ogHasDraftContent(form: OgForm): boolean {
  return (
    [
      form.summary,
      form.mood,
      form.changes,
      form.ban,
      form.ladder,
      form.wt,
      form.challenge,
      form.stage,
    ].some((v) => String(v ?? "").trim() !== "") || form.payoffs.some((p) => p.d.trim() !== "")
  );
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
      characters: lines(form.chars),
    },
    memo: {
      ...(existing?.memo ?? {}),
      payoff_plan: {
        ...(existing?.memo?.payoff_plan ?? {}),
        must_resolve: lines(form.mres),
        must_hold: lines(form.mhold),
      },
      required_changes: lines(form.changes),
      prohibitions: lines(form.ban),
    },
    emotional_design: {
      ...(existing?.emotional_design ?? {}),
      primary_mood: form.mood,
    },
    // 读者获得：类型（中文标签由渲染侧映射）+ 一句话描述；位置档已退役
    micro_payoffs: form.payoffs
      .filter((mp) => mp.d.trim())
      .map((mp) => ({
        kind: mp.k,
        description: mp.d.trim(),
      })),
    ladder_exit: form.ladder.trim(),
    // 章内剧情：**恒带键**（presence-gate：缺键保持原样、显式 [] 清空——见 chapter-data 场景）。
    // 输入侧已 maxLength/条数卡，此处防绕过再夹一次；空白条目不算一条。
    plot_items: form.plots
      .map((s) => s.slice(0, PLOT_MAX_LEN))
      .filter((s) => s.trim() !== "")
      .slice(0, PLOT_MAX_ITEMS),
    // 拆章两格：整表回传（缺键会被装配端写空——见 chapter-data 场景）
    challenge: form.challenge.trim(),
    plot_stage: form.stage.trim(),
    // 兜底 clamp（正常路径已被 ogFormIssues 拦截，此处防绕过）
    word_target: Number.isFinite(wt) && wt > 0 ? Math.min(6000, Math.max(500, wt)) : null,
  };
}
