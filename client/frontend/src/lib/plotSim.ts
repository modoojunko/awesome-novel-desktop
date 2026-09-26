/**
 * 剧情推演 API 客户端（plot-sim，storyline.html 四期尾）。
 *
 * 契约见 write/plot_sim.py：AI 按章纲＋上一章结尾推 2-4 回合；AI 不可用时
 * 后端回落确定性推演（source=fallback 仅作留痕，UI 口径一致）。
 * 产物只返回不落库；「收进章纲」走既有章纲保存链**追加为本章一条剧情条目**（c-og-slim-v2：原落点「预期策略」退役）。
 */

import { request } from "./api";

export interface SimMove {
  k: string; // 顺 / 拗
  tone: "ok" | "warn";
  label: string;
  out: string;
}

export interface SimRound {
  n: number;
  beat: string;
  who: string;
  place: string;
  time: string;
  at: string;
  shift: string;
  moves: SimMove[];
}

export interface SimResult {
  ok: boolean;
  source: "ai" | "fallback";
  entry: string;
  exit: string;
  prev_label: string;
  cast: string[];
  rounds: SimRound[];
}

export async function runSimulation(
  projectId: string,
  chapterRef: string,
): Promise<SimResult> {
  return (await request(
    `/novels/${projectId}/chapters/${chapterRef}/simulate`,
    { method: "POST" },
  )) as SimResult;
}
