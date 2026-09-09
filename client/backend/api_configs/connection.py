"""Connection testing — protocol-based health check.

探测按接口格式（api_format：openai | anthropic）构造，不再按 vendor 一一分支；
vendor 只保留 ollama 特例（本地服务、免 Key、自有 tags 端点）。
models 端点缺失（部分 Anthropic 兼容端点不提供列表）时降级为一条
max_tokens=1 的最小请求验证鉴权。
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

CONNECTION_TEST_TIMEOUT = int(os.environ.get("API_CONFIG_TEST_TIMEOUT", "10"))

# 降级探活请求的占位 model：仅验证鉴权与可达性，端点校验 model 在鉴权之后
_ANTHROPIC_PROBE_MODEL = "claude-sonnet-4-20250514"

# 「端点不提供 /models」时的候选起点（按 vendor）。
# 只放**实测可用**的 id（deepseek 2026-09-09 实测：anthropic 兼容端点 404、
# openai 端点 200 返回这三个）；没有把握的 vendor 留空 → 前端只给手动输入。
# 候选**不自动写库**（用户点选才落 models），避免把猜测值塞进配置。
VENDOR_MODEL_CANDIDATES: dict[str, list[str]] = {
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"],
}

# 端点不提供模型列表时的统一说明（连接成功但列表为空的原因）
NO_MODEL_LIST_NOTE = (
    "该端点不提供模型列表（Anthropic 兼容端点常见）——可手动填模型 id，"
    "或把接口格式改成 openai 后重新测试即可自动获取"
)


def model_candidates_for(vendor_id: str) -> list[str]:
    """该 vendor 的候选模型 id（可能为空；不触网）。"""
    return list(VENDOR_MODEL_CANDIDATES.get(vendor_id, []))


async def test_connection(
    vendor_id: str,
    api_key: str,
    base_url: str,
    api_format: str = "openai",
    timeout: int = CONNECTION_TEST_TIMEOUT,
) -> dict[str, Any]:
    """Test connectivity to a vendor's API.

    Returns a dict with:
        ok          — whether the probe succeeded (2xx)
        status      — one of "ok", "auth_error", "rate_limited",
                      "timeout", "network_error"
        models      — list of model IDs extracted, or None on failure
        error       — human-readable error string (only on failure)
    """
    # Some vendors (Ollama) don't require an API key
    requires_key = vendor_id != "ollama"
    if requires_key and not api_key.strip():
        return {
            "ok": False,
            "status": "auth_error",
            "models": None,
            "error": "API Key 为空，请填写后再测试",
        }

    endpoint, headers, extract_fn, fallback = _build_probe(
        api_format, vendor_id, api_key, base_url
    )

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code == 404 and fallback is not None:
                # models 端点不存在 → 降级最小请求验证鉴权；仅 401/403 判鉴权失败
                f_url, f_headers, f_payload = fallback
                resp = await client.post(f_url, headers=f_headers, json=f_payload)
                if resp.status_code in (401, 403):
                    detail = _extract_error_detail(resp)
                    return {
                        "ok": False,
                        "status": "auth_error",
                        "models": None,
                        "error": f"认证失败 (HTTP {resp.status_code}){detail}",
                    }
                return {
                    "ok": True,
                    "status": "ok",
                    "models": [],
                    "error": None,
                    "candidates": model_candidates_for(vendor_id),
                    "note": NO_MODEL_LIST_NOTE,
                }
    except httpx.TimeoutException:
        return {"ok": False, "status": "timeout", "models": None, "error": "连接超时"}
    except httpx.ConnectError:
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": "无法连接服务器",
        }
    except httpx.RequestError as exc:
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": f"网络错误: {exc}",
        }

    if resp.status_code == 401 or resp.status_code == 403:
        detail = _extract_error_detail(resp)
        return {
            "ok": False,
            "status": "auth_error",
            "models": None,
            "error": f"认证失败 (HTTP {resp.status_code}){detail}",
        }
    if resp.status_code == 429:
        return {
            "ok": False,
            "status": "rate_limited",
            "models": None,
            "error": "请求频率限制 (HTTP 429)",
        }
    if resp.status_code >= 500:
        detail = _extract_error_detail(resp)
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": f"服务端错误 (HTTP {resp.status_code}){detail}",
        }
    if resp.status_code != 200:
        detail = _extract_error_detail(resp)
        return {
            "ok": False,
            "status": "unknown",
            "models": None,
            "error": f"异常响应 (HTTP {resp.status_code}){detail}",
        }

    models = extract_fn(resp)
    return {"ok": True, "status": "ok", "models": models, "error": None}


# ── Protocol-based probe builder ────────────────────────────────────────────


def _openai_models_url(base: str) -> str:
    """OpenAI 格式探测端点：base 自带版本段（/v1、/v4、compatible-mode/v1）
    直接拼 /models；裸域名按 OpenAI 官方惯例补 /v1/models。"""
    return f"{base}/models" if re.search(r"/v\d+$", base) else f"{base}/v1/models"


def _build_probe(
    api_format: str, vendor_id: str, api_key: str, base_url: str
) -> tuple[str, dict[str, str], Any, tuple[str, dict[str, str], dict[str, Any]] | None]:
    """Return (endpoint_url, headers, response_extractor, auth_fallback).

    auth_fallback = (url, headers, payload)：models 端点 404 时的降级探活请求，
    仅 anthropic 格式提供（部分兼容端点不提供模型列表）。
    """
    base = base_url.rstrip("/")

    # ollama 特例：本地服务、免 Key、自有 tags 端点，不按任一协议探测
    if vendor_id == "ollama":
        url = "http://localhost:11434/api/tags"
        if "localhost" not in base and base != "http://localhost:11434":
            url = f"{base}/api/tags"
        return url, {}, _extract_ollama_models, None

    if api_format == "anthropic":
        # Anthropic SDK 惯例：base 不带 /v1（SDK 自拼 /v1/messages），
        # 用户粘贴以 /v1 结尾的 base 时先剥防双拼
        base = base.removesuffix("/v1")
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        fallback = (
            f"{base}/v1/messages",
            dict(headers),
            {
                "model": _ANTHROPIC_PROBE_MODEL,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            },
        )
        return f"{base}/v1/models", headers, _extract_openai_models, fallback

    # openai 格式（OpenAI 官方 / DeepSeek / GLM / Kimi / Qwen / 兼容端点）
    return (
        _openai_models_url(base),
        {"Authorization": f"Bearer {api_key}"},
        _extract_openai_models,
        None,
    )


# ── Response extractors ────────────────────────────────────────────────────


def _extract_openai_models(resp: httpx.Response) -> list[str]:
    """Extract model IDs from OpenAI/Anthropic /models response (data[].id)."""
    try:
        data = resp.json()
        return [
            m["id"] for m in data.get("data", []) if isinstance(m, dict) and m.get("id")
        ]
    except (KeyError, TypeError, ValueError):
        return []


def _extract_error_detail(resp: httpx.Response) -> str:
    """Extract a human-readable detail snippet from an error response."""
    try:
        body = resp.json()
        msg = (
            body.get("error", {}).get("message", "")
            or body.get("message", "")
            or body.get("error", "")
        )
        if isinstance(msg, str) and msg.strip():
            return f" — {msg.strip()[:120]}"
    except (ValueError, TypeError, AttributeError):
        pass
    return ""


def _extract_ollama_models(resp: httpx.Response) -> list[str]:
    """Extract model names from Ollama /api/tags response."""
    try:
        data = resp.json()
        return [
            m["name"]
            for m in data.get("models", [])
            if isinstance(m, dict) and m.get("name")
        ]
    except (KeyError, TypeError, ValueError):
        return []
