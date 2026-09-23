// chapter-plan-ai 契约（client/backend/chapters/ai_plan.py 同源字面）
// 三端点：出卡（PRO）／自检（免费只读例外）／进场锚（全档只读）。
// 出卡不落库；不足 2 张 → degraded + text（不 502）；grades 由服务端按四维名次算。

import { api } from "./api";

/** 进场锚：{text, source}——上一章有正文取正文末段，无正文取章纲落点 */
export interface ChapterEntry {
  text: string;
  source: string;
}

export interface ChapterDirection {
  axis: string;
  title: string;
  plot: string;
  obstacle: string;
  ending: string;
  acts: string[];
  stage: string;
  cast: string[];
  factions: string[];
  places: string[];
  why: string;
  gap: string;
}

export interface ChapterDirectionsResult {
  ok: boolean;
  entry: ChapterEntry;
  is_final?: boolean;
  quota_left?: number;
  diff?: { axes?: string[]; one_liner?: string[] };
  directions: ChapterDirection[];
  /** 服务端算出的字母（与 directions 序号对齐；不落库） */
  grades: string[];
  ranks?: Record<string, number[]>;
  reasons?: Record<string, string>;
  checks?: string[];
  note?: string;
  warnings?: string[];
  degraded?: boolean;
  text?: string;
  hint?: string;
}

export interface ChapterSelfcheckResult {
  ok: boolean;
  critiques?: Record<string, string>;
  weakest?: string;
  degraded?: boolean;
  hint?: string;
}

/** 排上请求体（五段；与章档案键路径一致：plot→outline.summary，其余顶层） */
export interface ChapterAdoptBody {
  title: string;
  plot?: string;
  challenge?: string;
  ending?: string;
  acts?: string[];
  stage?: string;
}

export const chapterPlanApi = {
  /** 下一章进场（全档只读；手写路径也要） */
  anchor: (pid: string, volRef: string): Promise<{ ok: boolean } & ChapterEntry> =>
    api.get(`/novels/${pid}/volumes/${volRef}/next-chapter-anchor`),
  /** 3 个互斥剧情方向（PRO） */
  directions: (pid: string, volRef: string): Promise<ChapterDirectionsResult> =>
    api.post(`/novels/${pid}/volumes/${volRef}/chapters/ai-directions`, {}),
  /** 章级自检（免费 · 只读例外） */
  selfcheck: (pid: string, chapterRef: string): Promise<ChapterSelfcheckResult> =>
    api.post(`/novels/${pid}/chapters/${chapterRef}/ai-selfcheck`, {}),
  /** 排上：建章＋五段（同一事务；重复提交幂等） */
  adopt: (pid: string, volRef: string, body: ChapterAdoptBody): Promise<{ ok: boolean; ref: string }> =>
    api.post(`/novels/${pid}/volumes/${volRef}/chapters`, body),
};
