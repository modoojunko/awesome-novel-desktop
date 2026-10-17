"""模型能力与调用预算（c-deconstruct-resilience D5/D6）。

拆书是**输出密集**任务：258 章卡片 ≈ 39 万输出 token，合批大小由「单次输出上限」
决定，1M 输入窗口只决定「能不能把更多材料一次喂进去」（单遍归并/更大批次），
不改变输出预算优先的口径。

能力来源（保守优先，未知不阻塞）：
1. env 显式覆盖 `DECONSTRUCT_CAPS`（JSON：context_window / max_output_tokens）——
   用户确认目标模型 1M 上下文后由此解锁大预算；
2. 内置 vendor 表（只收有公开文档、取保守下限的家族）；
3. 保守默认（32k 上下文 / 8k 输出）。

超预算自愈：能力数字偏大时 provider 会以 400「context length / maximum」拒绝——
classify 归为 truncated 同族（KIND_TRUNCATED 文本判定），管线按「拆半重试」
收缩批次，MUST NOT 原样重发同尺寸请求（见 policy.D1）。

token 估算：仓内无 tokenizer 依赖（design 勘探），用 CJK≈1 token/字、ASCII≈0.3/字、
整体 +15% 余量的确定性启发式；响应 usage 反向校准留给调用账（观测不回馈控制）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

_TOKEN_MARGIN = 1.15


@dataclass(frozen=True)
class ModelCaps:
    context_window: int
    max_output_tokens: int
    long_context_threshold: int = 128_000
    source: str = "conservative"  # env / known / conservative


DEFAULT_CAPS = ModelCaps(32_768, 8_192)

# vendor 保守下限表（公开文档口径；实际型号普遍高于此值，宁小勿大——
# 偏大靠 400/截断的拆半自愈兜底，偏小只是少省几次调用）
_VENDOR_KNOWN = {
    "deepseek": ModelCaps(131_072, 8_192, source="known"),
    "glm": ModelCaps(131_072, 8_192, source="known"),
}


def caps_for(vendor: str = "", model: str = "") -> ModelCaps:
    """解析能力：env 覆盖 > vendor 表 > 保守默认。解析失败按保守默认（不阻塞任务）。"""
    raw = os.environ.get("DECONSTRUCT_CAPS", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            return ModelCaps(
                context_window=int(data["context_window"]),
                max_output_tokens=int(data["max_output_tokens"]),
                long_context_threshold=int(data.get("long_context_threshold", 128_000)),
                source="env",
            )
        except (ValueError, KeyError, TypeError):
            pass
    low = f"{vendor} {model}".lower()
    for key, caps in _VENDOR_KNOWN.items():
        if key in low:
            return caps
    return DEFAULT_CAPS


def estimate_tokens(text: str) -> int:
    """确定性 token 估算：CJK 记 1/字、其余记 0.3/字，整体 +15% 余量。"""
    if not text:
        return 0
    cjk = sum(1 for ch in text if ord(ch) > 0x2E7F)
    other = len(text) - cjk
    return int((cjk + other * 0.3) * _TOKEN_MARGIN) + 1


def tokens_to_chars(tokens: int) -> int:
    """估算逆变换：给 token 预算求可喂字符上限（打包层继续按字符装箱，
    保持 CARD_BATCH_CHARS 语义与既有测试兼容）。"""
    return max(1, int(tokens / _TOKEN_MARGIN))


def usable_output(caps: ModelCaps) -> int:
    """单次调用可放心使用的输出预算（25% 安全余量：贴顶截断真机实证）。"""
    return max(1024, int(caps.max_output_tokens * 0.75))


def input_budget_chars(caps: ModelCaps, prompt_overhead_tokens: int = 4_000) -> int:
    """单次调用输入的字符上限 =（上下文 − 输出预算 − 模板/梗概开销）折算字符。"""
    budget_tokens = caps.context_window - usable_output(caps) - prompt_overhead_tokens
    return max(2_000, tokens_to_chars(max(budget_tokens, 2_000)))


# 单次归并/合批调用的输出 token 上限（安全默认；env DECONSTRUCT_MERGE_MAX_TOKENS 覆盖）
def merge_max_tokens(caps: ModelCaps) -> int:
    env = os.environ.get("DECONSTRUCT_MERGE_MAX_TOKENS", "").strip()
    if env.isdigit():
        return int(env)
    return max(8_192, min(usable_output(caps), 16_384))


def oversize_reject(e: Exception) -> bool:
    """provider 对「输入超上下文 / 输出超模型上限」的拒绝——按截断同族拆半自愈。

    只认 400（或不带状态码的包装异常）且报文含长度语义；其余 400 归 config 不重试。
    """
    status = getattr(e, "status_code", None)
    if status is not None and status != 400:
        return False
    low = str(e).lower()
    marks = ("context length", "maximum context", "too long", "max_tokens",
             "reduce the length", "input length", "超长", "上下文长度")
    return any(m in low for m in marks)


__all__ = [
    "DEFAULT_CAPS",
    "ModelCaps",
    "caps_for",
    "estimate_tokens",
    "input_budget_chars",
    "merge_max_tokens",
    "oversize_reject",
    "tokens_to_chars",
    "usable_output",
]
