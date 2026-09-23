import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";
// 设计系统在 tailwind 之后加载（覆盖共享类）；按屏追加在 base 之后
import "./design/base.css";
import "./design/list.css";
import "./design/model-config.css";
import "./design/book.css";
import "./design/landing.css";

// 默认值对齐既有取数语义（c-query-cache-layer 评审 P2）：
// retry:false——失败立即进错误态（原单次请求口径；401 每次重试都会重复触发踢出）；
// refetchOnWindowFocus:false——仅挂载与显式失效取数（桌面壳频繁发 focus 事件，
// 默认开启会让书架每次切回窗口都闪加载骨架并多发请求）。
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <App />
      </HashRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
