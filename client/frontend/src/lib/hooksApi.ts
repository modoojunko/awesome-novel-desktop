/**
 * 伏笔 API 客户端（foreshadow-settings-v2 tasks 4.2）——真表端点的类型与请求封装。
 *
 * 后端契约见 settings/hooks_router.py：
 *  - 列表一次给全（含 code/#H-####；台账三分组由前端按 status 归堆）
 *  - 字段级 PATCH（白名单：description/type/priority/status/三列章引用/payoff_note）
 *  - 删除即时落库并返回撤销凭证（ops token）；restore 按原 id 原样恢复
 *  - 章节引用只认同书章 id；mentioned_chapter_id 不在 PATCH 白名单（归档联动专属）
 */

import { api } from "./api";

export interface HookEntry {
  id: string;
  novel_id: string;
  seq: number;
  /** 展示编号 #H-####（由 seq 派生） */
  code: string;
  description: string;
  type: string;
  priority: number;
  status: "active" | "resolved" | "abandoned";
  introduced_chapter_id: string | null;
  planned_chapter_id: string | null;
  resolved_chapter_id: string | null;
  mentioned_chapter_id: string | null;
  payoff_note: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface HookListData {
  count: number;
  items: HookEntry[];
}

export interface HookUndo {
  token: string;
  hook_id: string;
}

export interface HookDeleteResult {
  receipt: string;
  undo: HookUndo;
}

/** 伏笔 PATCH 白名单（与后端 _PATCHABLE 镜像；mentioned_chapter_id 不在内）。 */
export type HookPatchBody = Partial<
  Pick<
    HookEntry,
    | "description"
    | "type"
    | "priority"
    | "status"
    | "introduced_chapter_id"
    | "planned_chapter_id"
    | "resolved_chapter_id"
    | "payoff_note"
  >
>;

/** 卷章树（GET /volumes：选择器数据源——章条目含 DB id，foreshadow-settings-v2 起）。 */
export interface ChapterTreeEntry {
  id: string;
  ref: string;
  volume: number;
  chapter: number;
  title: string;
  status: string;
  word_count: number;
  has_prose?: boolean;
  archived?: boolean;
}

export interface VolumeTreeEntry {
  ref: string;
  title: string;
  summary: string;
  chapter_count: number;
  chapters: ChapterTreeEntry[];
}

/** 后端统一信封 {ok, data}；入参是未 await 的 request() Promise（直接传会读到 Promise.data → 恒 undefined） */
async function unwrap<T>(p: Promise<unknown>): Promise<T> {
  const r = (await p) as { data?: T };
  if (!r || r.data === undefined) throw new Error("响应缺少 data");
  return r.data;
}

export const hooksApi = {
  list: (projectId: string) =>
    unwrap<HookListData>(api.get(`/novels/${projectId}/hooks`)),

  create: (projectId: string, body: HookPatchBody = {}) =>
    unwrap<HookEntry>(api.post(`/novels/${projectId}/hooks`, body)),

  patch: (projectId: string, id: string, body: HookPatchBody) =>
    unwrap<HookEntry>(api.patch(`/novels/${projectId}/hooks/${id}`, body)),

  remove: (projectId: string, id: string) =>
    unwrap<HookDeleteResult>(api.delete(`/novels/${projectId}/hooks/${id}`)),

  /** 按原 id 原样恢复（id 与 seq 不变）；token＝DELETE 返回的撤销凭证。 */
  restore: (projectId: string, undo: HookUndo) =>
    unwrap<HookEntry>(
      api.post(`/novels/${projectId}/hooks/${undo.hook_id}/restore`, { token: undo.token }),
    ),

  /** 卷章树（伏笔选择器数据源；/volumes 返回裸数组，非 {ok,data} 信封）。 */
  volumes: (projectId: string) =>
    api.get(`/novels/${projectId}/volumes`) as Promise<VolumeTreeEntry[]>,
};
