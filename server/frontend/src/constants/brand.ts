/**
 * 品牌单一事实源消费桥（brand-name-single-source）：
 * 构建期读仓库根 brand/brand.json（前端侧唯一入口）；运行时 site-config.json
 * 的 brandName 非空时覆盖 name——免重建改名，与备案号同一换发点、同一优先级语义。
 * 派生值在代码拼装、禁止写回 json。注意与 C端 桥派生不同构：S端 页脚版权行
 * = ©年 + 组合名（C端为 ©年 + name），勿混用（landing.spec 断言依赖）。
 */
import brandJson from '../../../../brand/brand.json'

export const brand = {
  name: brandJson.name,
  nameEn: brandJson.nameEn,
  mark: brandJson.mark,
  tagline: brandJson.tagline,
}

/** 组合名：「爱小说 · AI Novel」（name 可被运行时覆盖） */
export function brandFull(): string {
  return `${brand.name} · ${brand.nameEn}`
}

/** S端 页脚版权行：「© 2026 爱小说 · AI Novel」（年份动态取，勿写死） */
export function brandCopyright(): string {
  return `© ${new Date().getFullYear()} ${brandFull()}`
}

/**
 * 应用运行时覆盖（site-config.json 的 brandName 非空才生效；空/缺省回落构建期值）。
 * 返回是否发生了覆盖，供 main.ts bootstrap 决定是否同步改写 document.title。
 * 注意：仅限 main.ts bootstrap 在挂载前调用一次——brand 是普通对象，变异不触发
 * 响应式，挂载后才改不会重渲染。
 */
export function applyBrandOverride(cfg: { brandName?: string }): boolean {
  const name = cfg.brandName?.trim()
  if (name) {
    brand.name = name
    return true
  }
  return false
}
