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

/** 本次实际下发的提示词回显（c-char-prompt-view）：弹窗展开查看＋复制，报错有据 */
export interface AiPromptEcho {
  system: string;
  user: string;
}

/** 从简介立主角的出稿（character-bootstrap-from-intro）：只出稿不建卡，采纳走既有单格写入 */
export interface BootstrapDraft {
  name: string;
  aliases: string[];
  persona: string;
  cells: { path: string; value: string }[];
  skipped?: { key: string; why: string }[];
  /** 本次渲染提示词（旧后端无此字段＝undefined，弹窗不出折叠区） */
  prompt?: AiPromptEcho;
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

/** 建卡扩参（c-character-intro）：persona 一句人设＋prefill 只收 dossier.plot/background */
export interface CreateCharacterOpts {
  role?: string;
  persona?: string;
  prefill?: { plot?: string; background?: string };
}

/** 建卡撞同名（409 {"detail":{"code":"name_taken"}}）判定 */
export function isNameTaken(e: unknown): boolean {
  const err = e as { status?: number; code?: string } | null;
  return err?.status === 409 && (err?.code === "name_taken" || err?.code === undefined);
}

export const charactersApi = {
  list: (projectId: string) =>
    unwrap<CharacterListData>(
      api.get(`/novels/${projectId}/characters`),
    ),

  /** 建卡（向后兼容扩参，c-character-intro 2.3）：role 缺省「配角」；
   *  persona 一句人设（服务端 clamp 300）；prefill 只收 dossier.plot/background
   *  （非法键服务端 400）。撞同名 409（isNameTaken）。 */
  create: (projectId: string, name: string, opts: CreateCharacterOpts = {}) =>
    unwrap<CharacterCard>(
      api.post(`/novels/${projectId}/characters`, {
        name,
        role: opts.role ?? "配角",
        ...(opts.persona ? { persona: opts.persona } : {}),
        ...(opts.prefill ? { prefill: opts.prefill } : {}),
      }),
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

  /** 立卡出稿（书级端点，c-char-ai-card-generic）：characterId 缺省＝从简介立主角；
      带配角/反派卡 id＝右栏「一键立卡」，后端按卡角色分派模板，出稿只补空格 */
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
