/**
 * 知识库载荷字段的中文标签（c-kb-field-labels）。
 *
 * 机制**通用**：一张「键 → 中文」字典，任何概念（文风/文笔/世界/角色/手法）同一套
 * 查找；同一键在不同概念语义不同时（如 role：角色＝定位、文风＝声音角色）按概念
 * 消歧；字典未收录的键回退原键（不编造）。
 *
 * 角色档案八格与认知十一格**复用角色域唯一事实源** characterModel.ts（后端
 * settings/character_model.py 的逐字镜像），不手抄第二份标签。枚举值（世界分区、
 * 文风槽位、口癖严重度、布尔）同样按字段名给中文，未知值回退原值。
 */
import { COG_LAYERS, DOSSIER_FIELDS } from "./characterModel";

const SHARED_LABELS: Record<string, string> = {
  // 角色设定：卡级字段与知识侧标注（档案/认知格在下方由角色域同源表并入）
  archetype: "名字",
  persona: "一句话人设",
  aliases: "别名",
  role: "定位",
  kind: "小类",
  relation_slot: "关系槽位",
  arc: "成长弧线",
  // 文风 / 文笔
  slot: "槽位",
  text: "内容",
  sample: "示范段",
  sample_note: "示范说明",
  rule: "句法规则",
  craft: "写法",
  banned: "禁用词",
  banned_alt: "替换建议",
  tic_pattern: "口癖模式",
  tic_severity: "口癖严重度",
  // 世界设定
  part: "分区",
  content: "内容",
  hard: "硬约束",
  // 手法
  instruction: "打法",
  negative: "反例",
  scene: "适用场面",
  emotion: "情绪",
  steps: "步骤",
  // 拆书产物跨维度通用键（boss 2026-11-07 定稿：固定骨架＋开放内容）
  name: "名字",
  need: "读者需求",
  how: "怎么写",
  evidence_ch: "章证据",
  confidence: "可信度",
  transferable: "适用范围",
  emotion_chain: "情绪链",
  repro_steps: "复现步骤",
  swappable: "可替换",
  no_copy: "不可抄",
  example: "例证",
  note: "注记",
  // look/speech 由角色域同源表供（外貌标签/语感口音），不在此重复定义
};

/** 字段说明（作家语言一句话）——schema 段 desc 空时的回退单源。
 *  与标签同表维护：标签管「叫什么」，说明管「是什么」。未收录返空串（不渲染）。 */
const FIELD_DESCS: Record<string, string> = {
  archetype: "这个实例叫什么——角色实例就是角色名",
  persona: "一句话立住的形象",
  aliases: "书中被叫过的其他称呼",
  role: "在故事里担任的位置",
  look: "长相与体貌特征",
  speech: "说话的方式与口音习惯",
  background: "来历与身份",
  plot: "在书里走过的事件线",
  need: "这条写法满足读者的什么期待",
  how: "具体怎么写",
  evidence_ch: "出自原书哪几章",
  confidence: "拆书判断的可信程度",
  transferable: "挪到别的书还能不能用",
  emotion_chain: "读者情绪被怎样一步步带着走",
  repro_steps: "照着复现的步骤",
  swappable: "换题材时可以替换的部分",
  no_copy: "不能照抄的原书专属内容",
  example: "原书里的例证",
  note: "补充说明",
};

// 角色档案八格 / 认知十一格：角色域同源标签并入（id 冲突以本表先到为准）
for (const f of DOSSIER_FIELDS) {
  SHARED_LABELS[f.k] ??= f.label;
}
for (const layer of COG_LAYERS) {
  for (const f of layer.fields) {
    SHARED_LABELS[f.k] ??= f.label;
  }
}

/** 概念消歧：同一键在不同概念下语义不同时的覆盖（通用机制的一层数据）。 */
const CONCEPT_LABELS: Record<string, Record<string, string>> = {
  文风: { role: "声音角色" },
};

/** 字段说明（作家语言）：schema 段 desc 空时的回退；未收录返空串。 */
export function kbFieldDesc(key: string): string {
  return FIELD_DESCS[key] ?? "";
}

/** 字段值的中文标签（按字段名查枚举）；布尔一律 是/否；未收录回退原值。 */
const VALUE_LABELS: Record<string, Record<string, string>> = {
  slot: {
    // 文风槽位
    role: "声音角色",
    tone: "语调",
    pov: "视角",
    register: "语域",
    sample: "示范段",
    // 文笔槽位
    rule: "句法规则",
    craft: "写法",
    banned_word: "禁用词",
    tic: "口癖",
  },
  part: {
    // 世界分区
    stage: "世界舞台",
    power: "力量体系",
    cost: "力量的代价",
    factions: "势力",
    history: "历史",
    extra: "更多世界细节",
    constraint: "世界铁律",
  },
  tic_severity: { high: "高", medium: "中", low: "低" },
  confidence: { high: "高", mid: "中", low: "低" },
};

/** payload 键 → 中文标签；未知键回退原键。 */
export function kbFieldLabel(concept: string, key: string): string {
  return CONCEPT_LABELS[concept]?.[key] ?? SHARED_LABELS[key] ?? key;
}

/** payload 值 → 中文展示串（枚举值/布尔转中文）；未知值回退原值。 */
export function kbValueLabel(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string") return VALUE_LABELS[key]?.[value] ?? value;
  return String(value);
}
