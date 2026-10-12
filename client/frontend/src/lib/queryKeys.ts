// 查询 key 工厂＋失效映射单源（c-query-cache-layer）。
// 约定：key = [域, 资源id, 参数]；写操作经 queryKeys 失效相关查询，
// 杜绝字符串 key 散落与手工事件广播。
export const queryKeys = {
  /** 书架列表（GET /novels 全量树） */
  novels: ["novels"] as const,
  /** 拆书任务清单/详情（c-deconstruct-book）：列表轮询与写后失效同源 */
  deconstructTasks: ["deconstruct", "tasks"] as const,
  deconstructTask: (id: string) => ["deconstruct", "task", id] as const,
};
