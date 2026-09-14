/**
 * 角色领域常量（前端镜像）—— character-settings-v2 tasks 5.6。
 *
 * 唯一事实源在后端 `client/backend/settings/character_model.py`；
 * 本文件为其**逐字镜像**，由后端 `tests/test_shared_constants_parity.py` 的
 * 正则抽取对拍锁死——改任何一处必须两端同批。
 *
 * 声明式约束：为让后端正则可抽取，保持 `k: "值"` / `label: "值"` 的
 * 字面量形态，不使用模板字符串或计算属性。
 */

// ── 基础档案（8 键；UI 呈 6 行——性别·年龄·种族合一行）──────────────────
export interface CharacterField {
  k: string;
  label: string;
  author_only?: boolean;
  req?: boolean;
}

export const DOSSIER_FIELDS: CharacterField[] = [
  { k: "gender", label: "性别", author_only: true },
  { k: "age", label: "年龄", author_only: true },
  { k: "race", label: "种族", author_only: false },
  { k: "faction", label: "势力 · 身份", author_only: false },
  { k: "look", label: "外貌标签", author_only: false },
  { k: "speech", label: "语言特征", author_only: false },
  { k: "background", label: "背景", author_only: false },
  { k: "plot", label: "剧情定位", author_only: false },
];

export const DOSSIER_KEYS = DOSSIER_FIELDS.map((f) => f.k);
export const DOSSIER_FILL_KEYS = DOSSIER_FIELDS.filter((f) => !f.author_only).map((f) => f.k);

// ── 认知六层（30 格）─────────────────────────────────────────────────────
export interface CogLayer {
  id: string;
  no: string;
  name: string;
  tag: string;
  primary: string;
  fields: CharacterField[];
}

export const COG_LAYERS: CogLayer[] = [
  {
    id: "worldview", no: "01", name: "世界观", tag: "认知层", primary: "w1",
    fields: [
      { k: "w1", label: "世界规则认知度", req: false },
      { k: "w2", label: "局势主观判定", req: false },
      { k: "w3", label: "世界运行规则信仰", req: false },
      { k: "w4", label: "人性通用认知", req: false },
      { k: "w5", label: "核心认知盲区", req: true },
    ],
  },
  {
    id: "self", no: "02", name: "自我观", tag: "认知层", primary: "s1",
    fields: [
      { k: "s1", label: "自我身份定位", req: false },
      { k: "s2", label: "自我价值判定", req: false },
      { k: "s3", label: "深层软肋", req: false },
      { k: "s4", label: "优势与缺陷认知", req: false },
      { k: "s5", label: "宿命认知观", req: false },
    ],
  },
  {
    id: "values", no: "03", name: "价值观", tag: "认知层", primary: "v1",
    fields: [
      { k: "v1", label: "核心追求", req: false },
      { k: "v2", label: "三观底线", req: false },
      { k: "v3", label: "核心价值优先级", req: false },
      { k: "v4", label: "个人善恶判定标准", req: false },
    ],
  },
  {
    id: "power", no: "04", name: "能力", tag: "执行层", primary: "p2",
    fields: [
      { k: "p1", label: "先天天赋", req: false },
      { k: "p2", label: "后天综合能力（金手指）", req: false },
      { k: "p6", label: "技能 · 习得与来源", req: false },
      { k: "p3", label: "能力上限阈值", req: true },
      { k: "p4", label: "能力代价 · 短板", req: true },
      { k: "p5", label: "隐藏底牌后手", req: false },
    ],
  },
  {
    id: "behavior", no: "05", name: "行为", tag: "执行层", primary: "b1",
    fields: [
      { k: "b1", label: "性格 · 待人态度", req: false },
      { k: "b2", label: "行为习惯 · 小动作 · 喜忌", req: false },
      { k: "b3", label: "危机本能行为", req: false },
      { k: "b4", label: "决策思维习惯", req: false },
      { k: "b5", label: "社交表现形态", req: false },
    ],
  },
  {
    id: "env", no: "06", name: "环境", tag: "结果层", primary: "e3",
    fields: [
      { k: "e1", label: "地域与阶级环境", req: false },
      { k: "e2", label: "资源与权限条件", req: false },
      { k: "e3", label: "人际生态环境", req: false },
      { k: "e4", label: "时代局势背景", req: false },
      { k: "e5", label: "关键塑人事件", req: false },
    ],
  },
];

