"""角色领域单源（character-settings-v2 tasks 2.2）。

格名、项名、白名单、状态枚举的唯一事实源——提示词由这里渲染（模板不手抄格名），
前端留镜像副本 `src/lib/characterModel.ts` + parity 测试锁逐字一致
（照 tests/test_shared_constants_parity.py 的正则抽取手法）。

分层与 settings/world_model.py 同族：纯常量 + 纯函数，零 IO。
"""

from __future__ import annotations

import hashlib
import json

# ── 基础档案（8 键；UI 呈 6 行——性别·年龄·种族合一行）───────────────────
# author_only=True 的键永不进 AI 候选（gender/age 永不代填）
DOSSIER_FIELDS: list[dict] = [
    {"k": "gender", "label": "性别", "author_only": True},
    {"k": "age", "label": "年龄", "author_only": True},
    {"k": "race", "label": "种族", "author_only": False},
    {"k": "faction", "label": "势力 · 身份", "author_only": False},
    {"k": "look", "label": "外貌标签", "author_only": False},
    {"k": "speech", "label": "语言特征", "author_only": False},
    {"k": "background", "label": "背景", "author_only": False},
    {"k": "plot", "label": "剧情定位", "author_only": False},
]
DOSSIER_KEYS = tuple(f["k"] for f in DOSSIER_FIELDS)
DOSSIER_FILL_KEYS = tuple(f["k"] for f in DOSSIER_FIELDS if not f["author_only"])

# ── 认知六层（30 格；层主格 primary 供写章状态块与层头预览）────────────────
COG_LAYERS: list[dict] = [
    {
        "id": "worldview", "no": "01", "name": "世界观", "tag": "认知层",
        "primary": "w1",
        "fields": [
            {"k": "w1", "label": "世界规则认知度", "req": False},
            {"k": "w2", "label": "局势主观判定", "req": False},
            {"k": "w3", "label": "世界运行规则信仰", "req": False},
            {"k": "w4", "label": "人性通用认知", "req": False},
            {"k": "w5", "label": "核心认知盲区", "req": True},
        ],
    },
    {
        "id": "self", "no": "02", "name": "自我观", "tag": "认知层",
        "primary": "s1",
        "fields": [
            {"k": "s1", "label": "自我身份定位", "req": False},
            {"k": "s2", "label": "自我价值判定", "req": False},
            {"k": "s3", "label": "深层软肋", "req": False},
            {"k": "s4", "label": "优势与缺陷认知", "req": False},
            {"k": "s5", "label": "宿命认知观", "req": False},
        ],
    },
    {
        "id": "values", "no": "03", "name": "价值观", "tag": "认知层",
        "primary": "v1",
        "fields": [
            {"k": "v1", "label": "核心追求", "req": False},
            {"k": "v2", "label": "三观底线", "req": False},
            {"k": "v3", "label": "核心价值优先级", "req": False},
            {"k": "v4", "label": "个人善恶判定标准", "req": False},
        ],
    },
    {
        "id": "power", "no": "04", "name": "能力", "tag": "执行层",
        "primary": "p2",
        "fields": [
            {"k": "p1", "label": "先天天赋", "req": False},
            {"k": "p2", "label": "后天综合能力（金手指）", "req": False},
            {"k": "p6", "label": "技能 · 习得与来源", "req": False},
            {"k": "p3", "label": "能力上限阈值", "req": True},
            {"k": "p4", "label": "能力代价 · 短板", "req": True},
            {"k": "p5", "label": "隐藏底牌后手", "req": False},
        ],
    },
    {
        "id": "behavior", "no": "05", "name": "行为", "tag": "执行层",
        "primary": "b1",
        "fields": [
            {"k": "b1", "label": "性格 · 待人态度", "req": False},
            {"k": "b2", "label": "行为习惯 · 小动作 · 喜忌", "req": False},
            {"k": "b3", "label": "危机本能行为", "req": False},
            {"k": "b4", "label": "决策思维习惯", "req": False},
            {"k": "b5", "label": "社交表现形态", "req": False},
        ],
    },
    {
        "id": "env", "no": "06", "name": "环境", "tag": "结果层",
        "primary": "e3",
        "fields": [
            {"k": "e1", "label": "地域与阶级环境", "req": False},
            {"k": "e2", "label": "资源与权限条件", "req": False},
            {"k": "e3", "label": "人际生态环境", "req": False},
            {"k": "e4", "label": "时代局势背景", "req": False},
            {"k": "e5", "label": "关键塑人事件", "req": False},
        ],
    },
]

