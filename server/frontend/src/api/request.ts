import axios, { type AxiosRequestConfig } from 'axios'
import type { AxiosInstance, AxiosResponse } from 'axios'

export interface ApiResponse<T = any> {
  code: number
  msg: string
  data?: T
  total_count?: number
  activated_count?: number
  active_limit?: number
}

/**
 * S端 API 基址规范化：统一保证带上 /api 路由前缀。
 *
 * 线上域名的路由规则用 /api/ 分流到后端服务，调用侧地址必须带该前缀；
 * 本地 dev 默认同源 /api（nginx 反代 / vite 代理），云端静态托管构建时
 * 注入 VITE_API_BASE。注入值允许两种形态：
 *   https://<域名>       → 自动补成 https://<域名>/api
 *   https://<域名>/api   → 保持原样（自定义子路径配置一律不改动）
 */
function normalizeApiBase(raw: string): string {
  const v = raw.trim().replace(/\/+$/, '')
  if (!v) return '/api'
  if (v.startsWith('/')) return v
  try {
    const u = new URL(v)
    if (!u.pathname || u.pathname === '/') return `${v}/api`
  } catch {
    /* 非 URL 形态按原样返回，交由 axios/浏览器解析报错 */
  }
  return v
}

const request: AxiosInstance = axios.create({
  baseURL: normalizeApiBase(import.meta.env.VITE_API_BASE as string | undefined || ''),
  // 60s：云托管 MinNum=0 缩容后首次请求需冷启动（30-60s），15s 默认超时会误报失败
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

/**
 * 启动期覆盖 API 基址（site-config.json 运行时层，见 lib/site-config.ts）。
 * axios 每次请求才读 defaults.baseURL，且本函数只在 main.ts bootstrap 挂载前
 * 调用一次——不存在在途请求，改写即对后续全部请求生效。
 */
export function setApiBase(raw: string): void {
  request.defaults.baseURL = normalizeApiBase(raw)
}

// ── 请求拦截器：自动注入 Authorization ──
request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── 辅助函数：401 登出（避免导入 Vue Router 造成循环依赖）──
function handleUnauthorized(): void {
  localStorage.removeItem('token')
  // 使用 location.href 而非 router.push —— 401 时 SPA 状态已不可信，整页刷新更安全
  window.location.href = '/login'
}

// ── 响应拦截器：统一错误处理 ──
// 公共冷启动自愈（云托管 MinNum=0 缩零）：传输层失败（无响应=断连/网关 503 无 CORS 头，
// 或 502/503/504）且非 429 限频时——失败请求本身已触发扩容——先等预热门闩就绪，
// 再把原请求重放一次。调用方从此不需要各自 await 门闩或自写重试（AuthPage 曾因此
// 把 503 直接甩给用户）。
// 防循环：标记写在 config 上（axios mergeConfig 会携带自定义字段，代际传递——
// WeakSet 标在旧对象上不随重放传递，会让重放无限循环）；每请求至多重放一次。
type ColdHealableConfig = AxiosRequestConfig & { _coldHealed?: boolean }
// 预热探针豁免：探针自身失败时若再进自愈分支，等于等待自己所在的 warmPromise——
// 用进行中标志短路（单例单飞，同一时刻至多一个探针）
let warmingProbe = false

request.interceptors.response.use(
  (response: AxiosResponse<ApiResponse>) => {
    const data = response.data

    // 裸字段端点（/api/devices/current 无 code 字段）→ 包裹为标准格式
    if (data && typeof data.code === 'undefined') {
      return { ...response, data: { code: 0, data: data } } as any
    }

    // code !== 0 → 统一 reject
    if (data && data.code !== 0) {
      if (data.code === 2) {
        handleUnauthorized()
      }
      // 把后端 code 挂到 Error 上：调用方需区分业务失败（code 1）与网络错误；
      // data 一并携带（account-deletion 的 code 3/4 需要其中的权益清单/剩余天数）
      const err = new Error(data.msg || '请求失败') as Error & { code?: number; data?: any }
      err.code = data.code
      err.data = data.data
      return Promise.reject(err)
    }

    return response
  },
  async (error) => {
    const status = error.response?.status
    const cfg = error.config as ColdHealableConfig | undefined
    const transportFail =
      error.response === undefined || status === 502 || status === 503 || status === 504
    if (!warmingProbe && cfg && transportFail && !cfg._coldHealed) {
      cfg._coldHealed = true
      try {
        await warmUpBackend()
        return await request.request(cfg)
      } catch {
        // 自愈重放仍失败 → 落回统一错误映射
      }
    }
    if (status === 401) {
      handleUnauthorized()
    }
    const msg = error.response?.data?.msg || (error.response ? '服务器错误' : '网络连接失败')
    // 把 HTTP status 挂到 Error 上：调用方需区分限频 429 等传输层语义（message 可能不含状态码）
    const err = new Error(msg) as Error & { status?: number }
    err.status = status
    return Promise.reject(err)
  }
)

/**
 * 预热后端（云托管 MinNum=0 冷启动兜底）：
 * 站点加载时发一个轻量请求，让实例在用户填表/浏览期间完成冷启动。
 * 无 pc_hash 的 check-auth 不查库，极轻。冷启动期间网关返回 503 属预期——
 * 失败请求本身已触发扩容，间隔重试直到实例就绪（覆盖 30-60s 冷启动窗口）。
 * 注意空 pc_hash 固定返回 code 1「缺少 pc_hash」：带业务 code 的拒绝说明
 * 后端已应答（实例已热），与无 code 的网络错误（网关 503/断连）区分开。
 *
 * 单例（single-flight）：返回同一个进行中的 Promise——数据请求/登录先
 * await 本函数作为「门闩」，避免页面数据与预热并发赛跑去打冷后端。
 * 注意：只预热一次；长会话中后端再次缩零时，由各请求自身的网络错误
 * 重试链兜底（失败请求同样会触发扩容）。
 */
let warmPromise: Promise<void> | undefined

export function warmUpBackend(attemptDelaysMs: number[] = [15_000, 15_000, 15_000, 15_000]): Promise<void> {
  warmPromise ??= (async () => {
    for (let attempt = 0; ; attempt++) {
      try {
        warmingProbe = true
        try {
          await request.get('/check-auth', { params: { pc_hash: '' } })
        } finally {
          warmingProbe = false
        }
        return
      } catch (e: any) {
        // 带 code 的拒绝 = 后端已应答（如 code 1 缺少 pc_hash）= 已就绪，无需重试
        if (e?.code !== undefined) return
        if (attempt >= attemptDelaysMs.length) return
        await new Promise((resolve) => setTimeout(resolve, attemptDelaysMs[attempt]))
      }
    }
  })()
  return warmPromise
}

export default request
