// 查询 key 工厂＋失效映射单源（c-query-cache-layer）。
// 约定：key = [域, 资源id, 参数]；写操作经 queryKeys 失效相关查询，
// 杜绝字符串 key 散落与手工事件广播。
export const queryKeys = {
  /** 书架列表（GET /novels 全量树） */
  novels: ["novels"] as const,
};
