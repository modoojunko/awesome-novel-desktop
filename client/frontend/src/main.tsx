import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./lib/queryClient";
import App from "./App";
import "./index.css";
// 设计系统在 tailwind 之后加载（覆盖共享类）；按屏追加在 base 之后
import "./design/base.css";
import "./design/list.css";
import "./design/model-config.css";
import "./design/book.css";
import "./design/landing.css";
// 大屏等比缩放：必须最后引入（同选择器覆盖，压过上面各屏的原值）
import "./design/large-screen.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <HashRouter>
        <App />
      </HashRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
