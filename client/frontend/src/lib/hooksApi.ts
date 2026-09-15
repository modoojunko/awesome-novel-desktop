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

/** AI 起草候选（批2：POST /settings/ai/hooks/draft 出参；type/priority 已由后端走
 *  hooks_model 归一——非法 slug 降 mystery、非法 priority 降 2、空描述丢弃）。 */
export interface HookCandidate {
  description: string;
  type: string;
  priority: number;
}

/** AI 埋坑体检行：hook_id/code/status/goto_field 由服务端判定常量给出
 *  （模型只产 note），goto_field ∈ planned/payoff，null＝在期无需跳转。 */
export interface HookAuditCheck {
  hook_id: string;
  code: string;
  status: "ok" | "warn" | "miss";
  note: string;
  goto_field: "planned" | "payoff" | null;
}

export interface HooksAuditResult {
  checks: HookAuditCheck[];
  degraded: boolean;
  degraded_reasons: string[];
  verdict: string;
}

/** AI 拟收束方案（批3：POST /settings/ai/hooks/payoff 出参；resolved_chapter_ref
 *  已由后端走 canonical 惯例归一成 vol-N-ch-M，未必对应已建章——前端查树换 id）。 */
export interface HookPayoffResult {
  resolved_chapter_ref: string;
  payoff_note: string;
}

/** AI 查一致性行（批3）：三上下文 简介/题材/世界 × 选中伏笔；status 白名单同 audit。 */
export interface HookCheckRow {
  name: string;
  status: "ok" | "warn" | "miss";
  note: string;
}

export interface HooksCheckResult {
  checks: HookCheckRow[];
  degraded: boolean;
  degraded_reasons: string[];
  verdict: string;
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

  /** 起草伏笔（只出建议；AI 端点返回裸对象非信封。403 member_required 由
   *  request() 广播全局升级引导后继续抛出）。 */
  draftAi: (projectId: string) =>
    api.post(`/novels/${projectId}/settings/ai/hooks/draft`, {}) as Promise<{
      candidates: HookCandidate[];
    }>,

  /** 埋坑体检（全部活跃 × 已写章纲；无章纲/无活跃由后端降级免调用）。 */
  auditAi: (projectId: string) =>
    api.post(
      `/novels/${projectId}/settings/ai/hooks/audit`,
      {},
    ) as Promise<HooksAuditResult>,

  /** 拟收束方案（批3：对选中伏笔；body 传当前编辑值——后端不读库旧文）。
   *  返回规范 ref 形建议；采纳走前端组合 PATCH（见 HooksSettingForm adoptPayoff）。 */
  payoffAi: (
    projectId: string,
    body: {
      hook_id: string;
      description: string;
      type: string;
      priority: number;
      code?: string;
      planned_chapter_id?: string | null;
    },
  ) =>
    api.post(
      `/novels/${projectId}/settings/ai/hooks/payoff`,
      body,
    ) as Promise<HookPayoffResult>,

  /** 查一致性（批3：选中伏笔 × 简介/题材/世界；body 传当前编辑值）。
   *  三方全缺由后端降级免调用。 */
  checkAi: (
    projectId: string,
    body: {
      hook_id: string;
      description: string;
      type: string;
      priority: number;
      code?: string;
    },
  ) =>
    api.post(
      `/novels/${projectId}/settings/ai/hooks/check`,
      body,
    ) as Promise<HooksCheckResult>,
};
