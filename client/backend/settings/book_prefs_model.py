"""作品偏好（book-prefs）KV 模型（c-chapter-default-words，内测反馈#10）。

当前唯一字段＝**章节默认字数**：章纲「本章目标字数」留空时，生成链（写正文的
提示词字数要求）与前端表单文案（「留空默认 XXX」）共用的 per-book 默认值。

- 键 ``book-prefs`` 仿 threads/style-quant：route_relative_path 专用键、不进
  PATH_TO_KEY（不进通用 /settings/{type} 端点）；读写只走 book_prefs_router。
- 区间与缺省单源在本模块（前端镜像 ``src/lib/chapterTarget.ts``，
  tests/test_shared_constants_parity.py 对拍）：写正文的夹取守卫与表单校验必须是
  同一组数值，否则表单放行、生成侧静默回落，用户看到的默认与实际生效值是两回事。
- 存储只记**显式设置**：未设置（键缺失/null）＝缺省 2500——存量项目零迁移、
  行为不变（与逐章 word_target 留空同义）。
"""

from __future__ import annotations

from typing import Any

# 章节默认字数区间与缺省（与逐章 word_target 同区间，沿用 500-6000 / 2500）
CHAPTER_WORD_TARGET_MIN = 500
CHAPTER_WORD_TARGET_MAX = 6000
CHAPTER_WORD_TARGET_DEFAULT = 2500

# 作品偏好 KV 里的字段名（前端 JSON 契约同名字段）
CHAPTER_WORD_TARGET_FIELD = "chapter_word_target"

# 全书默认节奏（c-volume-pacing）：套路键＋每段几章。预设与 clamp 单源在
# volumes/pacing.py（纯常量模块，导入无环）；本模块只做 KV 读写形状。
PACING_PRESET_FIELD = "pacing_preset"
PACING_STEPS_LEN_FIELD = "pacing_steps_len"


def normalize_chapter_word_target(value: Any) -> int | None:
    """写入口守卫：None/空串＝清除设置（回落缺省）；合法 int 原样；其余抛错。

    调用方（book_prefs_router）把 TypeError/ValueError 转 400——表单已按区间限制，
    越界值到不了这里；这是 API 兜底，不静默改写用户输入。
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("章节默认字数必须是整数")
    if value < CHAPTER_WORD_TARGET_MIN or value > CHAPTER_WORD_TARGET_MAX:
        raise ValueError(
            f"章节默认字数需在 {CHAPTER_WORD_TARGET_MIN}-{CHAPTER_WORD_TARGET_MAX} 之间"
        )
    return value


def read_book_prefs(doc: Any) -> dict[str, Any]:
    """KV 原文 → 归一响应（只出显式设置过的字段；缺省由消费方按常量回落）。"""
    if not isinstance(doc, dict):
        return {}
    out: dict[str, Any] = {}
    target = doc.get(CHAPTER_WORD_TARGET_FIELD)
    if (
        isinstance(target, int)
        and not isinstance(target, bool)
        and CHAPTER_WORD_TARGET_MIN <= target <= CHAPTER_WORD_TARGET_MAX
    ):
        out[CHAPTER_WORD_TARGET_FIELD] = target
    # 全书默认节奏（c-volume-pacing）：套路键合法才出；段长只在套路在场时出
    # （孤值无意义——前端选择器换套路即重置段长，存储不背半套配置）。
    from volumes.pacing import LEN_MAX, LEN_MIN, PACING_PRESETS

    preset = str(doc.get(PACING_PRESET_FIELD) or "")
    if preset in PACING_PRESETS:
        out[PACING_PRESET_FIELD] = preset
        length = doc.get(PACING_STEPS_LEN_FIELD)
        if (
            isinstance(length, int)
            and not isinstance(length, bool)
            and LEN_MIN <= length <= LEN_MAX
        ):
            out[PACING_STEPS_LEN_FIELD] = length
    return out


def effective_chapter_word_target(doc: Any) -> int:
    """生成链取用：本书设置 → 缺省 2500（未设置/值损坏一律回落，不阻塞写章）。"""
    return read_book_prefs(doc).get(
        CHAPTER_WORD_TARGET_FIELD, CHAPTER_WORD_TARGET_DEFAULT
    )


def clamp_word_target(value: Any, default: int = CHAPTER_WORD_TARGET_DEFAULT) -> int:
    """目标字数守卫：空/非法/越界 → default；否则照用（区间 500-6000）。

    c-scene-density 评审（2026-10-13）自 write/chapter_writer 迁入本模块：数值单源
    本就住这里，写章组装（write/）与剧情抽卡（chapters/ai_plot）共用——函数留在
    write 域会逼出 chapters→write 的跨域 import。越界语义是「同落 default」而非
    逐层回落（与写章侧同 clamp，见 chapters/ai_plot 取值链注释）。
    """
    try:
        n = int(value) if value is not None else None
    except (TypeError, ValueError):
        n = None
    if n is None:
        return default
    if n < CHAPTER_WORD_TARGET_MIN or n > CHAPTER_WORD_TARGET_MAX:
        return default
    return n
