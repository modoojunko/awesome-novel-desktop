/**
 * 文风量化 API 客户端（style-settings-v2 tasks 2.3）。
 *
 * 后端契约见 settings/style_quant_router.py 与 ai_router.py /ai/style-* 族：
 *  - GET/PUT /settings/style-quant：全文读；写仅受理 locks（行级锁定切换，
 *    基线数值服务端只写——防表单整卡回踩，评审 P0）
 *  - GET  /settings/style-samples：样本两路（novel-samples/ 文件＋已归档章节）
 *  - POST /settings/ai/style-distill/{step1,step2,step3,commit}：三步蒸馏＋落卡
 *    （每步产物落 style-quant.draft，中断按 draft 续跑）
 *  - POST /settings/ai/style/{polish,check,fewshot-mine}：三区润色/锚定体检/例句提炼
 */

import { api } from "./api";

export interface StyleQuantRow {
  value: string;
  tolerance: number;
  locked: boolean;
}

export interface StyleQuantHistoryItem {
  at: string;
  sample_chars: number;
  confidence: number;
  baseline: Record<string, unknown>;
  mixture: Record<string, string>;
}

export interface StyleQuantDraft {
  step?: number;
  sample_chars?: number;
  step3?: { portrait?: string };
  [k: string]: unknown;
}

export interface StyleQuant {
  version: number;
  confidence: number;
  sample_chars: number;
  updated_at: string;
  baseline: Record<string, StyleQuantRow>;
  details: Record<string, string>;
  portrait: string;
  history: StyleQuantHistoryItem[];
  draft: StyleQuantDraft | null;
}

export interface StyleSamples {
  files: Array<{ name: string; chars: number }>;
  chapters: Array<{ id: string; label: string; chars: number }>;
  total: number;
  min: number;
  max: number;
  in_range: boolean;
  hint: string;
}

/** 六行基线（行序/标签与后端 style_quant_model.BASELINE_ROWS 镜像——改两边同批）。 */
export const BASELINE_ROWS: Array<[string, string]> = [
  ["narrative", "镜头与人称"],
  ["rhythm", "篇幅配比（五层）"],
  ["syntax", "句子与段落"],
  ["lexicon", "修饰密度"],
  ["emotion", "情绪外化"],
  ["dialogue_verb", "对话与动词质感"],
];

export const styleQuantApi = {
  async get(projectId: string): Promise<StyleQuant> {
    return api.get(`/novels/${projectId}/settings/style-quant`);
  },
  /** 仅锁定切换；其他字段后端忽略（服务端只写）。 */
  async putLocks(projectId: string, locks: Record<string, boolean>): Promise<StyleQuant> {
    return api.put(`/novels/${projectId}/settings/style-quant`, { locks });
  },
  async samples(projectId: string): Promise<StyleSamples> {
    return api.get(`/novels/${projectId}/settings/style-samples`);
  },
  async distillStep(
    projectId: string,
    step: 1 | 2 | 3,
    body: Record<string, unknown> = {},
  ): Promise<{ ok: boolean; resumed?: boolean; step?: number; portrait?: string }> {
    return api.post(`/novels/${projectId}/settings/ai/style-distill/step${step}`, body);
  },
  async commit(projectId: string): Promise<{ ok: boolean; quant: StyleQuant; banned_added: number }> {
    return api.post(`/novels/${projectId}/settings/ai/style-distill/commit`, {});
  },
};

export const styleAiApi = {
  /** 润色/起草三区（正文前提由后端自读；context 传当前三区所见值）。 */
  async polish(
    projectId: string,
    context: { role: string; rules: string[]; craft: string[] },
  ): Promise<{ role: string; rules: string[]; craft: string[] }> {
    return api.post(`/novels/${projectId}/settings/ai/style/polish`, { context });
  },
  async check(
    projectId: string,
    body: { role: string; rules: string[]; craft: string[] },
  ): Promise<{ checks: Array<{ name: string; res: string; note: string }>; verdict: string }> {
    return api.post(`/novels/${projectId}/settings/ai/style/check`, body);
  },
  async fewshotMine(projectId: string): Promise<{ lines: string[] }> {
    return api.post(`/novels/${projectId}/settings/ai/style/fewshot-mine`, {});
  },
};
