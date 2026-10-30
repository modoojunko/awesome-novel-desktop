/** 卷节奏 API（c-volume-pacing）：预设/书默认/卷配置/排段·调套路·润说明。 */

import { api } from "./api";

import type { PacingConfig, SegmentPlan } from "./volumePacing";

export type { PacingConfig };

const path = (pid: string, suffix: string) => `/novels/${pid}${suffix}`;

export interface PacingPreset {
  key: string;
  label: string;
  sub: string;
  steps_len: number;
  warn_len: number;
  hint: string;
  steps: Array<{ n: string; t: string }>;
  ch1_extra: string;
}

export interface PacingBookDefault {
  preset: string;
  steps_len: number;
}

export interface PacingPlanInfo extends SegmentPlan {
  target: number;
  steps_len: number;
}

/** GET /pacing/presets：六套预设＋书级默认＋题材建议（设定页块与卷页签共用） */
export interface PacingPresetsResult {
  presets: PacingPreset[];
  default_key: string;
  book_default: PacingBookDefault | null;
  suggested_key: string;
  theme: string;
  sub_genre: string;
}

/** GET /volumes/{ref}/pacing：卷配置＋展示预填＋实际生效配置＋段表 */
export interface VolumePacingResult {
  config: PacingConfig | null;
  prefill: PacingConfig | null;
  source: "volume" | "prev" | "book" | "genre";
  /** 实际会进注入的完整配置（卷列 → 书默认 → 空）；与 prefill/source 原义分开 */
  effective: PacingConfig | null;
  effective_source: "volume" | "book" | null;
  /** 卷列是否非空（区分「没存」与「存了但读不出来」） */
  config_present: boolean;
  config_invalid: boolean;
  book_default: PacingBookDefault | null;
  plan: PacingPlanInfo;
  presets: PacingPreset[];
  theme: string;
  sub_genre: string;
}

/** POST /pacing/plan：AI 排段预览（采纳＝PUT planned 落库） */
export interface PacingPlanDraft {
  ok: boolean;
  degraded: boolean;
  notes: Array<{ seg: number; text: string }>;
  /** degraded 时的原文兜底（给作家的可读提示） */
  text: string;
}

/** POST /pacing/tailor：AI 调一版套路（不采纳不落库；degraded 时 config 为空） */
export interface PacingTailorResult {
  ok: boolean;
  degraded: boolean;
  config: PacingConfig | null;
  note: string;
}

/** POST /pacing/polish：只润步说明（degraded 时 steps 原样回传） */
export interface PacingPolishResult {
  ok: boolean;
  degraded: boolean;
  steps: Array<{ n: string; t: string }>;
  note: string;
}

export const volumePacingApi = {
  presets: (pid: string): Promise<PacingPresetsResult> =>
    api.get(path(pid, "/pacing/presets")),

  saveBookDefault: (pid: string, body: PacingBookDefault): Promise<PacingBookDefault> =>
    api.put(path(pid, "/pacing/book-default"), body),

  getVolume: (pid: string, ref: string): Promise<VolumePacingResult> =>
    api.get(path(pid, `/volumes/${ref}/pacing`)),

  saveVolume: (pid: string, ref: string, config: PacingConfig): Promise<{ config: PacingConfig }> =>
    api.put(path(pid, `/volumes/${ref}/pacing`), config),

  /** AI 排段预览（生成类：ai-plan；采纳由 saveVolume(planned:true) 落库） */
  plan: (pid: string, ref: string): Promise<PacingPlanDraft> =>
    api.post(path(pid, `/volumes/${ref}/pacing/plan`), {}),

  /** AI 按这本书调一版套路（输出套路+步+每段几章建议；不采纳不落库） */
  tailor: (pid: string, ref: string): Promise<PacingTailorResult> =>
    api.post(path(pid, `/volumes/${ref}/pacing/tailor`), {}),

  /** AI 润一遍步骤说明（只顺措辞；步数/步序/每段几章不动） */
  polish: (
    pid: string,
    ref: string,
    steps: Array<{ n: string; t: string }>,
  ): Promise<PacingPolishResult> =>
    api.post(path(pid, `/volumes/${ref}/pacing/polish`), { steps }),
};

export default volumePacingApi;
