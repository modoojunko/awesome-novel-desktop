"""人味基线（c-renwei-check D2）：19 项指标的判据、真人分布与权重，冻结常量表。

来源：
- 判据（达标线）与分级：《可量化标准总表 2026-10-10》
- 真人分布（mean±SD 与 P25/P50/P75）：《人类样本指标参考_320章 2026-10-10》
  （拆文库 8 本 × 40 章 = 320 章实测）
- 人味率权重与映射：《人味率算法与纠正指南 2026-10-10》§1.1/§1.2

口径约定（与原型/设计说明一致，实现期以作者资产包 `_人味指纹.py` 复核）：
- 句号/省略号/句长族按「叙述文本」计（剥对白跨度）——真人基线「句号 12.4/千字」与
  「对话行 29.3%」只有在叙述口径下同时成立；问号/叹号按全文计（对白承载）。
- MTLD / Hapax 需 ≥2000 字样本（因子长度 60-100 字，短样本必失真），不足出「样本不足」。
- 人味率＝Σ(权重 × 100·exp(−z²/6)) / Σ权重；只对长度/题材无关的 15 项计分，
  缺失项重归一（不按 0 计入）。
"""

# 指标契约：key / 展示名 / 达标线 / 真人 mean / 真人 sd / P25 / P50 / P75 / 权重
# 权重 0＝仅观察不计分（长度/题材敏感项）。
# kind：cap＝上限型（越低越好）/ floor＝下限型（越高越好）/ ref＝仅参考。
METRICS = [
    # ── 标点层（叙述文本口径；zq：period/ellipsis/问/叹） ──
    {"key": "period_k", "label": "句号 / 千字", "target": "≤ 24", "mean": 12.4, "sd": 5.2,
         "p25": 9.1, "p50": 11.6, "p75": 14.7, "weight": 3, "kind": "cap"},
    {"key": "ellipsis_k", "label": "省略号 / 千字", "target": "≥ 2", "mean": 17.3, "sd": 12.9,
         "p25": 6.9, "p50": 16.2, "p75": 25.9, "weight": 2, "kind": "floor"},
    {"key": "q_k", "label": "问号 / 千字", "target": "3.0 – 6.5", "mean": 4.5, "sd": 1.8,
         "p25": 3.1, "p50": 4.3, "p75": 5.6, "weight": 1, "kind": "floor"},
    {"key": "excl_k", "label": "叹号 / 千字", "target": "≤ 2", "mean": 2.9, "sd": 2.9,
         "p25": 1.2, "p50": 2.2, "p75": 3.7, "weight": 1, "kind": "cap"},
    {"key": "gap_mean", "label": "标点间距均值（字）", "target": "参考", "mean": 8.9, "sd": 1.2,
         "p25": 8.0, "p50": 8.9, "p75": 9.8, "weight": 1, "kind": "ref"},
    {"key": "gap_skew", "label": "标点间距偏度", "target": "≤ 1.5", "mean": 0.63, "sd": 0.34,
         "p25": 0.40, "p50": 0.57, "p75": 0.77, "weight": 2, "kind": "cap"},
    # ── 句段层 ──
    {"key": "short_para", "label": "极短段占比", "target": "15% – 40%", "mean": 24.4, "sd": 8.6,
         "p25": 18.6, "p50": 23.6, "p75": 30.4, "weight": 3, "kind": "ref"},
    {"key": "dialogue", "label": "对话行占比", "target": "≥ 15%", "mean": 29.3, "sd": 12.5,
         "p25": 19.6, "p50": 29.5, "p75": 38.3, "weight": 2, "kind": "floor"},
    {"key": "avg_sent", "label": "平均句长（字）", "target": "参考", "mean": 29.6, "sd": 9.7,
         "p25": 23.2, "p50": 27.9, "p75": 34.1, "weight": 1, "kind": "ref"},
    {"key": "sent_sd", "label": "句长 SD", "target": "参考", "mean": 29.1, "sd": 8.2,
         "p25": 23.5, "p50": 27.9, "p75": 32.9, "weight": 1, "kind": "ref"},
    {"key": "run_len", "label": "句长趋同连串", "target": "0 处", "mean": 0.42, "sd": 0.51,
         "p25": 0.0, "p50": 0.33, "p75": 0.64, "weight": 3, "kind": "cap"},
    {"key": "long_sent", "label": "单句 > 60 字", "target": "0 处", "mean": None, "sd": None,
         "p25": None, "p50": None, "p75": None, "weight": 0, "kind": "cap"},
    # ── 词汇层 ──
    {"key": "mtld", "label": "MTLD 词汇丰富度", "target": "≥ 60", "mean": 73.8, "sd": 10.0,
         "p25": 66.8, "p50": 73.2, "p75": 80.3, "weight": 2, "kind": "floor"},
    {"key": "hapax", "label": "Hapax 率（只出现一次的字）", "target": "≥ 42%", "mean": 45.2, "sd": 2.6,
         "p25": 43.4, "p50": 45.2, "p75": 47.0, "weight": 0, "kind": "floor"},
    {"key": "func_k", "label": "虚词 / 千字", "target": "≥ 195", "mean": 208.0, "sd": 14.0,
         "p25": 199.0, "p50": 210.0, "p75": 219.0, "weight": 3, "kind": "floor"},
    {"key": "abstract_k", "label": "抽象名词 / 千字", "target": "≤ 4", "mean": 1.9, "sd": 1.2,
         "p25": 1.0, "p50": 1.8, "p75": 2.6, "weight": 2, "kind": "cap"},
    # ── 内容层（题材/长度敏感，仅观察） ──
    {"key": "concrete_k", "label": "具体名词 / 千字", "target": "≥ 8", "mean": 17.2, "sd": 5.7,
         "p25": 12.9, "p50": 17.0, "p75": 21.1, "weight": 0, "kind": "floor"},
    {"key": "trans_k", "label": "转场词 / 千字", "target": "≤ 5", "mean": 3.0, "sd": 1.6,
         "p25": 1.8, "p50": 2.9, "p75": 4.2, "weight": 0, "kind": "cap"},
    {"key": "senses", "label": "感官覆盖类数", "target": "≥ 4 类", "mean": 4.6, "sd": 0.6,
         "p25": 4.0, "p50": 5.0, "p75": 5.0, "weight": 0, "kind": "floor"},
]

METRIC_BY_KEY = {m["key"]: m for m in METRICS}

# 人味率判读（《人味率算法与纠正指南》§1.3）
RATE_BANDS = (
    (70.0, "很像人", "ok"),
    (55.0, "边缘", "warn"),
    (40.0, "偏机器", "warn"),
    (0.0, "机器味重", "err"),
)

MIN_RATE_CHARS = 1500     # 短于此时不出人味率（「打不了分」）
MIN_MTLD_CHARS = 2000     # MTLD/Hapax 收敛门槛
Z_CAP = 3.0               # 人味率单项 |z| 截断（防单指标爆表拖歪总分）
