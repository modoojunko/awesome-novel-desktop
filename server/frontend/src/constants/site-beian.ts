/**
 * 备案信息单一事实源：双层来源、字段级优先级——
 *   运行时 site-config.json（applyBeianOverride）> 构建期环境变量注入（GitHub
 *   Secrets → 内联展开）> 空（整条隐藏）。仓库内 site-config.json 允许承载
 *   真实号码（备案号为法定公开信息）；换号优先只换该 JSON 文件重新上传（免重建），
 *   走 secret 重新发布依然有效（兜底层）。
 * 省份口径由运维填入对应格式号码承担（广东主体备案「粤ICP备×号」/ 其他省服务备案号）。
 */
const icp = String(import.meta.env.VITE_BEIAN_ICP ?? '').trim()
const police = String(import.meta.env.VITE_BEIAN_POLICE ?? '').trim()
const policeLink = String(import.meta.env.VITE_BEIAN_POLICE_LINK ?? '').trim()

export const siteBeian = {
  icp,
  police,
  miitUrl: 'https://beian.miit.gov.cn/',
  policeUrl: '',
}

// 公安备案查询页：未显式配置链接时按编号中的数字串拼默认查询地址
function policeQueryUrl(no: string, link: string): string {
  return link || (no ? `https://beian.mps.gov.cn/#/query/webSearch?code=${no.replace(/\D/g, '')}` : '')
}
siteBeian.policeUrl = policeQueryUrl(police, policeLink)

/**
 * 应用运行时覆盖（site-config.json 非空字段才生效；空/缺省回落构建期值）。
 * 注意：仅限 main.ts bootstrap 在挂载前调用一次：siteBeian 是普通对象，变异不触发
 * 响应式，挂载后才改不会重渲染。
 */
export function applyBeianOverride(cfg: { beianIcp?: string; beianPolice?: string; beianPoliceLink?: string }): void {
  if (cfg.beianIcp) siteBeian.icp = cfg.beianIcp
  if (cfg.beianPolice) siteBeian.police = cfg.beianPolice
  siteBeian.policeUrl = policeQueryUrl(siteBeian.police, cfg.beianPoliceLink || policeLink)
}

export function hasBeianInfo(): boolean {
  return Boolean(siteBeian.icp || siteBeian.police)
}
