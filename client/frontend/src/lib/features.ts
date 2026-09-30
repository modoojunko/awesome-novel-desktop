/**
 * 功能 key 词汇表（c-s-entitlement-sync 起语义调整）。
 *
 * 本表是 FeatureKey 的**登记簿**（S端 tiers.entitlement 配置与 C端 门禁点按此
 * 对齐；加 key 先登记 specs），同时在**快照缺失时兜底**：有权益快照时判定权
 * 归快照（useFeature 查 features 数组），本表 memberOnly 不参与判定。
 *
 * 口径不变（2026-08-18）：人工写作能力免费完整可用；AI 能力是会员权益。
 * 入口一律可见（不做 UI 隐藏）；使用由后端 require_ai_access 统一拦截，
 * 403 member_required → 前端弹升级引导。运营判定（免费限 1 本/试用横幅）
 * 不进清单，保留直判（建书上限走快照 limits.max_projects）。
 * 纯 TS，无 DOM 依赖。
 */
export type FeatureKey =
  | "tree-crud"
  | "prose-edit"
  | "version-history"
  | "archive"
  | "volume-chapter-config"
  | "advanced-config-entry"
  | "settings-7-items"
  | "settings-ai-fields"
  | "outline-advanced-fields"
  | "ai-generate"
  | "prompt-panel"
  | "ai-model"
  | "ai-detect";

export const FEATURES: Record<FeatureKey, { memberOnly: boolean }> = {
  // 免费：完整人工写作能力
  "tree-crud": { memberOnly: false },
  "prose-edit": { memberOnly: false },
  "version-history": { memberOnly: false },
  "archive": { memberOnly: false },
  "volume-chapter-config": { memberOnly: false },
  "advanced-config-entry": { memberOnly: false },
  "settings-7-items": { memberOnly: false },
  // 模型配置＝人工路径能力（免费版也能配、配好升级 PRO 后直接用，D4/7.1）
  "ai-model": { memberOnly: false },
  // 会员：AI 能力（入口可见、使用需会员）
  "settings-ai-fields": { memberOnly: true },
  "outline-advanced-fields": { memberOnly: true },
  "ai-generate": { memberOnly: true },
  "prompt-panel": { memberOnly: true },
  // 朱雀 AI 检测：PRO 起发放、试用不含（c-ai-detect-pro-tier；2026-09-30 自 MAX
  // 专属下放——MAX 档未上线前朱雀无人可用，先挂 PRO 验证全链）；快照单源——
  // S端 entitlement 对 pro/max 发放本 key；快照缺失按兜底口径一律未授权（锁定）。
  "ai-detect": { memberOnly: true },
};

/** 是否会员功能（AI 能力）——用于 PRO 标识/升级引导文案，不控制显隐。 */
export function isMemberFeature(key: FeatureKey): boolean {
  return FEATURES[key].memberOnly;
}
