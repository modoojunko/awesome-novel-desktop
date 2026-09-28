import { api } from "@/lib/api";

/** 本章变化行被采纳/驳回/删除后广播（角色关系图据此重拉剧情边）。 */
export const DOSSIER_CHANGED_EVENT = "dossier-relations-changed";

/** 本章变化四域键（与后端 assemble dossier 四键一致）。 */
export type DossierDomain = "settings" | "relations" | "items" | "knowledge";

export const DOSSIER_DOMAINS: { key: DossierDomain; label: string }[] = [
  { key: "settings", label: "设定改动" },
  { key: "relations", label: "人物关系" },
  { key: "items", label: "物品变化" },
  { key: "knowledge", label: "角色认知" },
];

/** 提取任务态（后端 chapter_dossier_jobs 投影；null＝无任务）。 */
export interface DossierExtraction {
  state: "extracting" | "ok" | "failed" | "skipped";
  domains: Record<string, string>;
  error: string;
}

export interface DossierRow {
  id: string;
  domain: DossierDomain;
  status: "pending" | "accepted" | "rejected";
  flags: string;
  evidence: string;
  decided_at: string;
  // 域字段（按 domain 取）
  area?: string;
  content?: string;
  owner?: string;
  other?: string;
  rel_type?: string;
  change_note?: string;
  name?: string;
  change_type?: string;
  holder?: string;
  detail?: string;
  character?: string;
  fact?: string;
  learned?: boolean;
}

export interface DossierState {
  rows: DossierRow[];
  progress: { pending: number; accepted: number; rejected: number };
  extraction: DossierExtraction | null;
  not_extracted: boolean;
  stale: boolean;
  archived: boolean;
  accepted_count: number;
}

export interface DossierPreview {
  up_to_ref: string | null;
  domains: Record<DossierDomain, Record<string, unknown>[]>;
  counts: Record<DossierDomain, number>;
  skipped_stale_refs: string[];
}

export const dossierApi = {
  async get(projectId: string, chapterRef: string): Promise<DossierState> {
    // quiet：轮询复用同口，不触发全局副作用（frontend-auth-heal 规范）
    return api.get(`/novels/${projectId}/chapters/${chapterRef}/dossier`, {
      quiet: true,
    });
  },
  /** 逐条动作：accept / reject / restore（驳回恢复为待确认）。 */
  async rowAction(
    projectId: string,
    chapterRef: string,
    rowId: string,
    action: "accept" | "reject" | "restore",
  ): Promise<void> {
    await api.post(`/novels/${projectId}/chapters/${chapterRef}/dossier/rows/${rowId}`, {
      action,
    });
  },
  /** 删除已采纳行（AI 提错兜底；确认由 UI 承担）。 */
  async rowDelete(
    projectId: string,
    chapterRef: string,
    rowId: string,
  ): Promise<void> {
    await api.delete(`/novels/${projectId}/chapters/${chapterRef}/dossier/rows/${rowId}`);
  },
  /** 批量：accept/reject ×（全章 | 按域）。返回实际处理条数。 */
  async batch(
    projectId: string,
    chapterRef: string,
    action: "accept" | "reject",
    domain?: DossierDomain,
  ): Promise<number> {
    const d = (await api.post(`/novels/${projectId}/chapters/${chapterRef}/dossier/rows`, {
      action,
      ...(domain ? { domain } : {}),
    })) as { updated: number };
    return d.updated ?? 0;
  },
  /** 重试/补提取（未归档章＝完整归档提取；已归档章＝只重写本章变化行）。 */
  async extract(projectId: string, chapterRef: string): Promise<void> {
    await api.post(`/novels/${projectId}/chapters/${chapterRef}/dossier/extract`, {});
  },
  /** 逃生阀：跳过提取仍归档（确认与代价文案由 UI 承担）。 */
  async skip(projectId: string, chapterRef: string): Promise<void> {
    await api.post(`/novels/${projectId}/chapters/${chapterRef}/dossier/skip`, {});
  },
  /** 「截至本章」累计预览（与下一章提示词实际注入同源）。 */
  async preview(projectId: string, upToRef: string): Promise<DossierPreview> {
    return api.get(
      `/novels/${projectId}/dossier/preview?up_to_ref=${encodeURIComponent(upToRef)}`,
      { quiet: true },
    );
  },
};
