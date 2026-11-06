/**
 * 知识关系类型中文标签与视图句式（c-kb-relations-view）。
 *
 * 单一来源：KbOrganizePanel（整理面板）与 KbEntryRelations（知识视图「关联知识」段）
 * 同源 import，标签永不漂移。refines 沿用整理面板现词「细化」。
 *
 * 句式按关系类别定制（不用「出自/来自」方向后缀——近义词分不出方向，评审定谳）：
 * 出向（本知识 → 对端）「适用于 B」式，入向（对端 → 本知识）「B 适用于本知识」式；
 * contradicts 对称（与 B 相冲 / 与 B 相冲）。
 */

export const REL_TYPE_LABELS: Record<string, string> = {
  refines: "细化",
  contradicts: "相冲",
  depends_on: "依赖",
  instance_of: "属于",
  derived_from: "源自",
  applies_to: "适用于",
};

export function relTypeLabel(relType: string): string {
  return REL_TYPE_LABELS[relType] ?? relType;
}

export type RelDirection = "out" | "in";

/** 出向句式：本知识 → 对端。例：「适用于 B」「与 B 相冲」。 */
export function relPhraseOut(relType: string, otherTitle: string): string {
  switch (relType) {
    case "contradicts":
      return `与 ${otherTitle} 相冲`;
    case "instance_of":
      return `属于 ${otherTitle}`;
    case "derived_from":
      return `源自 ${otherTitle}`;
    case "depends_on":
      return `依赖 ${otherTitle}`;
    case "refines":
      return `细化 ${otherTitle}`;
    case "applies_to":
    default:
      return `适用于 ${otherTitle}`;
  }
}

/** 入向句式：对端 → 本知识。例：「B 适用于本知识」。 */
export function relPhraseIn(relType: string, otherTitle: string): string {
  switch (relType) {
    case "contradicts":
      return `与 ${otherTitle} 相冲`;
    case "instance_of":
      return `${otherTitle} 属于本知识`;
    case "derived_from":
      return `${otherTitle} 源自本知识`;
    case "depends_on":
      return `${otherTitle} 依赖本知识`;
    case "refines":
      return `${otherTitle} 细化本知识`;
    case "applies_to":
    default:
      return `${otherTitle} 适用于本知识`;
  }
}

/** 视图行文案：按方向拼句（标签已含在句式语义里，不重复前缀）。 */
export function relPhrase(relType: string, direction: RelDirection, otherTitle: string): string {
  return direction === "out"
    ? relPhraseOut(relType, otherTitle)
    : relPhraseIn(relType, otherTitle);
}
