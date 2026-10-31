// 写作知识库 API（c-knowledge-base）：账号级知识条目/库，信封 {ok, data} 同源。
import { request } from "./api";

export interface KbEntry {
  id: string;
  genre: string;
  concept: string;
  concept_id: string;
  title: string;
  instruction: string;
  payload: Record<string, unknown>;
  example: string;
  negative_example: string;
  when: Record<string, string>;
  evidence: string;
  src_kind: string;
  src_novel_name: string;
  created_at: string;
  updated_at: string;
}

export interface KbLibrary {
  id: string;
  genre: string;
  concept: string;
  name: string;
  purpose: string;
  contract: string;
  enabled: boolean;
  /** 成员条目数（含场景条目） */
  entry_count?: number;
  /** 几本书启用（跨书计数） */
  bound_novels?: number;
  /** 本书是否已启用（带 novel_id 查询时返回） */
  bound_in_book?: number;
}

export interface KbBinding {
  id: string;
  novel_id: string;
  library_id: string;
  enabled: boolean;
  genre: string;
  concept: string;
  library_name: string;
  member_count: number;
  /** 场景条目数（不进快照，逐章挑） */
  scene_count: number;
  /** 库有更新：新增/移除条目数（显式同步前累积） */
  added: number;
  removed: number;
  library_missing: boolean;
  synced_at: string;
}

export interface KbBindResult {
  binding_id: string;
  library_id: string;
  genre: string;
  concept: string;
  library_name: string;
  member_count: number;
  /** 逐键落库计数（style.role / world.stage ...） */
  landed: Record<string, number>;
  /** 互斥替换掉的同格绑定数 */
  replaced_bindings: number;
}

export interface KbGenreCount {
  name: string;
  count: number;
  key?: string;
}

export interface KbConceptMeta {
  name: string;
  fields: { key: string; required: boolean; max_length: number | null }[];
  readonly: boolean;
}

// request() 自带 /api 前缀，这里只给功能段（同 libraryApi 的 /character-library 口径）
const BASE = "/kb";

// 后端各端点统一 {ok: true, data: ...} 信封（同 libraryApi 口径）
async function unwrap<T>(p: Promise<unknown>): Promise<T> {
  const r = (await p) as { data?: T };
  if (!r || r.data === undefined) throw new Error("响应缺少 data");
  return r.data as T;
}

export const kbApi = {
  genres: () =>
    unwrap<KbGenreCount[]>(request(`${BASE}/genres`)),

  entries: (params: { genre?: string; concept?: string; src?: string; q?: string; cursor?: string }) => {
    const sp = new URLSearchParams();
    if (params.genre) sp.set("genre", params.genre);
    if (params.concept) sp.set("concept", params.concept);
    if (params.src) sp.set("src", params.src);
    if (params.q) sp.set("q", params.q);
    if (params.cursor) sp.set("cursor", params.cursor);
    return unwrap<{ entries: KbEntry[]; next_cursor: string }>(request(`${BASE}/entries?${sp}`));
  },

  entry: (id: string) =>
    unwrap<KbEntry>(request(`${BASE}/entries/${id}`)),

  libraries: (genre?: string, novelId?: string) => {
    const sp = new URLSearchParams();
    if (genre) sp.set("genre", genre);
    if (novelId) sp.set("novel_id", novelId);
    const qs = sp.toString();
    return unwrap<KbLibrary[]>(request(`${BASE}/libraries${qs ? `?${qs}` : ""}`));
  },

  concepts: () =>
    unwrap<{ concepts: KbConceptMeta[]; themes: string[] }>(request(`${BASE}/concepts`)),

  // ── 书内绑定（c-kb-snapshot：启用落设定）──

  bind: (novelId: string, libraryId: string) =>
    unwrap<KbBindResult>(request(`${BASE}/bindings`, {
      method: "POST",
      body: JSON.stringify({ novel_id: novelId, library_id: libraryId }),
    })),

  bindings: (novelId: string) =>
    unwrap<KbBinding[]>(request(`${BASE}/bindings?novel_id=${encodeURIComponent(novelId)}`)),

  syncBinding: (bindingId: string) =>
    unwrap<{ member_count: number; landed: Record<string, number> }>(
      request(`${BASE}/bindings/${bindingId}/sync`, { method: "POST" }),
    ),

  unbind: (bindingId: string, novelId: string) =>
    unwrap<{ unbound: string }>(
      request(`${BASE}/bindings/${bindingId}?novel_id=${encodeURIComponent(novelId)}`, { method: "DELETE" }),
    ),

  createEntry: (body: {
    genre: string;
    concept: string;
    concept_id?: string;
    title?: string;
    payload?: Record<string, unknown>;
    instruction?: string;
    example?: string;
    negative_example?: string;
    when_json?: Record<string, string>;
  }) =>
    unwrap<KbEntry>(request(`${BASE}/entries`, {
      method: "POST",
      body: JSON.stringify(body),
    })),

  /** 用作原型计数回写（c-kb-character）：KbPref.adopt_count 累加 */
  usePrototype: (entryId: string) =>
    unwrap<{ entry_id: string; adopt_count: number }>(
      request(`${BASE}/entries/${entryId}/prototype-use`, { method: "POST" }),
    ),

  // ── 全局图（c-kb-organize 批7：聚合＋下钻；关系边随 AI 整理二阶段）──

  graphAggregate: () =>
    unwrap<{
      nodes: { id: string; kind: "genre" | "cell"; genre: string; concept: string; count: number }[];
      links: { source: string; target: string }[];
    }>(request(`${BASE}/graph/aggregate`)),

  graphCell: (genre: string, concept: string) => {
    const sp = new URLSearchParams({ genre, concept });
    return unwrap<{
      nodes: { id: string; kind: "entry"; genre: string; concept: string; title: string; scope: string }[];
    }>(request(`${BASE}/graph/cell?${sp}`));
  },
};
