/**
 * 四档套餐文案单源（评审 P2 采纳项）：landing PricingSection 与收银台 CashierPage
 * 共用同一份兜底卖点与定位语，改口径只改这里，防两处漂移。
 * 目录 tiers.selling_points 非空时以目录为准（运营可改库覆盖）；本表是空数组时的保底。
 * 口径（2026-10-05 拍板）：免费=全流程人工+归档 AI；标准=AI 管流程+设定域 AI+正文自己写；
 * PRO=正文 AI 生成+朱雀检测；MAX=剧情推演+去AI味+文风蒸馏+拆书+人工客服+内测。
 */
export const TIER_FALLBACK_FEATS: Record<string, string[]> = {
  free: ['写作全流程免费（人工）', '归档记账 AI（唯一 AI，自配 Key）', '本地作品永久保留'],
  standard: ['AI 分卷规划＋拆章三方向', '章纲 AI 起草三选一', '设定域 AI 全家＋人物盘点', '卷体检＋单章评估＋文风建议', '正文自己写'],
  pro: [
    '含标准全部功能',
    '正文 AI 全家：整章生成，逐行采纳',
    '卷纲冲突检测：偏离卷目标当场报',
    '朱雀 AI 味检测（自配腾讯 Key）',
    '提示词页签：写作提示词自己调',
  ],
  max: ['含 PRO 全部功能', '剧情推演', 'AI 去AI味', '文风蒸馏', '拆书成设定（即将上线）', '人工客服＋新版内测'],
}

/** 各档定位语（明细页同口径） */
export const TIER_POS: Record<string, string> = {
  free: '全流程亲手写，AI 替你记账',
  standard: 'AI 当军师，正文自己写',
  pro: 'AI 当枪手，写完即查',
  max: 'AI 替你打磨，人工兜底',
}

/** 预告卡按档位写实质内容（不写空话） */
export const TIER_SOON_NOTES: Record<string, string> = {
  standard: 'AI 分卷规划 · 章纲起草三选一 · 设定域 AI 全家 · 卷体检与文风建议。上线后此处即可选购。',
  max: '剧情推演 · AI 去AI味 · 文风蒸馏 · 拆书成设定 · 人工客服与新版内测。上线后此处即可选购。',
}
