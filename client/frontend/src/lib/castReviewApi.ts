/**
 * 章纲人物精盘 API（c-character-intro）——盘点＋提案抽卡两端点的类型与请求封装。
 *
 * 冻结契约：
 *  POST /novels/{pid}/chapters/{ref}/cast/ai-review（免费只读，require_novel_model）
 *    body  { summary, challenge, plot_stage, ladder_exit, plot_items[], characters[] }
 *    resp  { rows[{idx,echo,verdict,who,as,why,gap{need,why_not_old,suggest},defaulted}],
 *            quota{named_count,regime}, hints[{name,text}] }
 *  POST /novels/{pid}/chapters/{ref}/cast/ai-draw（PRO 生成类，require_ai_access）
 *    body  { gap{idx,need,why_not_old}, characters[], exclude[{axis,name,persona}] }
 *    resp  { cards[{axis,name,persona,entrance,exit_kind,exit_note,grade,ranks,reasons}], note }
 *
 * 契约备注（容错点）：spec 卡面要求「他是干什么的」「老角色为什么不行」两格，
 * ai-draw 响应契约块未列其键名——前端以可选键 duty / why_not_old 容错读取
 * （cardDuty/cardWhyNotOld 多键兜底；why_not_old 缺省回落盘点缺口行原文，
 * 服务端「直抄缺人行」与该值同源）。后端键名对上即逐格预填，对不上不炸。
 */
import { api, type ApiError } from "./api";

// ── 闭集（人话标签即取值，UI 与模型输出同词，零映射层）───────────────────
export const VERDICT_OLD = "老角色能演";
export const VERDICT_UNNAMED = "不起名也行";
export const VERDICT_NEW = "缺一个新角色";
export const VERDICTS = [VERDICT_OLD, VERDICT_UNNAMED, VERDICT_NEW] as const;

export const CHOICES = ["加人", "改段", "延后"] as const;
export type CastChoice = (typeof CHOICES)[number];

export const AXES = ["身份", "关系", "功能"] as const;
export const EXIT_KINDS = ["章内退场", "本卷退场", "申请常驻"] as const;
export const GRADES = ["S", "A", "B"] as const;
/** 评分三维名（逐字值，ranks/reasons 的键） */
export const RANK_DIMS = ["合不合适", "差别在哪", "好不好落地"] as const;
/** 角标小字（pk-corner g-* 附文，tasks 0.2⑤） */
export const GRADE_NOTE: Record<string, string> = {
  S: "最合适",
  A: "也行",
  B: "备选",
};

// ── 盘点端点 ────────────────────────────────────────────────────────────
export interface CastReviewBody {
  summary: string;
  challenge: string;
  plot_stage: string;
  ladder_exit: string;
  plot_items: string[];
  characters: string[];
}

export interface CastGapRow {
  /** 这段戏缺的是（≤40 字） */
  need: string;
  /** 老角色为什么不行（≤40 字） */
  why_not_old: string;
  /** 预填三选一（∈ 加人/改段/延后；出界缺省「加人」带 defaulted） */
  suggest: string;
}

export interface CastReviewRow {
  /** 段定位＝剧情条目序号（0 基，不重排）；退化整章行为 null */
  idx: number | null;
  /** 回显（照抄条目原文前 60 字） */
  echo: string;
  verdict: string;
  who: string[];
  /** 不起名的称呼建议（「不起名也行」行用） */
  as: string;
  why: string;
  gap: CastGapRow | null;
  /** suggest 出界缺省=true → 前端不打「AI 建议」标（打「默认」） */
  defaulted: boolean;
}

export interface CastQuota {
  named_count: number;
  regime: "open" | "tight";
}

export interface CastHint {
  name: string;
  text: string;
}

export interface CastReviewResponse {
  rows: CastReviewRow[];
  quota: CastQuota;
  hints: CastHint[];
  /** 丢行/滤名警示（如「这一段没判出来」、老角色能演滤空提示；≤5，不重抽） */
  warnings?: string[];
}

// ── 抽卡端点 ────────────────────────────────────────────────────────────
export interface CastExcludeItem {
  axis: string;
  name: string;
  persona: string;
}

export interface CastDrawBody {
  gap: { idx: number | null; need: string; why_not_old: string };
  characters: string[];
  exclude: CastExcludeItem[];
}

export interface CastCard {
  axis: string;
  name: string;
  persona: string;
  entrance: string;
  exit_kind: string;
  exit_note: string;
  grade: string;
  ranks: Record<string, number>;
  reasons: Record<string, string>;
  /** 他是干什么的（≤30；契约块未列键名——容错读取，见文件头） */
  duty?: string;
  /** 老角色为什么不行（服务端直抄缺人行；缺省回落缺口行原文） */
  why_not_old?: string;
}