# 全部认知格键（冻结；新增格位=在此追加，JSON 列不需迁移）
COG_KEYS: tuple[str, ...] = tuple(
    f["k"] for layer in COG_LAYERS for f in layer["fields"]
)
COG_REQUIRED: tuple[str, ...] = tuple(
    f["k"] for layer in COG_LAYERS for f in layer["fields"] if f["req"]
)
COG_PRIMARY_KEYS: tuple[str, ...] = tuple(layer["primary"] for layer in COG_LAYERS)

# ── AI 补全键清单 ─────────────────────────────────────────────────────────
# 人设是唯一"覆盖型"（act=replace），单独一键
PERSONA_FILL_KEY = "persona"
# 认知补充 = 层主格 6 + 必填 3 + 技能 p6（设计稿的 10 格）
COG_FILL_KEYS = tuple(COG_PRIMARY_KEYS) + tuple(
    k for k in COG_REQUIRED if k not in COG_PRIMARY_KEYS
) + ("p6",)

# ── 写章「角色初始状态」块的供给键（tasks 2.8）────────────────────────────
# 六层主格 + dossier.speech；格序固定、每格 ≤40 字、每人 ≤120 字、块 ≤5 人
WRITE_STATE_KEYS: tuple[str, ...] = tuple(COG_PRIMARY_KEYS)
WRITE_STATE_PER_CELL_MAX = 40
WRITE_STATE_PER_CHAR_MAX = 120
WRITE_STATE_BLOCK_MAX_CHARS = 5

# ── 确认门禁（两档；readiness 与确认共用同一判据）────────────────────────
GATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("name", "角色名称"),
    ("persona", "一句话人设"),
    ("dossier.plot", "剧情定位"),
    ("cog.w5", "核心认知盲区"),
    ("cog.p3", "能力上限"),
    ("cog.p4", "能力代价"),
)
FIRST_CONFIRM_REQUIRED = ("name", "persona")

ROLES = ("主角", "配角", "反派", "路人")

# ── 人物关系类型词表（亲缘/师承/立场/恩怨）────────────────────────────────
RELATION_TYPES: tuple[str, ...] = (
    "父子", "母女", "兄弟", "姐妹", "血亲",
    "师徒", "同门", "举荐",
    "同盟", "友好", "主仆", "上下级", "竞争", "纵容", "管束",
    "恩情", "亏欠", "敌对", "仇人", "畏惧",
)

# ── 一致性体检：四态 + 项表（力量向 / 现实向两套；项名与 goto 由服务端出）──
CHAR_CHECK_STATUS = ("ok", "warn", "conflict", "miss")
# 冲突：绝不扩世界页的 _CHECK_STATUS（("ok","warn","miss")）——否则 world_check
# 会接受并下发 conflict，世界前端只认三态，把「矛盾」静默渲染成「缺失」。

_CHECK_ITEMS_POWER: tuple[tuple[str, str], ...] = (
    # (项名, goto)；goto 为不透明串，前端只做映射（layer:* 开合认知层，dossier:* 聚焦档案格）
    ("简介 × 角色", "dossier:plot"),
    ("题材 × 角色", "layer:behavior"),
    ("世界 × 能力上限", "layer:power"),
    ("世界 × 代价", "layer:power"),
    ("势力 × 角色落地", "panel:world"),
    ("主线 × 角色", "dossier:plot"),
)
_CHECK_ITEMS_REAL: tuple[tuple[str, str], ...] = (
    ("简介 × 角色", "dossier:plot"),
    ("题材 × 角色", "layer:behavior"),
    ("世界 × 现实规则", "layer:power"),
    ("世界 × 限制", "layer:power"),
    ("势力 × 角色落地", "panel:world"),
    ("主线 × 角色", "dossier:plot"),
)
_CHECK_GOTO_ALLOWED_PREFIXES = ("layer:", "dossier:", "panel:")

CHECK_NOTE_MAX = 120


def check_items(has_power: bool) -> tuple[tuple[str, str], ...]:
    """按书的形态给体检项（现实向书没有力量体系，项名随之切换）。"""
    return _CHECK_ITEMS_POWER if has_power else _CHECK_ITEMS_REAL


# ── 纯函数：判据与指纹 ────────────────────────────────────────────────────


def _filled(v) -> bool:
    return bool(str(v or "").strip())


def _read_path(card: dict, path: str):
    cur = card
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def card_gaps(card: dict) -> list[str]:
    """单卡缺口（六项）。路人卡只要剧情定位（门禁豁免在 gate 层做）。"""
    gaps: list[str] = []
    if not _filled(card.get("name")):
        gaps.append("角色名称")
    if not _filled(card.get("persona")):
        gaps.append("一句话人设")
    dossier = card.get("dossier") or {}
    cog = card.get("cog") or {}
    for path, label in GATE_FIELDS:
        if path.startswith("dossier."):
            if not _filled(dossier.get(path.split(".", 1)[1])):
                gaps.append(label)
        elif path.startswith("cog."):
            if not _filled(cog.get(path.split(".", 1)[1])):
                gaps.append(label)
    return gaps


