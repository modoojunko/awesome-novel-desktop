/**
 * 伏笔领域常量（前端镜像）—— foreshadow-settings-v2 tasks 1.1/4.2。
 *
 * 唯一事实源在后端 `client/backend/settings/hooks_model.py`；
 * 本文件为其**逐字镜像**（改任何一处必须两端同批——后端 parity 测试锁定，
 * 沿 test_shared_constants_parity 的 characterModel 先例）。
 *
 * 声明式约束：为让后端正则可抽取，保持 `k: "值"` / `label: "值"` 的
 * 字面量形态，不使用模板字符串或计算属性。
 */

// ── 类型词表（9 slug；UI 下拉与 AI 出参归一共用此表）─────────────────────
export interface HookType {
  k: string;
  label: string;
}

export const HOOK_TYPES: HookType[] = [
  { k: "mystery", label: "悬念" },
  { k: "threat", label: "威胁" },
  { k: "promise", label: "承诺" },
  { k: "clue", label: "线索" },
  { k: "relationship", label: "关系伏笔" },
  { k: "power", label: "能力伏笔" },
  { k: "emotion", label: "情绪钩" },
  { k: "choice", label: "选择钩" },
  { k: "desire", label: "渴望钩" },
];

export const HOOK_TYPE_KEYS: string[] = HOOK_TYPES.map((f) => f.k);

// ── 状态词表（单列；「收束」是唯一系统词）────────────────────────────────
// active=进行中·待收束 / resolved=已收束 / abandoned=废弃。
export const HOOK_STATUSES: string[] = ["active", "resolved", "abandoned"];

export type HookStatus = (typeof HOOK_STATUSES)[number];

// ── 长度纪律（同角色族：短段落 300 档）──────────────────────────────────
export const DESCRIPTION_MAX = 300;
export const PAYOFF_NOTE_MAX = 300;

// ── 优先级（存储 Integer 1/2/3；展示/注入统一 高/中/低，映射唯一）────────
export const PRIORITY_LABELS: Record<number, string> = { 1: "高", 2: "中", 3: "低" };

/** priority 混形归一：1/2/3、"1"/"2"/"3"、"high/medium/low"、高/中/低 → Integer。 */
export function normalizePriority(value: unknown): number {
  if (typeof value === "number" && (value === 1 || value === 2 || value === 3)) return value;
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (text === "high") return 1;
    if (text === "medium") return 2;
    if (text === "low") return 3;
    if (text === "1" || text === "2" || text === "3") return Number(text);
    if (value.trim() === "高") return 1;
    if (value.trim() === "中") return 2;
    if (value.trim() === "低") return 3;
  }
  throw new Error(`invalid priority: ${String(value)}`);
}

/** Integer → 高/中/低；非法值返回空串。 */
export function priorityLabel(value: unknown): string {
  try {
    return PRIORITY_LABELS[normalizePriority(value)] ?? "";
  } catch {
    return "";
  }
}

/** slug → 中文标签；未知值原样返回。 */
export function typeLabel(value: string): string {
  return HOOK_TYPES.find((f) => f.k === value)?.label ?? String(value ?? "");
}
