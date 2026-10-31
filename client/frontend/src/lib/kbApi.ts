// 写作知识库 API（c-knowledge-base）：账号级知识条目/库/全局图，信封 {ok, data} 同源。
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

export interface KbGraphAggregate {
  id: string;
  name: string;
  count: number;
}

export interface KbGraphDetail {
  id: string;
  name: string;
  concept: string;
  instruction: string;
}

const BASE = "/api/kb";

export const kbApi = {
  genres: () =>
    request<KbGenreCount[]>(`${BASE}/genres`),

  entries: (params: { genre?: string; concept?: string; src?: string; q?: string; cursor?: string }) => {
    const sp = new URLSearchParams();
    if (params.genre) sp.set("genre", params.genre);
    if (params.concept) sp.set("concept", params.concept);
    if (params.src) sp.set("src", params.src);
    if (params.q) sp.set("q", params.q);
    if (params.cursor) sp.set("cursor", params.cursor);
    return request<{ entries: KbEntry[]; next_cursor: string }>(`${BASE}/entries?${sp}`);
  },

  entry: (id: string) =>
    request<KbEntry>(`${BASE}/entries/${id}`),

  libraries: (genre?: string) =>
    request<KbLibrary[]>(`${BASE}/libraries${genre ? `?genre=${encodeURIComponent(genre)}` : ""}`),

  concepts: () =>
    request<{ concepts: KbConceptMeta[]; themes: string[] }>(`${BASE}/concepts`),

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
    request<KbEntry>(`${BASE}/entries`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  graphAggregate: () =>
    request<KbGraphAggregate[]>(`${BASE}/graph/aggregate`),
};
