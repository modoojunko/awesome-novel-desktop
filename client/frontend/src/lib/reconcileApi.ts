/** 归档收尾提案（archive-reconcile）：列表/采纳/驳回/重试。
 *  行＝某章某类收尾的一次产出；未确认不进后续章节提示词。 */
import { api } from "./api";

export type ReconcileKind =
  | "set_changes"
  | "relations"
  | "hooks"
  | "lore"
  | "char_states";

export type ReconcileStatus = "pending" | "accepted" | "rejected" | "failed";

export interface ReconcileRow {
  id: string;
  chapter_id: string;
  kind: ReconcileKind;
  status: ReconcileStatus;
  payload: {
    items?: Array<{
      key?: string;
      value?: string;
      owner?: string;
      other?: string;
      rel_type?: string;
      stance?: string;
      note?: string;
      name?: string;
      state_change?: string;
      description?: string;
      evidence?: string;
    }>;
    planted?: Array<{ description?: string; evidence?: string }>;
    resolved?: Array<{ description?: string; evidence?: string }>;
  };
  error: string;
  created_at: string;
  decided_at: string;
}

export interface ReconcileProgress {
  pending: number;
  failed: number;
  accepted: number;
  rejected: number;
}

export const KIND_LABEL: Record<ReconcileKind, string> = {
  set_changes: "设定变化",
  relations: "角色关系",
  hooks: "伏笔登记",
  lore: "世界要素",
  char_states: "角色状态变化",
};

export async function fetchReconcile(
  projectId: string,
  chapterRef: string,
): Promise<{ rows: ReconcileRow[]; progress: ReconcileProgress }> {
  const data = (await api.get(
    `/novels/${projectId}/chapters/${chapterRef}/reconcile`,
  )) as { rows: ReconcileRow[]; progress: ReconcileProgress };
  return data;
}

async function post(path: string): Promise<void> {
  await api.post(path, {});
}

export const acceptReconcile = (projectId: string, chapterRef: string, rowId: string) =>
  post(`/novels/${projectId}/chapters/${chapterRef}/reconcile/${rowId}/accept`);

export const rejectReconcile = (projectId: string, chapterRef: string, rowId: string) =>
  post(`/novels/${projectId}/chapters/${chapterRef}/reconcile/${rowId}/reject`);

export const retryReconcile = (projectId: string, chapterRef: string, rowId: string) =>
  post(`/novels/${projectId}/chapters/${chapterRef}/reconcile/${rowId}/retry`);

export const revertToChapter = (projectId: string, chapterRef: string) =>
  api.post(`/novels/${projectId}/chapters/${chapterRef}/revert`, {});
