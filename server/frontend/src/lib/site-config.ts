/**
 * S端 运行时站点配置：同源 site-config.json 是部署级配置（API 基址/备案号）的
 * 单一换发点——改这一个文件重新上传静态托管即全站生效，无需重新构建前端。
 *
 * 三层优先级：本文件非空值 > 构建期 env 烘焙（.env.production[.local]）> 内置默认。
 * JSON 中字段为空串或缺省 = 「回落构建期值」，不是清空。
 *
 * 加载纪律：
 * - 仅生产构建加载；dev/e2e 零感知（否则本地开发会吃到生产基址连错后端，
 *   e2e 也会绕开 playwright 注入的测试备案号）；
 * - 同源相对路径、单次尝试、3s 超时、no-store（换文件立即生效，不被缓存拖延）；
 * - 任何失败（404/网络/非法 JSON/超时）fail-open 返回空配置，绝不阻塞渲染。
 */

export interface SiteRuntimeConfig {
  apiBase?: string
  beianIcp?: string
  beianPolice?: string
  beianPoliceLink?: string
  brandName?: string
}

const CONFIG_URL = 'site-config.json'
const FETCH_TIMEOUT_MS = 3_000

const KNOWN_KEYS = ['apiBase', 'beianIcp', 'beianPolice', 'beianPoliceLink', 'brandName'] as const

/** 白名单清洗：只认 5 个已知键，字符串 trim 后非空才采纳，其余一律丢弃。
 * export 仅供 tests/site-config.test.ts（node --test 零依赖）验证语义。 */
export function sanitize(raw: unknown): SiteRuntimeConfig {
  const out: SiteRuntimeConfig = {}
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return out
  const obj = raw as Record<string, unknown>
  for (const key of KNOWN_KEYS) {
    const v = obj[key]
    if (typeof v === 'string' && v.trim()) out[key] = v.trim()
  }
  return out
}

export async function loadSiteConfig(): Promise<SiteRuntimeConfig> {
  if (import.meta.env.DEV) return {}

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const res = await fetch(CONFIG_URL, { cache: 'no-store', signal: controller.signal })
    if (!res.ok) {
      console.warn(`[site-config] ${CONFIG_URL} HTTP ${res.status}，回落构建期配置`)
      return {}
    }
    return sanitize(await res.json())
  } catch {
    console.warn(`[site-config] ${CONFIG_URL} 加载失败，回落构建期配置`)
    return {}
  } finally {
    clearTimeout(timer)
  }
}
