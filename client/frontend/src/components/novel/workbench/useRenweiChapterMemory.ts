/** 人味标注的章作用域内存态（c-renwei-check）＋切章清账。
 *
 *  编辑器单实例长驻（c-prose-editor-tiptap：切章走 setContent 不重建）、
 *  ProsePane 也不随章重挂——report/settled 若不复位，旧章段号会套到新章
 *  同序号段上（串章标注）。清账是章作用域语义的一部分：切章即重新检测，
 *  同章切页签不清（ProsePane 仅 hidden 不卸载，状态自然保留）。
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { RenweiReport } from "@/lib/renwei";

export type RenweiSettled = Record<number, "done" | "skip">;

export function useRenweiChapterMemory(chapterRef: string) {
  const [report, setReport] = useState<RenweiReport | null>(null);
  const [settled, setSettled] = useState<RenweiSettled>({});

  // 切章清账：置空连带触发 marks effect 的 applyRenweiMarks(editor, null) 退场；
  // 挂载首跑为无害空操作（两块本就是初值）。
  useEffect(() => {
    setReport(null);
    setSettled({});
  }, [chapterRef]);

  // 在途重扫判章：定时器触发 → flush → check 半路切章，闭包章号过期——
  // 结果按旧章算，丢弃（不 diff、不 toast、不落回 state；判例同 ProsePane
  // refAtStart「await 落盘期间已切章即放弃」）。
  const chapterRefRef = useRef(chapterRef);
  chapterRefRef.current = chapterRef;
  const staleResult = useCallback(
    (scheduledRef: string) => chapterRefRef.current !== scheduledRef,
    [],
  );

  return { report, settled, setReport, setSettled, staleResult };
}
