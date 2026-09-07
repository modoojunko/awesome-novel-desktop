import { defineConfig, type Plugin } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'url'

// brand/brand.json 是全仓品牌唯一声明处（brand-name-single-source）；
// index.html 静态 title 在此构建期注入（组合名兜底，JS 未执行前的首帧即正确）。
const brand = JSON.parse(
  readFileSync(fileURLToPath(new URL('../../brand/brand.json', import.meta.url)), 'utf-8'),
) as { name: string; nameEn: string; mark: string; tagline: string }

/** 构建期替换 index.html 的 <title> */
function brandTitle(): Plugin {
  return {
    name: 'brand-title',
    transformIndexHtml(html) {
      const title = `${brand.name} · ${brand.nameEn}`
      return html.replace(/<title>.*?<\/title>/, `<title>${title}</title>`)
    },
  }
}

export default defineConfig({
  plugins: [vue(), tailwindcss(), brandTitle()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // 5175 与 dev-up 的 S_FRONT_PORT 对齐；5173 是 C端前端默认端口，撞车后
    // playwright 的 reuseExistingServer 会复用错应用导致 e2e 大面积假失败
    port: 5175,
    // 端口被占时直接报错，避免 vite 静默递增端口后连到错误的服务
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:19000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].[hash].js',
        chunkFileNames: 'assets/[name].[hash].js',
        assetFileNames: 'assets/[name].[hash][extname]',
      },
    },
  },
})
