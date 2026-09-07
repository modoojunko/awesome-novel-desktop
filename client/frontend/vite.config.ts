import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import path from "path";

// brand/brand.json 是全仓品牌唯一声明处（brand-name-single-source）；
// index.html 静态 title 在此构建期注入，组合式与改前值逐字节一致。
const brand = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../brand/brand.json"), "utf-8"),
) as { name: string; nameEn: string; mark: string; tagline: string };

/** 构建期替换 index.html 的 <title>（JS 未执行前的首帧即正确） */
function brandTitle(): Plugin {
  return {
    name: "brand-title",
    transformIndexHtml(html) {
      const title = `${brand.nameEn} — ${brand.name}，${brand.tagline}`;
      return html.replace(/<title>.*?<\/title>/, `<title>${title}</title>`);
    },
  };
}

export default defineConfig({
  plugins: [react(), brandTitle()],
  base: "./",
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  preview: {
    allowedHosts: true,
  },
});
