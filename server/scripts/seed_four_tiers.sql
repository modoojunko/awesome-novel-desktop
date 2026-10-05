-- ═══ 四档套餐数据种子（tier-plan-four-tiers B2.4/B2.5）═══
-- 幂等（ON CONFLICT DO UPDATE/NOTHING）；生产应用走 MCP 带外（pg_gate 复核），
-- 应用前先 SELECT 核对现有 rank/sort（架构评估未核实项）。
-- B2 期：standard/max 保持 planned、SKU on_sale=false（预告卡态，不可购）。
-- 开卖日（B4）：standard/max tiers.status→live + skus.on_sale=true（先 SKU 后 status）。

-- ── tiers：standard 插行（rank=15；权益=v2 默认表 standard 行；device_limit=1）──
INSERT INTO tiers (key, display_name, rank, selling_points, entitlement, status, device_limit, duration_days)
VALUES (
  'standard', '标准', 15,
  '["AI 分卷规划＋拆章三方向","章纲 AI 起草三选一","设定域 AI 全家＋人物盘点","卷体检＋单章评估＋文风建议","正文自己写"]',
  '{"features":["ai-plan","chapter-review","settings-ai-fields","style-suggest","outline-advanced-fields","ai-model"],"limits":{"max_projects":3}}',
  'planned', 1, 0
)
ON CONFLICT (key) DO UPDATE SET
  rank = EXCLUDED.rank,
  selling_points = EXCLUDED.selling_points,
  entitlement = EXCLUDED.entitlement,
  device_limit = EXCLUDED.device_limit;

-- ── tiers：max 行 entitlement 补 MAX 件（若已存在 planned 行）；未建行则插 ──
INSERT INTO tiers (key, display_name, rank, selling_points, entitlement, status, device_limit, duration_days)
VALUES (
  'max', 'MAX', 30,
  '["含 PRO 全部功能","剧情推演","AI 去AI味","文风蒸馏","拆书成设定（即将上线）","人工客服＋新版内测"]',
  '{"features":["ai-plan","chapter-review","settings-ai-fields","style-suggest","outline-advanced-fields","ai-model","ai-generate","prompt-panel","ai-detect","ai-plot","ai-polish","style-quant"],"limits":{"max_projects":null}}',
  'planned', 10, 0
)
ON CONFLICT (key) DO UPDATE SET
  entitlement = EXCLUDED.entitlement,
  selling_points = EXCLUDED.selling_points,
  device_limit = EXCLUDED.device_limit;

-- ── tiers：基线行存在性保证（缺行=免费/试用塌 none，评审 P0）——INSERT ON CONFLICT ──
INSERT INTO tiers (key, display_name, rank, status, device_limit, duration_days)
VALUES ('free', '免费', 5, 'live', 1, 0)
ON CONFLICT (key) DO UPDATE SET rank = EXCLUDED.rank, device_limit = EXCLUDED.device_limit;

INSERT INTO tiers (key, display_name, rank, entitlement, status, device_limit, duration_days)
VALUES (
  'trial', '试用', 10,
  '{"features":["ai-plan","chapter-review","settings-ai-fields","style-suggest","outline-advanced-fields","ai-model","ai-generate","prompt-panel","ai-detect"],"limits":{"max_projects":null}}',
  'live', 1, 7
)
ON CONFLICT (key) DO UPDATE SET
  rank = EXCLUDED.rank,
  entitlement = EXCLUDED.entitlement,
  device_limit = EXCLUDED.device_limit,
  duration_days = EXCLUDED.duration_days;

INSERT INTO tiers (key, display_name, rank, selling_points, entitlement, status, device_limit, duration_days)
VALUES (
  'pro', 'PRO', 20,
  '["含标准全部功能","正文 AI 全家：整章生成，逐行采纳","卷纲冲突检测：偏离卷目标当场报","朱雀 AI 味检测（自配腾讯 Key）","提示词页签：写作提示词自己调"]',
  '{"features":["ai-plan","chapter-review","settings-ai-fields","style-suggest","outline-advanced-fields","ai-model","ai-generate","prompt-panel","ai-detect"],"limits":{"max_projects":null}}',
  'live', 3, 0
)
ON CONFLICT (key) DO UPDATE SET
  rank = EXCLUDED.rank,
  selling_points = EXCLUDED.selling_points,
  entitlement = EXCLUDED.entitlement,
  device_limit = EXCLUDED.device_limit;

-- ── tiers：按档固定设备数核对（free/standard/trial=1，pro=3，max=10）；trial 时长 7 ──
UPDATE tiers SET device_limit = 1 WHERE key IN ('free', 'standard', 'trial');
UPDATE tiers SET device_limit = 3 WHERE key = 'pro';
UPDATE tiers SET duration_days = 7 WHERE key = 'trial';

-- ── skus：月付三行（B2 期 on_sale=false；B4 上架）──
-- sort 排 pro 现有行（1/2/3）之后：popular_sku 取第一个年付 SKU，sort 撞序会静默换档。
INSERT INTO skus (sku_key, tier_id, period, period_days, base_price_fen, discount_permille, device_limit, on_sale, sort)
SELECT 'standard_monthly', t.id, 'monthly', 30, 2990, 1000, 1, false, 4
FROM tiers t WHERE t.key = 'standard'
ON CONFLICT (sku_key) DO UPDATE SET base_price_fen = 2990, device_limit = 1, sort = 4;

INSERT INTO skus (sku_key, tier_id, period, period_days, base_price_fen, discount_permille, device_limit, on_sale, sort)
SELECT 'pro_monthly', t.id, 'monthly', 30, 5990, 1000, 3, false, 5
FROM tiers t WHERE t.key = 'pro'
ON CONFLICT (sku_key) DO UPDATE SET base_price_fen = 5990, device_limit = 3, sort = 5;

INSERT INTO skus (sku_key, tier_id, period, period_days, base_price_fen, discount_permille, device_limit, on_sale, sort)
SELECT 'max_monthly', t.id, 'monthly', 30, 8990, 1000, 10, false, 6
FROM tiers t WHERE t.key = 'max'
ON CONFLICT (sku_key) DO UPDATE SET base_price_fen = 8990, device_limit = 10, sort = 6;

-- ── skus：PRO 现存行按档固定（年卡 device_limit 5→3）──
UPDATE skus SET device_limit = 3 WHERE sku_key IN ('pro_yearly', 'pro_quarterly', 'pro_monthly');

-- ── 运维注记 ──
-- ① pro 设备限额 5→3 在本脚本应用后即时生效于存量 pro 付费用户（60s TTL 内），
--    非 B4 开卖日才生效；超限设备在下一轮校验时失活。回滚须回写 device_limit=5。
-- ② 本迁移对应的 alembic revision=c9d0e1f2a3b4：MCP 带外应用 DDL 后 MUST
--    alembic stamp c9d0e1f2a3b4，否则再跑 upgrade 会 duplicate column。
-- ③ 应用前必核：SELECT key, rank, status FROM tiers ORDER BY rank;（基线行存在性
--    已由本脚本 INSERT ON CONFLICT 保证，但仍须目检 rank 无冲突）。

-- ── 目检 ──
-- SELECT key, rank, status, device_limit, duration_days FROM tiers ORDER BY rank;
-- SELECT sku_key, tier_id, period, base_price_fen, device_limit, on_sale, sort FROM skus ORDER BY sort;
-- 确认：popular 仍为 pro_yearly（应用层取第一个年付 SKU，standard/max 月付行不影响）
