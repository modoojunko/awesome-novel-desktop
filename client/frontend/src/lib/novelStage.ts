/**
 * 书的三阶段 + 「打开书时的默认落点」——单一事实源（用户 2026-09-10 拍板）。
 *
 * 阶段判据（只看章节，不看 current_phase——phase 是「最近一次操作」的记账，
 * 归档过一章就会停在 archive，那不代表整本写完）：
 *   无章节            → setting（设定中，刚建的书）
 *   全部章节已归档     → done（写完了）
 *   其余（有章节未全归档）→ writing（写作中）
 *
 * 默认落点（打开书时落哪个视图）：
 *   setting → 设定页     （第一次创建的书，先补设定）
 *   writing → 写作       （已在写作，直接回工作台）
 *   done    → 预览       （写完了，默认通读）
 *
 * 注意：书架卡片的阶段标签**当前仍按 current_phase 派生**（Parity 基线口径），
 * 与本模块在「归档过章但整本未完」时可能不一致——见 tasks 6.13 的遗留项。
 */

export type NovelStage = "setting" | "writing" | "done";

/** 书内视图名（与 useWorkbench 的 WorkspaceView 同构）。 */
export type LandingView = "advanced-settings" | "workbench" | "archives";

export const STAGE_LABEL: Record<NovelStage, string> = {
  setting: "设定中",
  writing: "写作中",
  done: "已归档",
};

/** 由「章节总数 / 已归档章节数」派生阶段。 */
export function stageFromChapters(
  totalChapters: number,
  archivedChapters: number,
): NovelStage {
  if (totalChapters <= 0) return "setting";
  if (archivedChapters >= totalChapters) return "done";
  return "writing";
}

/** 阶段 → 打开书时的默认落点视图。 */
export function landingViewFor(stage: NovelStage): LandingView {
  if (stage === "setting") return "advanced-settings";
  if (stage === "done") return "archives";
  return "workbench";
}
