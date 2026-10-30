// 建书提示（c-deconstruct-import-async 8.1）：建书时的降级提示落在书侧 KV
// （`settings/import-notice`），新书设定页顶部读它、关掉即删。与任务侧
// `import.warnings` 是两份副本：任务详情以载荷为准，这里是给用户看的。
import { api } from "./api";

export interface ImportNotice {
  items: string[];
  task_id?: string;
  at?: string;
}

export async function getImportNotice(projectId: string): Promise<ImportNotice> {
  const doc = (await api.get(`/novels/${projectId}/settings/import-notice`)) as ImportNotice;
  return { items: Array.isArray(doc?.items) ? doc.items.map(String) : [] };
}

export async function dismissImportNotice(projectId: string): Promise<void> {
  await api.delete(`/novels/${projectId}/settings/import-notice`);
}
