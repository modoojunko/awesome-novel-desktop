import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import path from "path";

// brand/brand.json 是全仓品牌唯一声明处（brand-name-single-source）；
// index.html 静态 title 与内联启动画面品牌名在此注入，组合式与改前值逐字节一致。
const brand = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../brand/brand.json"), "utf-8"),
) as { name: string; nameEn: string; mark: string; tagline: string };

/** 构建期/开发期替换 index.html：<title> 与 boot-splash 的 __BRAND_NAME__
 *  （JS 未执行前的首帧即正确；transformIndexHtml 在 dev server 同样生效） */
function brandInject(): Plugin {
  return {
    name: "brand-inject",
    transformIndexHtml(html) {
      const title = `${brand.nameEn} — ${brand.name}，${brand.tagline}`;
      return html
        .replace(/<title>.*?<\/title>/, `<title>${title}</title>`)
        .replace(/__BRAND_NAME__/g, brand.name);
    },
  };
}

export default defineConfig({
  plugins: [react(), brandInject()],
  base: "./",
  // deps 缓存目录换道（判例 2026-11-15）：npm 升级 react 后 ?v= hash 未变，浏览器
  // immutable 缓存里的旧 chunk 毒杀页面——换路径强制缓存 miss（旧 .vite 可删）
  cacheDir: "node_modules/.vite2",
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
    // 双 react 副本收敛（c-writing-agent 加 react-markdown 后气泡白屏判例）：
    // hooks dispatcher null = 组件链上出现第二个 react 实例
    dedupe: ["react", "react-dom"],
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
  },
  server: {
    // dev 全程 no-store：deps chunk 内容变更（npm 升级/重优化）而 ?v= hash 未变时，
    // 浏览器 immutable 缓存会喂旧 chunk（react 19 毒缓存判例 2026-11-15）
    headers: { "Cache-Control": "no-store" },
    port: 5173,
    proxy: {
      "/api": {
        // VITE_API_PROXY：会话私有 e2e 栈可指向自起后端（默认共享 dev 栈 8000 不动）
        target: process.env.VITE_API_PROXY || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    allowedHosts: true,
  },
});
