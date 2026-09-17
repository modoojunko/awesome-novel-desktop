/** 右栏 AI 辅助「检测族」契约（后端 write/ai_check.py + chapters/ai_draft.py + write/router.py）。
 *
 * - runAiCheck：六类案头检查（卷纲/关系/伏笔冲突、文风一致性、标记偏离、建议补边），
 *   产出 findings 就地弹窗消费，不落库。
 * - fillOutlineGaps：按缺口清单补全章纲字段，产物由表单承接后走既有保存链。
 * - refinePrompt：按模式修订整章提示词（提案制：弹窗确认后走既有提示词保存链）。
 */
import { api } from "./api";

export type AiCheckKind =
  | "volume_conflict"
  | "relations_conflict"
  | "hooks_conflict"
  | "style_consistency"
  | "style_deviations"
  | "relation_suggest";

export const CHECK_TITLE: Record<AiCheckKind, string> = {
  volume_conflict: "卷纲冲突检测",
  relations_conflict: "关系冲突检测",
  hooks_conflict: "伏笔冲突检测",
  style_consistency: "文风一致性检查",
  style_deviations: "标记偏离段落",
  relation_suggest: "建议补边",
};

export interface AiFinding {
  title: string;
  detail: string;
}

/** 六类案头检查：返回 finding 列表（空数组＝没有发现问题）。 */
export async function runAiCheck(
  projectId: string,
  chapterRef: string,
  kind: AiCheckKind,
): Promise<AiFinding[]> {
  const data = (await api.post(
    `/novels/${projectId}/chapters/${chapterRef}/ai-check`,
    { kind },
  )) as { findings?: AiFinding[] };
  return data.findings ?? [];
}

/** 章纲缺项补全：missing 为后端白名单键（前端由缺口标签映射）。 */
export async function fillOutlineGaps(
  projectId: string,
  chapterRef: string,
  missing: string[],
): Promise<Record<string, unknown>> {
  const data = (await api.post(
    `/novels/${projectId}/chapters/${chapterRef}/outline/fill-gaps`,
    { missing },
  )) as { fills?: Record<string, unknown> };
  return data.fills ?? {};
}

export type RefineMode = "negative" | "concise";

export const REFINE_TITLE: Record<RefineMode, string> = {
  negative: "补全负向约束",
  concise: "精简提示词",
};

/** 提示词精修（提案制）：产物不落库，作者确认后由调用方写入提示词存储。 */
export async function refinePrompt(
  projectId: string,
  chapterRef: string,
  mode: RefineMode,
  currentPrompt?: string,
): Promise<string> {
  const data = (await api.post(
    `/novels/${projectId}/chapters/${chapterRef}/write/prompt/refine`,
    { mode, current_prompt: currentPrompt ?? "" },
  )) as { prompt?: string };
  return data.prompt ?? "";
}

/** 采纳精修稿：走既有提示词保存链（与提示词页签手工保存同一端点）。 */
export async function saveWritePrompt(
  projectId: string,
  chapterRef: string,
  content: string,
): Promise<void> {
  await api.put(`/novels/${projectId}/chapters/${chapterRef}/prompts/write`, {
    content,
  });
}
