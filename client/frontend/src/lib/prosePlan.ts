/** 正文方案卡目标章校验（c-agent-dialog-prose review P1）。
 *
 * 方案卡按章持久但 ch:prose 线程跨章共享——点击旧卡时若卡上的 chapter_ref 与
 * 当前章不一致，绝不能开流：生成是「清空重写」，会把本章正文换成别章的素材。
 * 纯函数（点卡时与确认回执时各判一次，钉子好写）。 */
export function isForeignProsePlan(
  payload: Record<string, unknown>,
  currentChapterRef: string | null | undefined,
): boolean {
  const target =
    typeof payload.chapter_ref === "string" ? payload.chapter_ref.trim() : "";
  return Boolean(target && currentChapterRef && target !== currentChapterRef);
}
