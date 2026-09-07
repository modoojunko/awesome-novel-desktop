import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { warmUpBackend, setApiBase } from './api/request'
import { loadSiteConfig } from './lib/site-config'
import { applyBeianOverride } from './constants/site-beian'
import { applyBrandOverride, brandFull } from './constants/brand'
import './style.css'
import './design/base.css'
import './design/landing.css'
import './design/dashboard.css'

// 异步 bootstrap：挂载前应用运行时站点配置（site-config.json，生产 only，
// 失败 fail-open），保证首个 API 请求与备案条渲染都拿到最终值
async function bootstrap(): Promise<void> {
  const cfg = await loadSiteConfig()
  if (cfg.apiBase) setApiBase(cfg.apiBase)
  applyBeianOverride(cfg)
  // brandName 运行时覆盖（非空才生效，brand-name-single-source）：覆盖后同步改写
  // document.title——AuthPage 卸载恢复的 DEFAULT_TITLE 是挂载时捕获值，引导段不落
  // title 则覆盖值丢失
  if (applyBrandOverride(cfg)) document.title = brandFull()

  const app = createApp(App)
  app.use(createPinia())
  app.use(router)
  app.mount('#app')

  // 预热云端后端（冷启动兜底，本地无副作用）；在配置应用后发起，天然使用最终基址
  warmUpBackend()
}

void bootstrap()
