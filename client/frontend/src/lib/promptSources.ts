/**
 * 提示词组装来源 API 客户端（prompt-sources，storyline.html 四期尾）。
 *
 * 契约见 write/prompt_sources.py：六处来源的只读投影（label/chars/preview），
 * 行序固定 = 全书设定 / 大纲·卷纲 / 本章章纲 / 全书文风＋本章调整 /
 * 伏笔进展·截至上一章 / 本章涉及角色。
 */

import { request } from "./api";

export interface PromptSource {
  key: string;
  label: string;
  chars: number;
  preview: string;
  empty: boolean;
}

export interface PromptSourcesResult {
  sources: PromptSource[];
  total_chars: number;
  cast_count: number;
}

export async function fetchPromptSources(
  projectId: string,
  chapterRef: string,
): Promise<PromptSourcesResult> {
  return (await request(
    `/novels/${projectId}/chapters/${chapterRef}/prompt-sources`,
    { quiet: true },
  )) as PromptSourcesResult;
}
