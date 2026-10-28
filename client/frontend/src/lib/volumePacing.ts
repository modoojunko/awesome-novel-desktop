/** 卷节奏前端镜像（c-volume-pacing）——段表/拍位公式与后端
 *  `volumes/pacing.py` 单源对拍（tests 不允许漂移）：
 *  - 段数＝max(1, ⌊章数目标÷每段几章⌋)，末段吸收余数；
 *  - 章的拍位＝落在哪个段区间＋段内第几步；步名取当前套路步表。
 *  展示文案（六套路的名称/步表/提示语）由后端 `/pacing/presets` 下发，
 *  本镜像只承载公式与最小说明——文案改后端，前端不持有第二份。
 */

export interface PacingSteps {
  n: string;
  t: string;
}

export interface PacingConfig {
  preset: string;
  steps: PacingSteps[];
  steps_len: number;
  ch1_extra_on: boolean;
  ch1_extra: string;
  planned: boolean;
}

export interface SegmentPlan {
  /** 段数（末段吸收余数） */
  n: number;
  /** 余数章数（0＝整除） */
  rem: number;
  /** 末段起始章 */
  last_from: number;
  /** 末段结束章（＝章数目标） */
  last_to: number;
}

export interface BeatPosition {
  seg: number;
  step_idx: number;
  step_name: string;
  step_task?: string;
}

/** 段表：与后端 segment_plan 同口径。目标 0/缺省＝1 段（last_to 0，展示层自隐藏）。 */
export function segmentPlan(target: number, stepsLen: number): SegmentPlan {
  const t = Math.max(0, Math.floor(target || 0));
  const len = Math.max(1, Math.floor(stepsLen || 1));
  if (t === 0) return { n: 1, rem: 0, last_from: 1, last_to: 0 };
  const n = Math.max(1, Math.floor(t / len));
  const rem = t % len;
  return { n, rem, last_from: (n - 1) * len + 1, last_to: t };
}

/** 章号 → 拍位；未配置/越界 → null（下游按无拍位口径渲染）。 */
export function beatOf(
  chapterNo: number,
  config: Pick<PacingConfig, "steps" | "steps_len"> | null | undefined,
  chapterTarget: number | null | undefined,
): BeatPosition | null {
  if (!config || !chapterNo || chapterNo < 1) return null;
  const target = Math.floor(chapterTarget || 0);
  if (target <= 0 || chapterNo > target) return null;
  const len = Math.max(1, Math.floor(config.steps_len || 1));
  const n = Math.max(1, Math.floor(target / len));
  const seg = Math.min(n, Math.floor((chapterNo - 1) / len) + 1);
  const idx = (chapterNo - 1) % len;
  const step = config.steps[Math.min(idx, config.steps.length - 1)];
  if (!step) return null;
  return { seg, step_idx: idx + 1, step_name: step.n };
}

/** 拖沓提醒：每段章数达到该套路的拖线（展示层黄牌）。 */
export function isOverlong(stepsLen: number, warnLen: number): boolean {
  return Math.floor(stepsLen || 0) >= Math.max(1, Math.floor(warnLen || 1));
}
