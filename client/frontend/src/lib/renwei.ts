/** 人味检测（c-renwei-check）：本地确定性体检的前端契约与调用。
 *
 *  纯本地：正文不出本机、不花额度、不调模型——检测结果只用于「指路」，不改正文。
 *  口径（与后端 write/renwei_check.py 同源）：
 *  - findings[].para 为 0-based 非空段序（与朱雀 segments / 问题段同轨，展示时 +1）
 *  - score === null ＝ 短章「打不了分」（<1500 字，不给人味率）
 *  - metrics 恒为 19 项；ok === null ＝ 仅参考/样本不足
 */
import { api } from "./api";


export type RenweiSev = "err" | "warn";

export interface RenweiFinding {
  rule_id: string;
  rule: string;
  sev: RenweiSev;
  /** 0-based 非空段序（UI 展示 +1） */
  para: number;
  before: string;
  hit: string;
  after: string;
  why: string;
  fix: string;
}

export interface RenweiMetric {
  k: string;
  v: string;
  t: string;
  /** 真人常见范围（P25–P75） */
  h: string;
  /** 分量（3/2/1，0＝仅观察） */
  w: number;
  ok: boolean | null;
}

export interface RenweiPriority {
  k: string;
  w: number;
  z: number;
  fix: string;
}

export interface RenweiReport {
  ok: boolean;
  chars: number;
  paras: number;
  score: { rate: number; band: string; cls: "ok" | "warn" | "err" } | null;
  priorities: RenweiPriority[];
  metrics: RenweiMetric[];
  findings: RenweiFinding[];
  short_chapter: boolean;
  mtld_unconverged: boolean;
}

/** 本地体检（免费、零额度）。失败抛出 api 层错误，由调用方兜住。 */
export function renweiCheck(projectId: string, chapterRef: string): Promise<RenweiReport> {
  return api.post(`/novels/${projectId}/chapters/${encodeURIComponent(chapterRef)}/renwei-check`);
}
