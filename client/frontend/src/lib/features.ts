/**
 * 功能 key 词汇表（tier-plan-four-tiers 起 minTier 语义）。
 *
 * 本表是 FeatureKey 的**登记簿**（S端 tiers.entitlement 配置与 C端 门禁点按此
 * 对齐；加 key 先登记 specs），同时在**快照缺失时兜底**：有权益快照时判定权
 * 归快照（useFeature 查 features 数组），本表 minTier 不参与判定。
 *
 * 口径（2026-10-05 四档拍板）：人工写作能力免费完整可用；AI 能力按档逐层解锁——
 * 标准=AI 管流程（卷规划/拆章/章纲起草/体检/设定域 AI/文风建议），正文自己写；
 * PRO=正文 AI＋朱雀检测（ai-detect 留 PRO，trial 同权）；MAX=剧情推演＋去AI味＋文风蒸馏。
 * 入口一律可见（不做 UI 隐藏）；使用由后端 require_ai_access 统一拦截，
 * 403 member_required（非会员）/ feature_required（会员但档位不够）→ 前端分档引导。
 * 运营判定（免费限 1 本/试用横幅）不进清单，保留直判（建书上限走快照 limits.max_projects）。
 * 纯 TS，无 DOM 依赖。
 */
export type TierKey = "free" | "standard" | "pro" | "max";

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
  | "ai-plan"
  | "chapter-review"
  | "style-suggest"
  | "style-quant"
  | "ai-generate"
  | "prompt-panel"
  | "ai-model"
  | "ai-detect"
  | "ai-plot"
  | "ai-polish";

const TIER_ORDER: Record<TierKey, number> = { free: 0, standard: 1, pro: 2, max: 3 };

export const FEATURES: Record<FeatureKey, { minTier: TierKey }> = {
  // 免费：完整人工写作能力
  "tree-crud": { minTier: "free" },
  "prose-edit": { minTier: "free" },
  "version-history": { minTier: "free" },
  "archive": { minTier: "free" },
  "volume-chapter-config": { minTier: "free" },
  "advanced-config-entry": { minTier: "free" },
  "settings-7-items": { minTier: "free" },
  // 模型配置＝人工路径能力（免费版也能配、配好升级后直接用，D4/7.1）
  "ai-model": { minTier: "free" },
  // 标准：AI 管流程（正文自己写）
  "settings-ai-fields": { minTier: "standard" },
  "outline-advanced-fields": { minTier: "standard" },
  "ai-plan": { minTier: "standard" },
  "chapter-review": { minTier: "standard" },
  "style-suggest": { minTier: "standard" },
  // PRO：正文 AI＋朱雀检测
  "ai-generate": { minTier: "pro" },
  "prompt-panel": { minTier: "pro" },
  // 朱雀 AI 检测：PRO 起发放、trial 同权（2026-10-05 拍板留 PRO——撤销「上收 MAX」
  // 草案）；快照单源——S端 entitlement 对 pro/max 发放本 key；快照缺失按兜底口径
  // 一律未授权（锁定）。
  "ai-detect": { minTier: "pro" },
  // MAX：剧情推演＋去AI味加工＋文风蒸馏
  "ai-plot": { minTier: "max" },
  "ai-polish": { minTier: "max" },
  "style-quant": { minTier: "max" },
};

/** 档位序（供 minTier 比较；free=0 起步） */
export function tierRank(tier: TierKey): number {
  return TIER_ORDER[tier] ?? 0;
}

/** 该 key 的最低可用档（快照缺失时兜底/403 tier_required 推导用） */
export function minTierOf(key: FeatureKey): TierKey {
  return FEATURES[key].minTier;
}

/**
 * 是否会员功能（AI 能力）——兼容派生（生产零调用点、仅测试保留）：
 * minTier 高于 free 即会员功能。用于 PRO 标识/升级引导文案，不控制显隐。
 */
export function isMemberFeature(key: FeatureKey): boolean {
  return tierRank(FEATURES[key].minTier) > 0;
}