export interface CastDrawResponse {
  cards: CastCard[];
  note: string;
}

// ── 锚定与归一（gapId=f(段 idx)，跨重盘稳定）─────────────────────────────
/** 缺口锚定 id：段 idx 派生；退化整章行锚＝chapter */
export function gapIdOf(idx: number | null): string {
  return idx == null ? "gap-chapter" : `gap-${idx}`;
}

export type VerdictKind = "old" | "unnamed" | "new" | "unknown";
export function verdictKind(v: string): VerdictKind {
  if (v === VERDICT_OLD) return "old";
  if (v === VERDICT_UNNAMED) return "unnamed";
  if (v === VERDICT_NEW) return "new";
  return "unknown";
}

/** suggest 归一：只认三值，其余一律缺省「加人」（defaulted 由响应带） */
export function castChoice(s: string): CastChoice {
  return s === "改段" || s === "延后" ? s : "加人";
}

/** 卡面「他是干什么的」容错读取（键名容错：duty / job / plot） */
export function cardDuty(card: Partial<CastCard>): string {
  return String(card.duty ?? (card as { job?: string }).job ?? (card as { plot?: string }).plot ?? "").trim();
}

/** 卡面「老角色为什么不行」：卡自带（服务端直抄）优先，回落缺口行原文 */
export function cardWhyNotOld(card: Partial<CastCard>, fallback: string): string {
  return String(card.why_not_old ?? "").trim() || fallback;
}

/** 建卡扩参的 background 拼句（design 决策 6：怎么出场＋怎么退场档值原文拍平） */
export function castBackgroundLine(fields: {
  entrance: string;
  exitKind: string;
  exitNote: string;
}): string {
  const ent = fields.entrance.trim();
  const kind = fields.exitKind.trim();
  const note = fields.exitNote.trim();
  const parts: string[] = [];
  if (ent) parts.push(`怎么出场：${ent}`);
  if (kind || note) parts.push(`怎么退场（${kind || "未定"}）：${note || "未定"}`);
  return parts.join("；");
}

// ── 写入两出口（弹窗 ↔ 工作台落账链的内部契约）───────────────────────────
export interface CastWriteFields {
  /** 称呼（≤12） */
  name: string;
  /** 他是干什么的（≤30） */
  duty: string;
  /** 一句人设（≤60） */
  persona: string;
  /** 怎么出场（≤40） */
  entrance: string;
  /** 怎么退场（三选一档值原文） */
  exitKind: string;
  /** 退场说明（≤40） */
  exitNote: string;
}

export interface CastWriteRequest {
  /** 主出口＝建卡并写入；次出口＝只加名单（预填字段不保存） */
  mode: "with-card" | "list-only";
  fields: CastWriteFields;
  /** 建卡已成功后的重试：只走名单写入（不再建卡） */
  listOnlyAfterCreate?: boolean;
}

export type CastWriteOutcome =
  | {
      ok: true;
      /** 角色表确实多了一张卡（false＝只加名单/撞名回落） */
      created: boolean;
      name: string;
      castBefore: number;
      castAfter: number;
      warnings: string[];
      /** 附加提示（撞名回落「已有同名卡，名单会自动挂上」等） */
      note?: string;
    }
  | {
      ok: false;
      kind: "create_failed" | "save_failed";
      message: string;
      /** 建卡已成功（重试只走名单写入） */
      created: boolean;
    };

// ── 请求封装 ────────────────────────────────────────────────────────────
export const castReviewApi = {
  /** 盘点（免费只读）：422 空章引导、失败不 500 */
  review: (projectId: string, chapterRef: string, body: CastReviewBody) =>
    api.post(`/novels/${projectId}/chapters/${chapterRef}/cast/ai-review`, body) as Promise<CastReviewResponse>,

  /** 提案抽卡（PRO 生成类）：403 member_required 走统一升级出口 */
  draw: (projectId: string, chapterRef: string, body: CastDrawBody) =>
    api.post(`/novels/${projectId}/chapters/${chapterRef}/cast/ai-draw`, body) as Promise<CastDrawResponse>,
};

/** 错误归类：盘点/抽卡失败态的分流依据 */
export function classifyCastError(e: unknown): {
  noModel: boolean;
  memberRequired: boolean;
  emptyChapter: boolean;
  message: string;
} {
  const err = e as Partial<ApiError> | null;
  const status = err?.status;
  const message = err?.message || "AI 没响应，可再试";
  return {
    noModel: status === 503 && (err?.reason === "no_key" || err?.reason === "missing_model"),
    memberRequired: status === 403 && err?.reason === "member_required",
    emptyChapter: status === 422,
    message,
  };
}
