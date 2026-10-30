// 角色库 API（c-character-library）：账号级跨书角色卡，信封 {ok, data} 与 charactersApi 同源。
import { request } from "./api";

export interface LibraryCard {
  id: string;
  name: string;
  aliases: string[];
  role: string;
  genre: string;
  kind: string;
  persona: string;
  dossier: Record<string, string>;
  cog: Record<string, string>;
  src: { kind: "book" | "deconstruct" | "manual"; novel_name: string; ref: string; character_id: string };
  avatar: { has: boolean; url: string; thumb_url: string };
  rev: number;
  updated_at: string;
}

export interface LibraryCardInput {
  name: string;
  aliases: string[];
  role: string;
  genre: string;
  kind: string;
  persona: string;
  dossier: Record<string, string>;
  cog: Record<string, string>;
}

export interface LibraryListData {
  count: number;
  items: LibraryCard[];
}

export interface ApplyResult {
  character_id: string;
  name: string;
  role: string;
  renamed: boolean;
  demoted: boolean;
  avatar: boolean;
}

async function unwrap<T>(p: Promise<unknown>): Promise<T> {
  const r = (await p) as { data?: T };
  if (!r || r.data === undefined) throw new Error("响应缺少 data");
  return r.data as T;
}

export function listLibrary(): Promise<LibraryListData> {
  return unwrap<LibraryListData>(request("/character-library"));
}

export function createLibraryCard(input: LibraryCardInput): Promise<LibraryCard> {
  return unwrap<LibraryCard>(request("/character-library", { method: "POST", body: JSON.stringify(input) }));
}

export function updateLibraryCard(id: string, input: LibraryCardInput): Promise<LibraryCard> {
  return unwrap<LibraryCard>(
    request(`/character-library/${id}`, { method: "PUT", body: JSON.stringify(input) }),
  );
}

export function deleteLibraryCard(id: string): Promise<{ deleted: string }> {
  return unwrap<{ deleted: string }>(request(`/character-library/${id}`, { method: "DELETE" }));
}

export function importCardFromBook(
  novelId: string,
  characterId: string,
  rename: boolean,
): Promise<{ created: boolean; card: LibraryCard }> {
  return unwrap(
    request("/character-library/import/book", {
      method: "POST",
      body: JSON.stringify({ novel_id: novelId, character_id: characterId, rename }),
    }),
  );
}

export function syncCardFromBook(id: string): Promise<LibraryCard> {
  return unwrap<LibraryCard>(
    request(`/character-library/${id}/sync-from-book`, { method: "POST" }),
  );
}

export function applyCardToBook(id: string, novelId: string, rename: boolean): Promise<ApplyResult> {
  return unwrap<ApplyResult>(
    request(`/character-library/${id}/apply-to-book`, {
      method: "POST",
      body: JSON.stringify({ novel_id: novelId, rename }),
    }),
  );
}

export function randomLibraryName(gender: string): Promise<{ name: string; age: number; source: string }> {
  return unwrap<{ name: string; age: number; source: string }>(
    request("/character-library/random-name", { method: "POST", body: JSON.stringify({ gender }) }),
  );
}

export interface NovelOption {
  id: string;
  name: string;
}

/** 书架现存书（用到新书/书内导入的选书源） */
export async function listNovelOptions(): Promise<NovelOption[]> {
  const rows = (await request<NovelOption[]>("/novels")) as unknown as NovelOption[];
  return Array.isArray(rows) ? rows.map((n) => ({ id: n.id, name: n.name })) : [];
}

/** 头像字节走鉴权 fetch（<img> 不带 Bearer）——按卡缓存 objectURL，避免列表重渲重下。 */
const avatarCache = new Map<string, string>();

export type LibraryAvatarRef = Pick<LibraryCard, "id" | "avatar">;

export async function fetchLibraryAvatar(card: LibraryAvatarRef, variant: "full" | "thumb" = "thumb"): Promise<string> {
  const hit = avatarCache.get(`${card.id}:${variant}`);
  if (hit) return hit;
  const token = localStorage.getItem("auth_token") || "";
  const res = await fetch(card.avatar[variant === "full" ? "url" : "thumb_url"], {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("头像加载失败");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  avatarCache.set(`${card.id}:${variant}`, url);
  return url;
}

export function clearLibraryAvatarCache(cardId?: string): void {
  if (cardId) {
    for (const variant of ["full", "thumb"] as const) {
      const key = `${cardId}:${variant}`;
      const url = avatarCache.get(key);
      if (url) URL.revokeObjectURL(url);
      avatarCache.delete(key);
    }
    return;
  }
  for (const url of avatarCache.values()) URL.revokeObjectURL(url);
  avatarCache.clear();
}

// ── 库卡头像生成（c-library-avatar-gen） ────────────────────────────────────

export interface GeneratedLibraryAvatar {
  card_id: string;
  avatar: { has: boolean; url: string; thumb_url: string };
  rev: number;
}

/** 按卡上档案生成头像（PRO 同权：image-generate 门在后端拦截）。 */
export function generateLibraryAvatar(cardId: string): Promise<GeneratedLibraryAvatar> {
  return unwrap<GeneratedLibraryAvatar>(
    request(`/character-library/${cardId}/avatar/generate`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  );
}