export const COG_KEYS = COG_LAYERS.flatMap((l) => l.fields.map((f) => f.k));
export const COG_REQUIRED = COG_LAYERS.flatMap((l) =>
  l.fields.filter((f) => f.req).map((f) => f.k),
);
export const COG_PRIMARY_KEYS = COG_LAYERS.map((l) => l.primary);
export const COG_FILL_KEYS = [
  ...COG_PRIMARY_KEYS,
  ...COG_REQUIRED.filter((k) => !COG_PRIMARY_KEYS.includes(k)),
  "p6",
];
export const PERSONA_FILL_KEY = "persona";

// ── 写章状态块（后端 WRITE_STATE_KEYS 同源）──────────────────────────────
export const WRITE_STATE_KEYS = COG_PRIMARY_KEYS;
export const WRITE_STATE_PER_CELL_MAX = 40;
export const WRITE_STATE_PER_CHAR_MAX = 120;

// ── 门禁 ─────────────────────────────────────────────────────────────────
export const GATE_FIELDS: [string, string][] = [
  ["name", "角色名称"],
  ["persona", "一句话人设"],
  ["dossier.plot", "剧情定位"],
  ["cog.w5", "核心认知盲区"],
  ["cog.p3", "能力上限"],
  ["cog.p4", "能力代价"],
];
/** 右栏 AI 作用域上下文（SettingsView 拼「当前角色：… 缺 n/m」用） */
export interface CharAiCtx {
  name: string;
  code: string;
  role: string;
  personaGap: number;
  dossierGap: number;
  cogGap: number;
}

/** 未命名哨兵（create/清空名时服务端写入 "\u0000"+uuid 段，唯一键安全） */
export const NAME_PLACEHOLDER_PREFIX = "\u0000";

/** 展示名：哨兵 → 空串（调用方再兜底「未命名」）；真名原样。 */
export function displayName(name: string | null | undefined): string {
  if (!name || name.startsWith(NAME_PLACEHOLDER_PREFIX)) return "";
  return name;
}

export const ROLES = ["主角", "配角", "反派", "路人"] as const;
export type CharacterRole = (typeof ROLES)[number];

// ── 体检四态与项（力量向 / 现实向）───────────────────────────────────────
export const CHAR_CHECK_STATUS = ["ok", "warn", "conflict", "miss"] as const;
export type CharCheckStatus = (typeof CHAR_CHECK_STATUS)[number];

export const CHECK_ITEMS_POWER: [string, string][] = [
  ["简介 × 角色", "dossier:plot"],
  ["题材 × 角色", "layer:behavior"],
  ["世界 × 能力上限", "layer:power"],
  ["世界 × 代价", "layer:power"],
  ["势力 × 角色落地", "panel:world"],
  ["主线 × 角色", "dossier:plot"],
];
export const CHECK_ITEMS_REAL: [string, string][] = [
  ["简介 × 角色", "dossier:plot"],
  ["题材 × 角色", "layer:behavior"],
  ["世界 × 现实规则", "layer:power"],
  ["世界 × 限制", "layer:power"],
  ["势力 × 角色落地", "panel:world"],
  ["主线 × 角色", "dossier:plot"],
];

// ── 关系类型词表 ─────────────────────────────────────────────────────────
export const RELATION_TYPES = [
  "父子", "母女", "兄弟", "姐妹", "血亲",
  "师徒", "同门", "举荐",
  "同盟", "友好", "主仆", "上下级", "竞争", "纵容", "管束",
  "恩情", "亏欠", "敌对", "仇人", "畏惧",
] as const;

// ── 视图辅助（纯前端派生）────────────────────────────────────────────────
export function cardGaps(card: {
  name?: string; persona?: string;
  dossier?: Record<string, string>; cog?: Record<string, string>;
}): string[] {
  const gaps: string[] = [];
  const filled = (v?: string) => !!String(v ?? "").trim();
  if (!filled(card.name)) gaps.push("角色名称");
  if (!filled(card.persona)) gaps.push("一句话人设");
  for (const [path, label] of GATE_FIELDS) {
    if (!path.includes(".")) continue;
    const [bucket, key] = path.split(".") as ["dossier" | "cog", string];
    if (!filled(card[bucket]?.[key])) gaps.push(label);
  }
  return gaps;
}

export function extraGaps(card: {
  dossier?: Record<string, string>;
}): string[] {
  return filled_(card.dossier?.plot) ? [] : ["剧情定位"];
}

function filled_(v?: string): boolean {
  return !!String(v ?? "").trim();
}
