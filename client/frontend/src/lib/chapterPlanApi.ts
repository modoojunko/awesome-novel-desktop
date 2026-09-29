// chapter-plan-ai 契约（client/backend/chapters/ai_plan.py 同源字面）
// 三端点：出卡（PRO）／自检（免费只读例外）／进场锚（全档只读）。
// 出卡不落库；不足 2 张 → degraded + text（不 502）；grades 由服务端按四维名次算。

import { api } from "./api";

/** 进场锚：{text, source}——上一章有正文取正文末段，无正文取章纲落点 */
export interface ChapterEntry {
  text: string;
  source: string;
  /** 下一章章号（服务端算，前端不再自造——标题「拆第N章」/行号 0N 取这里） */
  next_no?: number;
  /** 本卷卷号（同上，kicker 用） */
  vol_no?: number;
}

export interface ChapterDirection {
  axis: string;
  title: string;
  plot: string;
  obstacle: string;
  ending: string;
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
  /** 衔接（本地）：本次重新派生的进场 vs 卡面当前显示进场 */
  link?: { ok: boolean; text: string };
  /** 配额（本地）：这一章是否超出卷的目标章数 */
  quota?: { ok: boolean; text: string };
  critiques?: Record<string, string>;
  weakest?: string;
  degraded?: boolean;
  hint?: string;
}

/** 排上请求体（四段；与章级数据键路径一致：plot→outline.summary，其余顶层）
 *  c-og-slim-v2：「本章行动」退役（键被服务端忽略，载荷不再携带） */
export interface ChapterAdoptBody {
  title: string;
  /** 幂等键（同一次排上意图的重发同值；服务端据此返回同一章） */
  client_token?: string;
  plot?: string;
  challenge?: string;
  ending?: string;
  stage?: string;
}

/** 自检请求体：卡面草稿（自检发生在排上之前，章未落库）＋卡面当前显示进场 */
export interface ChapterSelfcheckBody {
  vol_ref: string;
  entry_text: string;
  chapter_ref?: string;
  title?: string;
  plot?: string;
  challenge?: string;
  ending?: string;
  stage?: string;
}

/** 重抽排除项（c-plan-draw-exclude）：已出批的轴＋一句话；请求携带，SHALL NOT 落库 */
export interface DrawExcludeItem {
  axis: string;
  line: string;
}

export const chapterPlanApi = {
  /** 下一章进场（全档只读；手写路径也要） */
  anchor: (pid: string, volRef: string): Promise<{ ok: boolean } & ChapterEntry> =>
    api.get(`/novels/${pid}/volumes/${volRef}/next-chapter-anchor`),
  /** 3 个互斥剧情方向（PRO）；exclude＝重抽排除清单（会话期用品） */
  directions: (pid: string, volRef: string, exclude?: DrawExcludeItem[]): Promise<ChapterDirectionsResult> =>
    api.post(`/novels/${pid}/volumes/${volRef}/chapters/ai-directions`,
      exclude?.length ? { exclude } : {}),
  /** 章级自检（免费 · 只读例外；卡面草稿随请求携带——未排上也能自检） */
  selfcheck: (pid: string, body: ChapterSelfcheckBody): Promise<ChapterSelfcheckResult> =>
    api.post(`/novels/${pid}/chapters/ai-selfcheck`, body),
  /** 回改：读一章的四段（同一张卡面；进场/章号由服务端算） */
  chapter: (
    pid: string,
    ref: string,
  ): Promise<{
    title?: string;
    plot?: string;
    challenge?: string;
    ending?: string;
    stage?: string;
    entry_text?: string;
    entry_source?: string;
    next_no?: number;
  }> => api.get(`/novels/${pid}/chapters/${ref}/plan-card`),
  /** 回改保存：读章全量 → 合并四段 → 全量 PUT。
   *  后端写入口对缺键按空写（prose/子表/word_target），局部提交会清空正文与章纲子表——
   *  必须先取全量再合并（c-chapter-plan-guards）。 */
  saveEdit: async (pid: string, ref: string, body: ChapterAdoptBody): Promise<{ ok: boolean }> => {
    const full = await api.get(`/novels/${pid}/chapters/${ref}`) as {
      outline?: Record<string, unknown> | null;
      [key: string]: unknown;
    };
    const merged = {
      ...full,
      outline: { ...(full.outline ?? {}), summary: body.plot ?? "" },
      challenge: body.challenge ?? "",
      ladder_exit: body.ending ?? "",
      plot_stage: body.stage ?? "",
    };
    await api.put(`/novels/${pid}/chapters/${ref}`, merged);
    return { ok: true };
  },
  /** 排上：建章＋四段（同一事务；重复提交幂等） */
  adopt: (pid: string, volRef: string, body: ChapterAdoptBody): Promise<{ ok: boolean; ref: string }> =>
    api.post(`/novels/${pid}/volumes/${volRef}/chapters`, body),
};
