/**
 * C端 品牌桥：仓库根 brand/brand.json 是全仓品牌唯一声明处，本文件是前端侧唯一
 * 读取入口（brand-name-single-source）。派生值在代码拼装、禁止写回 json；
 * 版权行年份动态取——勿写死年份（spec: brand-identity）。
 * 版权行主体（company）是法定名称，不是品牌派生值：与法务页「经营者」、
 * Windows 发布者（build.spec 读同一键）同口径，勿在各组件另写。
 */
import brandJson from "../../../../brand/brand.json";

export const BRAND = {
  name: brandJson.name,
  nameEn: brandJson.nameEn,
  mark: brandJson.mark,
  tagline: brandJson.tagline,
} as const;

/** 组合名：「爱小说 · AI Novel」 */
export const brandFull = `${BRAND.name} · ${BRAND.nameEn}`;

/** 经营主体（版权人/发布者）：「星纬（海口）投资有限公司」 */
export const companyName = brandJson.company;

/** C端版权行：「© 2026 星纬（海口）投资有限公司 · 爱小说」
 *  （S端页脚为 ©年+主体+组合名，两端派生不同构勿混用） */
export const copyrightLine = `© ${new Date().getFullYear()} ${companyName} · ${BRAND.name}`;
