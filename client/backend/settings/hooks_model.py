"""伏笔领域单源（foreshadow-settings-v2 tasks 1.1）。

type 枚举、status 枚举、长度常量、priority 归一的唯一事实源——注入块由这里渲染
（模板不手抄枚举），前端留镜像副本 `src/lib/hooksModel.ts` + parity 测试锁逐字一致
（照 tests/test_shared_constants_parity.py 的正则抽取手法；镜像与 parity 测试随
前端批 1 PR 落地，见 tasks 4.x）。

分层与 settings/character_model.py 同族：纯常量 + 纯函数，零 IO。
"""

from __future__ import annotations

# ── 类型词表（9 slug；UI 标签与 AI 出参归一共用此表）─────────────────────
HOOK_TYPES: list[dict] = [
    {"k": "mystery", "label": "悬念"},
    {"k": "threat", "label": "威胁"},
    {"k": "promise", "label": "承诺"},
    {"k": "clue", "label": "线索"},
    {"k": "relationship", "label": "关系伏笔"},
    {"k": "power", "label": "能力伏笔"},
    {"k": "emotion", "label": "情绪钩"},
    {"k": "choice", "label": "选择钩"},
    {"k": "desire", "label": "渴望钩"},
]
HOOK_TYPE_KEYS: tuple[str, ...] = tuple(f["k"] for f in HOOK_TYPES)
_TYPE_LABELS = {f["k"]: f["label"] for f in HOOK_TYPES}

# ── 状态词表（单列；「收束」是唯一系统词）────────────────────────────────
# active=进行中·待收束 / resolved=已收束 / abandoned=废弃。
# mentioned 不是状态：归档留痕走 mentioned_in_chapter_id 独立列（write-archive-meta-sync）。
HOOK_STATUSES: tuple[str, ...] = ("active", "resolved", "abandoned")

# ── 长度纪律（同角色族：短段落 300 档）──────────────────────────────────
DESCRIPTION_MAX = 300
PAYOFF_NOTE_MAX = 300

# ── 优先级（存储 Integer 1/2/3；展示/注入统一 高/中/低，映射唯一）────────
PRIORITY_LABELS: dict[int, str] = {1: "高", 2: "中", 3: "低"}
# API 兼容混形：字符串数字与英文词都归一到 Integer（导入器 v1 读窗同源复用）
_PRIORITY_WORDS = {"high": 1, "medium": 2, "low": 3}


def normalize_priority(value) -> int:
    """priority 混形归一：int 1/2/3、"1"/"2"/"3"、"high/medium/low" → Integer。

    非法输入 raise ValueError（服务层转 400；导入器记 warning），不静默吞。
    """
    if isinstance(value, bool):
        raise ValueError(f"invalid priority: {value!r}")  # noqa: TRY004 — 调用方按 ValueError 归一 400
    if isinstance(value, int):
        if value in PRIORITY_LABELS:
            return value
        raise ValueError(f"invalid priority: {value!r}")
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _PRIORITY_WORDS:
            return _PRIORITY_WORDS[text]
        if text.isdigit():
            num = int(text)
            if num in PRIORITY_LABELS:
                return num
        if value.strip() in PRIORITY_LABELS.values():
            # 中文标签「高/中/低」也容许（展示值回存）
            return next(k for k, v in PRIORITY_LABELS.items() if v == value.strip())
    raise ValueError(f"invalid priority: {value!r}")


def priority_label(value) -> str:
    """Integer → 高/中/低；非法值返回空串（调用方丢弃该标注，不静默吞错位）。"""
    try:
        return PRIORITY_LABELS.get(normalize_priority(value), "")
    except ValueError:
        return ""


def type_label(value: str) -> str:
    """slug → 中文标签；未知值原样返回（导入器/AI 出参兜底）。"""
    return _TYPE_LABELS.get(str(value or ""), str(value or ""))
