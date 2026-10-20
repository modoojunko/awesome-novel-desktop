"""Vendor detection — match base_url to known providers."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

from schema_version import app_version


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
    # c-modelconfig-gemini-go：Gemini 官方兼容层＋OpenCode Go 订阅两口。键＝前端
    # 方块 id（schema 白名单/落库 vendor/编辑回显三处同一字符串）；两个 Go 键同主机，
    # **/v1 模式必须登记在无版本段模式之前**（search 前缀匹配，顺序反了会被遮蔽）。
    VendorPattern(
        "gemini",
        "Gemini",
        re.compile(r"^https://generativelanguage\.googleapis\.com", re.IGNORECASE),
    ),
    VendorPattern(
        "opencode-go-chat",
        "OpenCode Go · 通用",
        re.compile(r"^https://opencode\.ai/zen/go/v1", re.IGNORECASE),
    ),
    VendorPattern(
        "opencode-go-claude",
        "OpenCode Go · Claude 系",
        re.compile(r"^https://opencode\.ai/zen/go", re.IGNORECASE),
    ),
]

OPENCODE_SESSION_HEADER = "x-opencode-session"
_PROCESS_SALT = uuid.uuid4().hex


def is_opencode_base(base_url: str) -> bool:
    """主机命中 OpenCode 订阅网关（opencode.ai 或其子域）——身份头仅对此类请求附加。"""
    try:
        host = (urlsplit(base_url or "").hostname or "").lower()
    except ValueError:
        return False
    return host == "opencode.ai" or host.endswith(".opencode.ai")


def opencode_identity_headers(api_key: str, base_url: str) -> dict[str, str]:
    """OpenCode 网关身份头（spec「订阅入口与 Gemini 的调用适配」）：会话标识＝进程盐
    ＋base＋key 摘要（同一配置进程内稳定、重启更换、零穿参），UA＝产品形态——
    SHALL NOT 以 SDK/HTTP 库默认 UA 出现在该网关请求上。"""
    digest = hashlib.sha256(
        f"{_PROCESS_SALT}|{base_url or ''}|{api_key or ''}".encode()
    ).hexdigest()[:16]
    return {
        OPENCODE_SESSION_HEADER: f"ainovel-{digest}",
        "User-Agent": f"ai-novel/{app_version()}",
    }


def gemini_effort(effort: str) -> str:
    """思考档位换算：Gemini 契约无 max 档——low/high 原样，深 max 按高下发。"""
    e = (effort or "low").strip().lower()
    return "high" if e == "max" else (e or "low")


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
        return (vendor_override, vendor_override, "openai")

    detected = detect_vendor(base_url)
    if detected:
        return (detected.vendor_id, detected.display_name, detected.protocol)

    return ("openai-compat", "OpenAI 兼容", "openai")