def character_gate(card: dict) -> dict:
    """门禁判据（两档共用此纯函数）：ok / no_protagonist / missing。

    两档由「是否已确认过」决定（见 spec：首次确认只查主角卡完整）。
    本函数实现"此后确认"的完整档；首次档由调用方传 first=True。
    """
    if not _filled(card.get("name")) and not card.get("role") == "主角":
        return {"ok": False, "no_protagonist": True, "missing": []}
    if card.get("role") != "主角":
        return {"ok": True, "no_protagonist": False, "missing": []}
    gaps = [
        label for path, label in GATE_FIELDS
        if not _filled(_read_path(card, path))
    ]
    return {"ok": not gaps, "no_protagonist": False, "missing": gaps}


def book_characters_gate(cards: list[dict], first: bool = False) -> dict:
    """整本书的角色门禁：主角 + 每个非路人卡六项；路人只要剧情定位。

    first=True（该项从未确认过）：只查主角卡名称与人设。
    """
    prots = [c for c in cards if c.get("role") == "主角"]
    if not prots:
        return {"ok": False, "no_protagonist": True, "missing": []}
    missing: list[dict] = []
    prot = prots[0]
    if first:
        req = FIRST_CONFIRM_REQUIRED
        gaps = [
            label for key, label in (
                ("name", "角色名称"), ("persona", "一句话人设"),
            ) if key in req and not _filled(prot.get(key))
        ]
        if gaps:
            missing.append({"name": prot.get("name") or "未命名", "fields": gaps})
    else:
        for card in cards:
            role = card.get("role")
            if role == "路人":
                if not _filled((card.get("dossier") or {}).get("plot")):
                    missing.append({
                        "name": card.get("name") or "未命名",
                        "fields": ["剧情定位"],
                    })
                continue
            gaps = [
                label for path, label in GATE_FIELDS
                if not _filled(_read_path(card, path))
            ]
            if gaps:
                missing.append({"name": card.get("name") or "未命名", "fields": gaps})
    return {"ok": not missing, "no_protagonist": False, "missing": missing}


def gate_fingerprint(cards: list[dict]) -> str:
    """确认时的门禁相关性摘要：非路人卡的六项按 id(seq) 排序拼接后 sha256[:16]。

    只进门禁字段——改外貌这类非门禁格不进位（避免误打回）。
    """
    parts: list[str] = []
    for card in sorted(cards, key=lambda c: str(c.get("seq", 0))):
        if card.get("role") == "路人":
            continue
        values = [
            str(_read_path(card, path) or "") for path, _label in GATE_FIELDS
        ]
        parts.append("|".join(values))
    return hashlib.sha256("\u0001".join(parts).encode("utf-8")).hexdigest()[:16]


# ── 纯函数：AI 草稿的域归一 ───────────────────────────────────────────────


def compute_targets(dossier: dict, cog: dict, persona: str, target: str) -> list[str]:
    """空格清单（服务端此刻的空值是唯一基准；gender/age 永不进候选）。"""
    if target == "persona":
        return [] if _filled(persona) else [PERSONA_FILL_KEY]
    if target == "dossier":
        return [
            k for k in DOSSIER_FILL_KEYS if not _filled((dossier or {}).get(k))
        ]
    if target == "cog":
        return [k for k in COG_FILL_KEYS if not _filled((cog or {}).get(k))]
    raise ValueError(f"unknown target: {target}")


def apply_character_fills(card: dict, target: str, fills: dict) -> tuple[dict, list[dict], list[dict]]:
    """把模型稿写进卡（域层纯函数）：逐格 best-effort，非空拒写。

    返回 (新卡, applied[], skipped[])；skipped.reason ∈ already_filled / out_of_scope /
    unknown_key / author_only。人设（persona）由调用方走覆盖路径，不经本函数。
    """
    card = json.loads(json.dumps(card, ensure_ascii=False))  # 深拷贝
    applied: list[dict] = []
    skipped: list[dict] = []
    allowed = set(DOSSIER_FILL_KEYS if target == "dossier" else COG_FILL_KEYS)
    bucket = card.setdefault(target, {})
    for key, value in (fills or {}).items():
        if target == "dossier" and key in ("gender", "age"):
            skipped.append({"key": key, "reason": "author_only"})
            continue
        if key not in allowed:
            skipped.append({"key": key, "reason": "unknown_key"})
            continue
        text = str(value or "").strip()
        if not text:
            skipped.append({"key": key, "reason": "unknown_key"})
            continue
        if _filled(bucket.get(key)):
            skipped.append({"key": key, "reason": "already_filled"})
            continue
        bucket[key] = text
        applied.append({"key": key, "value": text})
    return card, applied, skipped
