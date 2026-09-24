// volume-plan-ai 三端点契约（client/backend/volumes/ai_plan.py 同源字面）
// 三端点均不落库：产出为草稿/报告；校验两次失败后端降级 degraded=true + text（不 502）。
// c-volume-antagonist 终版：plans/expand 带结构化 antagonist 两字段；answered 四问可作约束。

import { api } from "./api";
import type { DrawExcludeItem } from "./drawSession";

export interface VolumePlanCard {
  no: number;
  spine: string;
  conflict: string;
  ending: string;
  focus: string;
  focus_axis: string;
  antagonist_type: string;
  antagonist_line: string;
}

/** 四问已答（互切保留、作 options/expand 约束——作家答过的不被改写） */
export interface PlanAnswers {
  q1: string;
  conflict: string;
  antagonist_type: string;
  antagonist_line: string;
  q4: string;
}

export const EMPTY_ANSWERS: PlanAnswers = {
  q1: "", conflict: "", antagonist_type: "", antagonist_line: "", q4: "",
};

export interface VolumeOptionsResult {
  ok: boolean;
  plans: VolumePlanCard[];
  note: string;
  volume_estimate: string;
  similar: boolean;
  warnings: string[];
  degraded?: boolean;
  text?: string;
  hint?: string;
}

export interface VolumeExpandDraft {
  name: string;
  summary: string;
  conflict: string;
  ending: string;
  antagonist_type: string;
  antagonist_line: string;
  plants: string[];
  reveals: string[];
  chapter_target: number;
  checks: string[];
}

export interface VolumeExpandResult {
  ok: boolean;
  vol_no: number;
  draft?: VolumeExpandDraft;
  warnings: string[];
  degraded?: boolean;
  text?: string;
  hint?: string;
}

export type VolumeCheckStatus = "ok" | "warn" | "none";

export interface VolumeCheckItem {
  status: VolumeCheckStatus;
  text: string;
  evidence?: string;
}

export interface VolumeCheckResult {
  ok: boolean;
  vol_no: number;
  name: string;
  report: Array<{ name: string; items: VolumeCheckItem[] }>;
  degraded?: boolean;
  text?: string;
  hint?: string;
}

const path = (pid: string, suffix: string) => `/novels/${pid}/volumes${suffix}`;

export const volumePlanApi = {
  /** 3 套可行走法（PRO）——answers 带四问已答约束 */
  options: (pid: string, answers: PlanAnswers, exclude?: DrawExcludeItem[]): Promise<VolumeOptionsResult> =>
    api.post(path(pid, "/ai/options"), {
      line: answers.q1,
      conflict: answers.conflict,
      antagonist_type: answers.antagonist_type,
      antagonist_line: answers.antagonist_line,
      ending: answers.q4,
      ...(exclude?.length ? { exclude } : {}),
    }),
  /** 展开卷纲草稿（PRO）——卡面/手写四问带入，AI 不覆盖 */
  expand: (
    pid: string,
    answers: PlanAnswers,
    volNo?: number | null,
  ): Promise<VolumeExpandResult> =>
    api.post(path(pid, "/ai/expand"), {
      line: answers.q1,
      conflict: answers.conflict,
      antagonist_type: answers.antagonist_type,
      antagonist_line: answers.antagonist_line,
      ending: answers.q4,
      vol_no: volNo ?? null,
    }),
  /** 卷纲体检（免费 · 只读例外通道） */
  check: (pid: string, ref: string): Promise<VolumeCheckResult> =>
    api.post(path(pid, `/${ref}/ai/check`), {}),
};
