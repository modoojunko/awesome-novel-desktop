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

  libraries: (genre?: string) =>
    unwrap<KbLibrary[]>(request(`${BASE}/libraries${genre ? `?genre=${encodeURIComponent(genre)}` : ""}`)),

  concepts: () =>
    unwrap<{ concepts: KbConceptMeta[]; themes: string[] }>(request(`${BASE}/concepts`)),

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
};
