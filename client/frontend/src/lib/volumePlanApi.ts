// volume-plan-ai 三端点契约（client/backend/volumes/ai_plan.py 同源字面）
// 三端点均只返回草稿/报告（不写任何表）；校验两次失败后端降级 degraded=true + text（不 502）。

import { api } from "./api";

export interface VolumePlanCard {
  no: number;
  spine: string;
  conflict: string;
  ending: string;
  focus: string;
  focus_axis: string;
}

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
  goal: string;
  ending: string;
  plants: string[];
  reveals: string[];
  chapter_target: number;
  checks: string[];
}

export interface VolumeExpandResult {
  ok: boolean;
  vol_no: number;
  plan_line: string;
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
  /** 3 套可行走法（PRO） */
  options: (pid: string, line: string): Promise<VolumeOptionsResult> =>
    api.post(path(pid, "/ai/options"), { line }),
  /** 展开卷纲草稿（PRO） */
  expand: (pid: string, line: string, volNo?: number | null): Promise<VolumeExpandResult> =>
    api.post(path(pid, "/ai/expand"), { line, vol_no: volNo ?? null }),
  /** 卷纲体检（免费 · 只读例外通道） */
  check: (pid: string, ref: string): Promise<VolumeCheckResult> =>
    api.post(path(pid, `/${ref}/ai/check`), {}),
};
