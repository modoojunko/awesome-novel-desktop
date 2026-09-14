/**
 * 角色 API 客户端（character-settings-v2）——真表端点的类型与请求封装。
 *
 * 后端契约见 settings/characters_router.py：
 *  - 列表聚合一次给全（含 code/缺口/protagonist_id/gate 摘要）
 *  - 单格 PATCH + base_rev 乐观锁（409 = rev_conflict，带 field/current/rev）
 *  - 关系 PUT 幂等 upsert（同对端一条）；删除/合并返回 undo token
 */

import { api } from "./api";

export interface CharacterCard {
  id: string;
  novel_id: string;
  seq: number;
  code: string;
  name: string;
  aliases: string[];
  role: string;
  persona: string;
  dossier: Record<string, string>;
  cog: Record<string, string>;
  rev: number;
  created_at: string | null;
  updated_at: string | null;
  /** 首次出场＝出场章最小阅读序的章号；未出场为 null */
  first_chapter?: number | null;
  /** 仅单卡 GET 携带：单向关系（他怎么看别人） */
  relations?: CharacterRelation[];
  /** 仅列表携带：门禁缺口 */
  gaps?: string[];
}

export interface CharacterRelation {
  id: string;
  owner_id: string;
  other_id: string;
  other_name?: string;
  rel_type: string;
  stance: string;
  note: string;
  ch_ref: string;
  rev: number;
}

export interface CharacterListItem extends CharacterCard {
  rel_count?: number;
}

export interface CharacterListData {
  count: number;
  protagonist_id: string | null;
  gate: { ok: boolean; no_protagonist: boolean };
  confirmed: boolean;
  items: CharacterListItem[];
}

export interface GateStatus {
  confirmed: boolean;
  stale: boolean;
  confirmed_at: string | null;
}

/** 从简介立主角的出稿（character-bootstrap-from-intro）：只出稿不建卡，采纳走既有单格写入 */
export interface BootstrapDraft {
  name: string;
  aliases: string[];
  persona: string;
  cells: { path: string; value: string }[];
  skipped?: { key: string; why: string }[];
}

export interface UndoResult {
  ok: boolean;
  receipt: string;
}

/** 后端统一信封 {ok, data}；入参是未 await 的 request() Promise（直接传会读到 Promise.data → 恒 undefined） */
async function unwrap<T>(p: Promise<unknown>): Promise<T> {
  const r = (await p) as { data?: T };
  if (!r || r.data === undefined) throw new Error("响应缺少 data");
  return r.data;
}

export const charactersApi = {
  list: (projectId: string) =>
    unwrap<CharacterListData>(
      api.get(`/novels/${projectId}/characters`),
    ),

  create: (projectId: string, name: string, role = "配角") =>
    unwrap<CharacterCard>(
      api.post(`/novels/${projectId}/characters`, { name, role }),
    ),

  get: (projectId: string, id: string) =>
    unwrap<CharacterCard>(
      api.get(`/novels/${projectId}/characters/${id}`),
    ),

  patch: (
    projectId: string,
    id: string,
    path: string,
    value: unknown,
    baseRev: number,
  ) =>
    unwrap<{ rev: number }>(
      api.patch(`/novels/${projectId}/characters/${id}`, {
        path,
        value,
        base_rev: baseRev,
      }),
    ),

  remove: (projectId: string, id: string) =>
    unwrap<{ receipt: string; undo: { op_id: string } }>(
      api.delete(`/novels/${projectId}/characters/${id}`),
    ),

  merge: (projectId: string, sourceId: string, targetId: string) =>
    unwrap<{
      receipt: string;
      undo: { op_id: string };
      target: CharacterCard;
    }>(
      api.post(`/novels/${projectId}/characters/${sourceId}/merge`, {
        target_id: targetId,
      }),
    ),

  undo: (projectId: string, token: string) =>
    unwrap<UndoResult>(
      api.post(`/novels/${projectId}/characters/ops/${token}/undo`, {}),
    ),

  upsertRelation: (
    projectId: string,
    ownerId: string,
    otherId: string,
    body: { rel_type: string; stance: string; note: string; ch_ref?: string },
  ) =>
    unwrap<CharacterRelation>(
      api.put(
        `/novels/${projectId}/characters/${ownerId}/relations/${otherId}`,
        body,
      ),
    ),

  deleteRelation: (projectId: string, ownerId: string, otherId: string) =>
    unwrap<{ receipt: string; undo: { op_id: string } }>(
      api.delete(
        `/novels/${projectId}/characters/${ownerId}/relations/${otherId}`,
      ),
    ),

  confirm: (projectId: string, first: boolean) =>
    unwrap<{ ok: boolean }>(
      api.post(`/novels/${projectId}/characters/confirm`, { first }),
    ),

  gateStatus: (projectId: string) =>
    unwrap<GateStatus | null>(
      api.get(`/novels/${projectId}/characters/gate/status`),
    ),

  aiDraft: (
    projectId: string,
    characterId: string,
    target: "persona" | "dossier" | "cog",
  ) =>
    unwrap<{
      targets: string[];
      cells: { path: string; value: string }[];
      skipped?: { key: string; why: string }[];
      act: "insert" | "replace";
    }>(
      api.post(
        `/novels/${projectId}/settings/ai/characters/${characterId}/draft`,
        { target },
      ),
    ),

  /** 从简介立主角（书级）：characterId 可选——主角待立时带上，出稿只补空格 */
  bootstrapDraft: (projectId: string, characterId?: string) =>
    unwrap<BootstrapDraft>(
      api.post(`/novels/${projectId}/settings/ai/characters/bootstrap`, {
        character_id: characterId || undefined,
      }),
    ),

  aiCheck: (projectId: string, characterId: string) =>
    unwrap<{
      items: {
        name: string;
        status: "ok" | "warn" | "conflict" | "miss";
        note: string;
        goto?: string;
      }[];
      degraded: boolean;
      degraded_reasons: string[];
      verdict: string;
    }>(
      api.post(
        `/novels/${projectId}/settings/ai/characters/${characterId}/check`,
        {},
      ),
    ),
};
