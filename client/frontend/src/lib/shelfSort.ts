/**
 * 书架检索与组织——纯函数单源（c-works-toolbar，与原型 works.html v2 逐行 1:1）。
 *
 * 排序语义（design.md 决策 1/2）：状态 rank 恒为第一键（待完本→写作中→设定中→已完结），
 * 第二键为用户所选排序键，末键书名 zh 升序 tie-break。
 * 时间比较容错：接口下发无时区 ISO 字符串（后端事实），解析失败/缺失一律归 0——
 * 否则 NaN 比较会让排序静默退化为原序（评审 F1.4）。
 */
import { stageFromChapters, type NovelStage } from "@/lib/novelStage";

export const SHELF_PAGE_SIZE = 12;

export type ShelfSortKey = "recency" | "created" | "words" | "title";

export interface ShelfFilters {
  /** 状态筛选：all 或四态之一 */
  kind: "all" | NovelStage;
  /** 书名搜索（大小写不敏感包含匹配） */
  q: string;
  sort: ShelfSortKey;
  /** 分页：已显示条数 */
  shown: number;
}

/** visibleBooks 消费的最小书形状（NovelListPage 的 Novel 结构性满足）。 */
export interface ShelfNovel {
  name: string;
  total_chapters?: number;
  total_archives?: number;
  finished_at?: string | null;
  created_at?: string;
  updated_at?: string;
  word_count?: number;
}

/** 新建筛选态（切换筛选/搜索/排序时的原子重置口径单源）。 */
export function defaultFilters(): ShelfFilters {
  return { kind: "all", q: "", sort: "recency", shown: SHELF_PAGE_SIZE };
}

/** 状态 rank：待完本恒置顶、已完结恒沉底（与原型 works.html rank 表逐字一致）。 */
const RANK: Record<NovelStage, number> = { ready: 0, writing: 1, setting: 2, done: 3 };

/** 书的阶段派生（与书架四态徽章同一判据：章数 + 已归档数 + 完结时间戳）。 */
export function stageOfNovel(n: ShelfNovel): NovelStage {
  return stageFromChapters(n.total_chapters || 0, n.total_archives || 0, n.finished_at ?? null);
}

/** 时间戳容错解析：缺失/非法归 0。 */
function ts(v?: string | null): number {
  if (!v) return 0;
  const n = new Date(v).getTime();
  return Number.isFinite(n) ? n : 0;
}

/** 过滤（状态 + 书名）→ 排序（rank 优先）。返回带原索引的条目（回看等动作按索引回指）。 */
export function visibleBooks<T extends ShelfNovel>(
  novels: T[],
  filters: Pick<ShelfFilters, "kind" | "q" | "sort">,
): { book: T; idx: number }[] {
  const q = filters.q.trim().toLowerCase();
  const list: { book: T; idx: number }[] = [];
  novels.forEach((b, idx) => {
    if (filters.kind !== "all" && stageOfNovel(b) !== filters.kind) return;
    if (q && !String(b.name || "").toLowerCase().includes(q)) return;
    list.push({ book: b, idx });
  });
  list.sort((x, y) => {
    const r = RANK[stageOfNovel(x.book)] - RANK[stageOfNovel(y.book)];
    if (r) return r;
    let d = 0;
    if (filters.sort === "words") d = (y.book.word_count || 0) - (x.book.word_count || 0);
    else if (filters.sort === "title")
      d = String(x.book.name || "").localeCompare(String(y.book.name || ""), "zh");
    else if (filters.sort === "created") d = ts(y.book.created_at) - ts(x.book.created_at);
    else d = ts(y.book.updated_at) - ts(x.book.updated_at);
    if (d) return d;
    return String(x.book.name || "").localeCompare(String(y.book.name || ""), "zh");
  });
  return list;
}

/** 分页切片。 */
export function slicePage<T>(list: T[], shown: number): T[] {
  return list.slice(0, shown);
}
