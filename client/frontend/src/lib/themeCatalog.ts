/**
 * 题材目录（大类 + 子类）——题材面板第 01 格「什么题材？」的候选源（前端镜像）。
 *
 * 单一事实源＝后端 `genres/theme_catalog.py`；本文件必须逐字一致
 * （`client/backend/tests/test_shared_constants_parity.py` 对拍），否则作者选中的
 * 题材在后端校验不过（400「未知的题材」）。
 *
 * 存储值即**中文名**（封闭目录，名字即稳定键）；子类必须属于所选大类。
 */

export interface ThemeEntry {
  /** 大类名（存 story.yaml.genre，是书本题材展示名的主来源）。 */
  name: string;
  /** 子类清单（存 story.yaml.sub_genre，可空）。 */
  subTypes: string[];
}

export const THEMES: ThemeEntry[] = [
  {
    name: "都市",
    subTypes: ["都市生活", "都市职场", "商战", "都市情感", "家庭伦理", "市井烟火", "都市群像"],
  },
  { name: "年代文", subTypes: ["民国", "建国初期", "70年代", "80年代", "90年代", "改革开放年代"] },
  { name: "乡土/乡村", subTypes: ["乡村振兴", "乡土人情", "农村家族故事"] },
  { name: "刑侦/现实犯罪", subTypes: ["本格刑侦", "社会派犯罪", "连环案", "罪案人性挖掘"] },
  { name: "校园长篇", subTypes: ["青春成长", "校园群像", "教育困境"] },
  { name: "谍战", subTypes: ["民国谍战", "现代谍战"] },
  { name: "军事", subTypes: ["现代军旅", "古代战争", "战争史诗"] },
  { name: "体育", subTypes: ["足球", "篮球", "赛车", "田径", "乒乓"] },
  { name: "美食", subTypes: ["市井美食", "美食传承", "美食创业"] },
  { name: "正史历史小说", subTypes: ["先秦", "秦汉", "唐宋", "明清历史演义"] },
  { name: "架空古王朝", subTypes: ["权谋", "宫斗", "宅斗", "古言种田"] },
  { name: "穿越历史", subTypes: ["穿真实朝代", "穿虚构王朝（穿越架空古言）"] },
  { name: "仙侠/修真", subTypes: ["古典仙侠", "凡人流", "仙魔大战", "种田修仙"] },
  { name: "玄幻", subTypes: ["东方史诗玄幻", "武魂流", "异兽流", "王朝争霸"] },
  { name: "志怪/民俗灵异", subTypes: ["民俗怪谈", "单元精怪故事"] },
  { name: "西式奇幻", subTypes: ["史诗奇幻", "低魔奇幻", "黑暗奇幻"] },
  { name: "科幻", subTypes: ["硬科幻", "软科幻", "星际", "赛博朋克", "近未来", "时间旅行"] },
  { name: "末世/废土", subTypes: ["丧尸末世", "天灾末世", "核战后废土"] },
  { name: "无限流", subTypes: ["副本闯关", "空间解密"] },
  { name: "游戏文", subTypes: ["网游（虚拟头盔）", "游戏异界"] },
];

/** 某大类的子类清单；未知大类返回空数组。 */
export function subTypesOf(theme: string | null | undefined): string[] {
  return THEMES.find((t) => t.name === theme)?.subTypes ?? [];
}

/** 书本题材展示名：大类 · 子类（子类可空）。 */
export function themeLabel(theme?: string | null, subType?: string | null): string {
  const t = (theme || "").trim();
  const s = (subType || "").trim();
  if (t && s) return `${t} · ${s}`;
  return t || s;
}
