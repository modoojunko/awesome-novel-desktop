/** 去 AI 味修稿向导类型（c-deai-wizard）。
 *  段号口径：paraIndex ＝ 0-based 非空段序（与朱雀 segments.paragraph_index 同轨）。 */

export type WizardStep = 1 | 2 | 3 | 4;

export type ScanSeverity = "blocking" | "advisory";

/** ① AI 味检查：单条 finding（本地确定性规则命中） */
export interface ScanFinding {
  rule: string;
  severity: ScanSeverity;
  para: number;
  excerpt: string;
  detail: string;
  count: number;
  autofixable: boolean;
}

export interface ScanMetrics {
  comma_period_ratio: number | null;
  short_para_ratio: number | null;
  dialogue_ratio: number | null;
  metaphor_density?: number | null;
}

/** ① 输出：规则扫描报告 */
export interface ScanReport {
  metrics: ScanMetrics;
  findings: ScanFinding[];
  para_count: number;
}

/** 问题段（①合并两路来源 → ②勾选 → ③改写队列） */
export interface ProblemSegment {
  para: number;
  text: string;
  source: "detector" | "rule" | "both";
  confidence: number | null;
  reasons: string[];
  suggested_fix: string;
}

/** ③ 单段候选（逐段出改稿、当场取舍） */
export type CandidateStatus = "loading" | "ready" | "error" | "empty";

export interface FixCandidate {
  seg: ProblemSegment;
  status: CandidateStatus;
  after?: string;
  error?: string;
  attempts: number;
  decision: "adopt" | "keep" | "undecided";
}

/** ④ 应用项（采用段的写回指令） */
export interface ParagraphApplyItem {
  paraIndex: number;
  from: string;
  text: string;
}

/** 后端 `/ai-flavor-scan` 出参 */
export interface AiFlavorScanResponse {
  ok: true;
  report: ScanReport;
  problems: ProblemSegment[];
  detector: { stored: boolean; human_ratio: number | null; stale_hint: null };
}

/** 写回执行器（ProsePane 内部实现经 props 注入） */
export type ApplyParagraphEdits = (items: ParagraphApplyItem[]) => boolean;
