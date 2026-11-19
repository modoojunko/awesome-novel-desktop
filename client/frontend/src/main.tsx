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
import "./design/image-assets.css";
import "./design/library.css";
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

// 启动画面淡出（index.html 内联 #boot-splash，视觉延续壳层 loading.html）：
// React 首帧提交后（下一帧）开始淡出，露出界面随 page-enter 浮起；
// 600ms 兜底移除节点（transition 450ms），React 未挂载（bundle 加载失败）时
// 画面停留转圈——比白屏好，且壳层装载看门狗仍兜底。
function dismissBootSplash() {
  const el = document.getElementById("boot-splash");
  if (!el) return;
  el.classList.add("boot-splash--out");
  window.setTimeout(() => el.remove(), 600);
}
requestAnimationFrame(dismissBootSplash);
