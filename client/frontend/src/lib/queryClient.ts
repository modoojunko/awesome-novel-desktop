// 应用级 QueryClient 单源（c-query-cache-layer）：main.tsx 挂 Provider，
// 非组件模块（如 lib/portal）经此做 imperative 取数/失效。
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 失败立即进错误态（原单次请求口径；401 每次重试都会重复触发踢出）
      retry: false,
      // 仅挂载与显式失效取数（桌面壳频繁发 focus 事件，默认开启会让
      // 书架每次切回窗口都闪加载骨架并多发请求）
      refetchOnWindowFocus: false,
    },
  },
});
