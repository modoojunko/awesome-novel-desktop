// 章纲回收/悬念两格的台账投影派生（c-og-hooks-projection）。
// 纯函数：HooksPane 同口径解析章号；两格语义与写作链同源——
// 回收＝计划收 ≤ 本章（「该收了」判定，hooks pane dueBaseChNo 同法）；
// 维持＝埋点 ≠ 本章（写作注入「排除本章引入」同口径；无埋点开书条目计入）。
// 投影只在格空时展示、不落库；台账「计划收」是作者意图，这里不赋值。
import type { ChapterLite, HookRow } from "@/hooks/useHooksLedger";

export interface HookHint {
  id: string;
  code: string;
  description: string;
  /** 计划收 ≤ 本章（该收了） */
  due: boolean;
  /** 计划收章号；未设为 null */
  plannedNo: number | null;
  /** 「计划收 第 N 章」；未设为 null */
  plannedLabel: string | null;
  /** 「埋于 第 N 章」；无埋点＝「埋于 开书」 */
  originLabel: string;
}

export interface OgHookHints {
  /** 必须在本章回收投影：该收了的悬置伏笔 */
  mres: HookHint[];
  /** 必须维持悬念投影：本章之前埋下且仍悬置的伏笔 */
  mhold: HookHint[];
  /** 全部悬置伏笔（回收格编辑候选＝全部，该收了优先——可提前收，不锁死在计划章） */
  active: HookHint[];
  /** 悬置伏笔总数（理由句用） */
  activeCount: number;
  /** 本章之前埋下的悬置数（维持格理由句用） */
  carryCount: number;
}

export function ogHookHints(
  hooks: HookRow[],
  chapters: ChapterLite[],
  currentChId: string | null,
  currentChNo: number | null,
): OgHookHints {
  const idToNo = new Map(chapters.map((c) => [c.id, c.chapter]));
  const chNoOf = (id: string | null): number | null =>
    id ? (idToNo.get(id) ?? null) : null;

  const activeRows = hooks.filter((h) => h.status === "active");
  const hintOf = (h: HookRow): HookHint => {
    const plannedNo = chNoOf(h.planned_chapter_id);
    const originNo = chNoOf(h.introduced_chapter_id);
    // API code 形如「#H-0009」——归一成裸「H-0009」，展示/落格统一 [H-0009]
    const code = (h.code || "").replace(/^[#\[]+/, "").replace(/\]$/, "");
    return {
      id: h.id,
      code,
      description: h.description || "",
      due: plannedNo != null && currentChNo != null && plannedNo <= currentChNo,
      plannedNo,
      plannedLabel: plannedNo != null ? `计划收 第 ${plannedNo} 章` : null,
      originLabel: originNo != null ? `埋于 第 ${originNo} 章` : "埋于 开书",
    };
  };

  // 回收候选：全部悬置，该收了优先、再按计划收章号升序、无计划收垫底
  const active = activeRows.map(hintOf).sort((a, b) => {
    if (a.due !== b.due) return a.due ? -1 : 1;
    const pa = a.plannedNo ?? Number.MAX_SAFE_INTEGER;
    const pb = b.plannedNo ?? Number.MAX_SAFE_INTEGER;
    return pa - pb;
  });
  const mres = active.filter((h) => h.due);
  // 维持投影：埋点 ≠ 本章（当前章 id 解析不出时不过滤，宁多勿漏）
  const carryRows =
    currentChId == null
      ? activeRows
      : activeRows.filter((h) => h.introduced_chapter_id !== currentChId);
  const mhold = carryRows.map(hintOf);
  return {
    mres,
    mhold,
    active,
    activeCount: active.length,
    carryCount: mhold.length,
  };
}

/** 候选 chips：本格已含编号的不再列 */
export function hookChipCandidates(hints: HookHint[], fieldText: string): HookHint[] {
  return hints.filter((h) => h.code && !fieldText.includes(h.code));
}
