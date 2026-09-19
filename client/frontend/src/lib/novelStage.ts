/**
 * 书的四阶段 + 「打开书时的默认落点」——单一事实源（用户 2026-09-10 拍板；
 * c-works-finish-flow 扩为四态，2026-09-19）。
 *
 * 阶段判据（只看章节与完结状态，不看 current_phase——phase 是「最近一次操作」
 * 的记账，归档过一章就会停在 archive，那不代表整本写完）：
 *   finished_at 非空      → done（已完结，完本动作落库）
 *   无章节                → setting（设定中，刚建的书）
 *   全部章节已归档未完结  → ready（待完本，就差完本这个动作；「已归档」标签退役）
 *   其余（有章节未全归档）→ writing（写作中）
 *
 * 默认落点（打开书时落哪个视图）：
 *   setting → 设定页     （第一次创建的书，先补设定）
 *   writing → 写作       （已在写作，直接回工作台）
 *   ready   → 写作       （待完本仍可加章/改稿；预览由书架「回看/查看」显式进入）
 *   done    → 预览       （完结后默认通读）
 */

export type NovelStage = "setting" | "writing" | "ready" | "done";

/** 书内视图名（与 useWorkbench 的 WorkspaceView 同构）。 */
export type LandingView = "advanced-settings" | "workbench" | "archives";

export const STAGE_LABEL: Record<NovelStage, string> = {
  setting: "设定中",
  writing: "写作中",
  ready: "待完本",
  done: "已完结",
};

/** 由「章节总数 / 已归档章节数 / 完结时间戳」派生阶段。 */
export function stageFromChapters(
  totalChapters: number,
  archivedChapters: number,
  finishedAt?: string | null,
): NovelStage {
  if (finishedAt) return "done";
  if (totalChapters <= 0) return "setting";
  if (archivedChapters >= totalChapters) return "ready";
  return "writing";
}

/** 阶段 → 打开书时的默认落点视图。 */
export function landingViewFor(stage: NovelStage): LandingView {
  if (stage === "setting") return "advanced-settings";
  if (stage === "done") return "archives";
  // writing / ready 都落写作：待完本还没「完本」，写作仍是主操作面
  return "workbench";
}
