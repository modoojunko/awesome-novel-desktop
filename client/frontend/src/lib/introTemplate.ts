/**
 * 简介六段模板 / 禁忌三元 —— 单一来源（genre-signup-redesign D5/D14）。
 *
 * 用途：简介面板「怎么写」引导、AI 体检行名、prompt 模板占位符共用同一份文案。
 * 后端镜像在 `client/backend/prompts/` 同名常量，二者由 parity 测试对拍
 * （参照 GET /api/genres/candidates 的「后端下发 + 前端镜像」机制）。
 *
 * 注意区分两套「三条」：
 *  - TABOO_RULES（体检扫描规则）：设定集腔 / 作者自白 / 剧透
 *  - DONT_DO（写作引导「别踩」）：设定集腔 / 作者自白 / 写死结局
 * 第三项不同（写死结局 ≠ 剧透），勿合并为同一枚举。
 */

export interface IntroSegment {
  /** 段名（体检行名、prompt 占位符键，逐字一致） */
  name: string;
  /** 成书视角解释：为什么要有这一格 */
  why: string;
  /** 例句（六段同书贯穿） */
  example: string;
}

export const INTRO_SEGMENTS: IntroSegment[] = [
  {
    name: "主角身份",
    why: "有了它，读者三秒知道跟谁走。",
    example: "外门杂徒林拾，在宗门扫了十年落叶。",
  },
  {
    name: "本来的生活",
    why: "先给平静，后面打破它才有劲。",
    example: "熬满十年就出宗，回家守几亩灵田过安稳日子。",
  },
  {
    name: "突发状况",
    why: "变故一出，故事才算开锣。",
    example: "一双能看见修为漏洞的眼，偏在这时睁开了。",
  },
  {
    name: "必须面对的矛盾",
    why: "两头都疼，读者才揪心。",
    example: "用它，会被忌惮他的首座盯上；不用，废他根骨的仇永远报不了。",
  },
  {
    name: "不做的后果",
    why: "把退路写死，读者才信他必须动。",
    example: "三个月后丹田枯竭，仇人坐着的位置越坐越稳。",
  },
  {
    name: "做了的可能结局",
    why: "「可能」二字留悬念。",
    example: "要么踩着漏洞一路捅上去，要么变成所有人都想挖走的那只眼。",
  },
];

/** 六段公式（面板底部展示）。 */
export const INTRO_FORMULA = INTRO_SEGMENTS.map((s) => s.name).join(" + ");

/** AI 体检的禁忌扫描规则（三元的第三项＝剧透）。 */
export const TABOO_RULES = ["设定集腔", "作者自白", "剧透"] as const;

/** 写作引导「别踩」三条（第三项＝写死结局，与 TABOO_RULES 不同）。 */
export const DONT_DO = [
  "写成世界观设定集（没人关心大陆历史）",
  "写成作者自白（\"我构思了三年\"）",
  "最后一格写死结局（\"可能\"＝没写的部分）",
] as const;

/** 简介字数上限（前后端同源）。 */
export const INTRO_MAX_LEN = 500;
