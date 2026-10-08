"""Vendor detection — match base_url to known providers."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class VendorPattern:
    vendor_id: str
    display_name: str
    pattern: re.Pattern[str]
    protocol: str = "openai"


VENDOR_PATTERNS: list[VendorPattern] = [
    VendorPattern(
        "openai", "OpenAI", re.compile(r"^https://api\.openai\.com", re.IGNORECASE)
    ),
    VendorPattern(
        "anthropic",
        "Anthropic",
        re.compile(r"^https://api\.anthropic\.com", re.IGNORECASE),
    ),
    VendorPattern(
        "deepseek",
        "DeepSeek",
        re.compile(r"^https://api\.deepseek\.com", re.IGNORECASE),
    ),
    VendorPattern(
        "glm", "GLM", re.compile(r"^https://open\.bigmodel\.cn", re.IGNORECASE)
    ),
    VendorPattern(
        "kimi", "Kimi", re.compile(r"^https://api\.moonshot\.cn", re.IGNORECASE)
    ),
    VendorPattern(
        "qwen", "Qwen", re.compile(r"^https://dashscope\.aliyuncs\.com", re.IGNORECASE)
    ),
    VendorPattern(
        "ollama", "Ollama", re.compile(r"^http://localhost:11434", re.IGNORECASE)
    ),
]

ANTHROPIC_MODELS: list[str] = [
    "claude-sonnet-4-20250514",
    "claude-haiku-4-20250712",
]


def detect_vendor(base_url: str) -> VendorPattern | None:
    """Match a base_url against known vendor patterns.

    Returns the first matching VendorPattern, or None if no match.
    """
    for vp in VENDOR_PATTERNS:
        if vp.pattern.search(base_url):
            return vp
    return None


# 无 URL 形态的入口型 vendor 展示名——按钮显式选择、域名检测不可达：
# relay 中转站域名形态任意，只能经 vendor_override 登记（c-relay-vendor-entry）
_OVERRIDE_DISPLAY = {
    "relay": "中转站 API",
    "openai-compat": "OpenAI 兼容",
}


def resolve_vendor(
    base_url: str,
    vendor_override: str | None = None,
) -> tuple[str, str, str]:
    """Return (vendor_id, display_name, protocol).

    Respects vendor_override if provided; otherwise auto-detects.
    Falls back to ("openai-compat", "OpenAI 兼容", "openai").
    """
    if vendor_override:
        # Check if the override matches a known vendor
        for vp in VENDOR_PATTERNS:
            if vp.vendor_id == vendor_override:
                return (vp.vendor_id, vp.display_name, vp.protocol)
        return (
            vendor_override,
            _OVERRIDE_DISPLAY.get(vendor_override, vendor_override),
            "openai",
        )

    detected = detect_vendor(base_url)
    if detected:
        return (detected.vendor_id, detected.display_name, detected.protocol)

    return ("openai-compat", "OpenAI 兼容", "openai")
