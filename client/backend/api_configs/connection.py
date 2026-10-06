"""Connection testing — protocol-based health check.

探测按接口格式（api_format：openai | anthropic）构造，不再按 vendor 一一分支；
vendor 只保留 ollama 特例（本地服务、免 Key、自有 tags 端点）。
models 端点缺失（部分 Anthropic 兼容端点不提供列表）时降级为一条
max_tokens=1 的最小请求验证鉴权。

「通」的判据（2026-10-05 拍板）：200 必须是 API JSON——网站首页/SPA 对任意路径
回 200 HTML 不算通；可达且鉴权通过后向对话接口发**真实最小生成探针**——消息「你好」、
关闭思考（ai_client 同款禁思考约定，端点拒绝该参数时去参重试一次）、短输出预算，
与生成同址同鉴权头（openai {base}/chat/completions／anthropic {base}/v1/messages）；
收到**格式正确且含可见回复文本**的回复才算通——非 2xx、体不符格式、空回复一律判失败，
400/422 类业务性拒绝不再放行（点名所试模型 id）；无可用模型 id（列表空且无候选）
判失败并提示填写模型名。
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
# 与前端 vendorDefaults.ts 的 VENDOR_DEFAULTS 登记表同族（那边是创建预填值）：
# 登记值/候选变更两处对齐。
VENDOR_MODEL_CANDIDATES: dict[str, list[str]] = {
    "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"],
}

# 端点不提供模型列表时的统一说明（连接成功但列表为空的原因）
NO_MODEL_LIST_NOTE = (
    "该端点不提供模型列表（Anthropic 兼容端点常见）——可手动填模型 id，"
    "或把接口格式改成 openai 后重新测试即可自动获取"
)

# 最小生成探针（2026-10-05 拍板）：「你好」＋禁思考＋短输出预算，格式正确回复才算通
_PROBE_PROMPT = "你好"
_PROBE_MAX_TOKENS = 32
_THINKING_DISABLED = {"type": "disabled"}


def model_candidates_for(vendor_id: str) -> list[str]:
    """该 vendor 的候选模型 id（可能为空；不触网）。"""
    return list(VENDOR_MODEL_CANDIDATES.get(vendor_id, []))


async def test_connection(
    vendor_id: str,
    api_key: str,
    base_url: str,
    api_format: str = "openai",
    timeout: int = CONNECTION_TEST_TIMEOUT,
    preferred_model: str | None = None,
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
                # models 端点不存在 → 降级为「你好」最小生成探针（2026-10-05 拍板）：
                # 收到格式正确且含可见回复文本的回复才算通；401/403 判鉴权失败；
                # 404/405 = 对话接口本身不可达（地址/格式错）
                f_url, f_headers, f_payload = fallback
                resp = await _post_with_thinking_retry(
                    client, f_url, f_headers, f_payload
                )
                if resp.status_code in (401, 403):
                    detail = _extract_error_detail(resp)
                    return {
                        "ok": False,
                        "status": "auth_error",
                        "models": None,
                        "error": f"认证失败 (HTTP {resp.status_code}){detail}",
                    }
                if resp.status_code in (404, 405):
                    return {
                        "ok": False,
                        "status": "endpoint_mismatch",
                        "models": None,
                        "error": (
                            f"对话接口不可达（HTTP {resp.status_code} @ {f_url}）——"
                            "请核对 Base URL 与接口格式是否和厂商文档一致"
                        ),
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
                        "error": (
                            f"最小生成探针被拒（HTTP {resp.status_code} @ {f_url}）"
                            f"{detail}——请核对模型 id 与接口格式"
                        ),
                    }
                not_api = _non_api_response(resp)
                if not_api:
                    return {
                        "ok": False,
                        "status": "endpoint_mismatch",
                        "models": None,
                        "error": not_api,
                    }
                if not _anthropic_reply_text(resp):
                    return {
                        "ok": False,
                        "status": "unknown",
                        "models": None,
                        "error": (
                            f"模型回复格式不正确或回复为空（@ {f_url}）——请核对接口格式"
                            "（anthropic 契约应返回 content 文本块）"
                        ),
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

    not_api = _non_api_response(resp)
    if not_api:
        return {
            "ok": False,
            "status": "endpoint_mismatch",
            "models": None,
            "error": not_api,
        }
    models = extract_fn(resp)
    # openai 格式：追加「你好」最小生成探针（与生成同址同头）。旧实现只探 /models，
    # 而生成走 {base}/chat/completions——「测试通了、一用就 405/404」的错位根源（内测 405 案）。
    if api_format == "openai" and vendor_id != "ollama":
        probe_model = _probe_model(models, vendor_id, preferred_model)
        if not probe_model:
            # 无任何可用模型 id：仅凭可达性/鉴权不算通（2026-10-05 拍板）
            return {
                "ok": False,
                "status": "unknown",
                "models": None,
                "error": "模型列表为空且无候选模型 id——请填写模型名称后重新测试",
            }
        ping = await _probe_chat_path(client, base_url, headers, probe_model)
        if ping is not None:
            return ping
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
                "max_tokens": _PROBE_MAX_TOKENS,
                "messages": [{"role": "user", "content": _PROBE_PROMPT}],
                "thinking": dict(_THINKING_DISABLED),
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


# ── 「通」的判据组件：非 API 响应识别 / 对话路径探针 ──────────────────────────


def _non_api_response(resp: httpx.Response) -> str:
    """200 响应但体不是 API JSON → 返回给用户的说明；是 JSON 则返回空串。

    典型：Base URL 填成网站首页，SPA 对任意路径回 200 HTML——旧实现按 200 判
    「连接正常」，坏配置到生成期才炸（内测 405 案）。
    """
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    try:
        body = resp.json()
    except (ValueError, TypeError):
        return (
            "该地址返回的不是 API 数据"
            + (f"（Content-Type: {ctype}）" if ctype else "")
            + "——看起来像网页。请检查 Base URL 是否填成了网站地址"
        )
    if isinstance(body, dict) and body.get("error"):
        msg = body["error"]
        if isinstance(msg, dict):
            msg = msg.get("message") or msg.get("msg") or str(msg)
        return f"服务返回了错误（{str(msg)[:120]}）——请检查 Base URL 与 API Key"
    return ""


def _probe_model(
    models: list[str], vendor_id: str, preferred_model: str | None = None
) -> str:
    """对话探针的模型 id：配置已选模型（preferred）→ 模型列表首个 → vendor 候选首个 → 空串（跳过探针）。"""
    if preferred_model and preferred_model.strip():
        return preferred_model.strip()
    if models:
        return models[0]
    candidates = model_candidates_for(vendor_id)
    return candidates[0] if candidates else ""


async def _probe_chat_path(
    client: httpx.AsyncClient, base_url: str, headers: dict[str, str], model: str
) -> dict[str, Any] | None:
    """openai 格式最小生成探针（2026-10-05 拍板）：POST {base}/chat/completions，
    消息「你好」＋禁思考＋短输出预算——收到格式正确且含可见回复文本的回复才算通。

    返回 None = 通过；非 2xx、体不符格式、空回复一律判失败（400/422 类业务性拒绝
    不再放行——点名所试模型 id），失败形态 dict = 直接作为连接测试结果返回。
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": _PROBE_PROMPT}],
        "max_tokens": _PROBE_MAX_TOKENS,
        "thinking": dict(_THINKING_DISABLED),
    }
    try:
        resp = await _post_with_thinking_retry(client, url, headers, payload)
    except httpx.TimeoutException:
        return {
            "ok": False,
            "status": "timeout",
            "models": None,
            "error": "对话探针超时（连接超时）",
        }
    except httpx.RequestError as exc:
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": f"网络错误: {exc}",
        }
    if resp.status_code in (401, 403):
        detail = _extract_error_detail(resp)
        return {
            "ok": False,
            "status": "auth_error",
            "models": None,
            "error": f"认证失败 (HTTP {resp.status_code}){detail}",
        }
    if resp.status_code in (404, 405):
        return {
            "ok": False,
            "status": "endpoint_mismatch",
            "models": None,
            "error": (
                f"对话接口不可用（HTTP {resp.status_code} @ {url}）——请核对 Base URL "
                "与接口格式是否和厂商文档一致（常见：地址少了 /v1，或填成了网站地址）"
            ),
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
            "error": (
                f"探针请求被拒（HTTP {resp.status_code} @ {url}）——所试模型 {model}"
                f"{detail}；请核对模型 id 是否有效（可在配置里填写模型名称）"
            ),
        }
    not_api = _non_api_response(resp)
    if not_api:
        return {
            "ok": False,
            "status": "endpoint_mismatch",
            "models": None,
            "error": not_api,
        }
    if not _openai_reply_text(resp):
        return {
            "ok": False,
            "status": "unknown",
            "models": None,
            "error": (
                f"模型回复格式不正确或回复为空（@ {url}）——所试模型 {model}，"
                "请核对模型 id 与接口格式（openai 契约应返回 choices[0].message）"
            ),
        }
    return None


async def _post_with_thinking_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> httpx.Response:
    """POST 最小生成探针；端点拒绝 thinking 参数时去参重试一次（ai_client 同款约定）。"""
    resp = await client.post(url, headers=headers, json=payload)
    if "thinking" in payload and resp.status_code == 400:
        body = getattr(resp, "text", "") or ""
        if "thinking" in body.lower():
            stripped = {k: v for k, v in payload.items() if k != "thinking"}
            resp = await client.post(url, headers=headers, json=stripped)
    return resp


def _openai_reply_text(resp: httpx.Response) -> str:
    """openai chat.completion 契约的助手回复文本；格式不符/空 → 空串。"""
    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        return ""
    return content.strip() if isinstance(content, str) else ""


def _anthropic_reply_text(resp: httpx.Response) -> str:
    """anthropic messages 契约的可见回复文本（text 块拼接）；格式不符/空 → 空串。"""
    try:
        data = resp.json()
    except (ValueError, TypeError):
        return ""
    blocks = data.get("content") if isinstance(data, dict) else None
    if not isinstance(blocks, list):
        return ""
    texts = [
        b.get("text", "")
        for b in blocks
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    return "".join(t for t in texts if isinstance(t, str)).strip()


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
