/** 右栏 AI 辅助「检测族」契约（后端 write/ai_check.py + chapters/ai_draft.py + write/router.py）。
 *
 * - runAiCheck：六类案头检查（卷纲/关系/伏笔冲突、文风一致性、标记偏离、建议补边），
 *   产出 findings 就地弹窗消费，不落库。
 * - fillOutlineGaps：按缺口清单补全章纲字段，产物由表单承接后走既有保存链。
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
