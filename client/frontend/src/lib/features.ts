/**
 * 功能 key 词汇表（tier-plan-four-tiers 起 minTier 语义）。
 *
 * 本表是 FeatureKey 的**登记簿**（S端 tiers.entitlement 配置与 C端 门禁点按此
 * 对齐；加 key 先登记 specs），同时在**快照缺失时兜底**：有权益快照时判定权
 * 归快照（useFeature 查 features 数组），本表 minTier 不参与判定。
 *
 * 口径（2026-10-05 四档拍板）：人工写作能力免费完整可用；AI 能力按档逐层解锁——
 * 标准=AI 管流程（卷规划/拆章/章纲起草/体检/设定域 AI/文风建议），正文自己写；
 * PRO=正文 AI＋朱雀检测（ai-detect 留 PRO，trial 同权）；MAX=剧情推演＋文风蒸馏。
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
  | "assistant-execute"
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
  | "assistant-diverge"
  | "image-generate"
  | "deconstruct"
  | "deconstruct-import"
  | "kb-official"
  | "human-taste";

const TIER_ORDER: Record<TierKey, number> = { free: 0, standard: 1, pro: 2, max: 3 };

export const FEATURES: Record<FeatureKey, { minTier: TierKey }> = {
  // 标准（免费）：完整创作流程 + 自己的库 + AI 头脑风暴（读/聊；不生成/不写）
  "tree-crud": { minTier: "free" },
  "prose-edit": { minTier: "free" },
  "version-history": { minTier: "free" },
  "archive": { minTier: "free" },
  "volume-chapter-config": { minTier: "free" },
  "advanced-config-entry": { minTier: "free" },
  "settings-7-items": { minTier: "free" },
  // 模型配置＝基础能力：标准免费也能配，配好升级后直接用
  "ai-model": { minTier: "free" },
  // PRO：AI 写手——规划/章纲/正文/执行
  "settings-ai-fields": { minTier: "pro" },
  "assistant-execute": { minTier: "pro" },
  "outline-advanced-fields": { minTier: "pro" },
  "ai-plan": { minTier: "pro" },
  "chapter-review": { minTier: "pro" },
  "style-suggest": { minTier: "pro" },
  "ai-generate": { minTier: "pro" },
  "prompt-panel": { minTier: "pro" },
  "ai-detect": { minTier: "pro" },
  "deconstruct": { minTier: "pro" },
  // 官方写作知识库（官方层）；本地库不挂 key，标准免费
  "kb-official": { minTier: "pro" },
  // MAX：写作秘书——质量/图像/建书/效率/放手
  "image-generate": { minTier: "max" },
  "human-taste": { minTier: "max" },
  "ai-plot": { minTier: "max" },
  "assistant-diverge": { minTier: "max" },
  "style-quant": { minTier: "max" },
  "deconstruct-import": { minTier: "max" },
};

/** 档位序（供 minTier 比较；free=0 起步） */
export function tierRank(tier: TierKey): number {
  return TIER_ORDER[tier] ?? 0;
}

/** 该 key 的最低可用档（快照缺失时兜底/403 tier_required 推导用） */
export function minTierOf(key: FeatureKey): TierKey {
  return FEATURES[key].minTier;
}

/** 档位短名（徽标/角标用；档位名唯一来源，升级弹窗/门槛徽标等都取这里） */
export function tierLabel(tier: TierKey): string {
  return { free: "标准", standard: "标准会员（旧）", pro: "PRO", max: "MAX" }[tier];
}

/** 升级引导短文案（按 key 最低档单源）：锁定行/-toast/徽标统一出口用。 */
export function upgradeHintOf(key: FeatureKey): string {
  const t = FEATURES[key].minTier;
  if (t === "standard") return "标准会员（旧）专属";
  return `${tierLabel(t)} 专属`;
}

/**
 * 是否会员功能（AI 能力）——兼容派生（生产零调用点、仅测试保留）：
 * minTier 高于 free 即会员功能。用于 PRO 标识/升级引导文案，不控制显隐。
 */
export function isMemberFeature(key: FeatureKey): boolean {
  return tierRank(FEATURES[key].minTier) > 0;
}
