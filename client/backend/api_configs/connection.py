"""Connection testing — protocol-based health check.

探测按接口格式（api_format：openai | anthropic）构造，不再按 vendor 一一分支；
vendor 只保留 ollama 特例（本地服务、免 Key、自有 tags 端点）。
models 端点缺失（部分 Anthropic 兼容端点不提供列表）时降级为同款最小生成探针；
models 端点回 200 网页体（网关对未知路径回首页的可用端点，内测反馈#1 残余）同样降级，
对话接口探通即放行，探不通才按「不是 API 数据」判失败。

「通」的判据（2026-10-05 拍板）：200 必须是 API JSON——网站首页/SPA 对任意路径
回 200 HTML 不算通；可达且鉴权通过后向对话接口发**真实最小生成探针**——消息「你好」、
关闭思考（ai_client 同款禁思考约定，端点拒绝该参数时去参重试一次）、短输出预算，
与生成同址同鉴权头（openai {base}/chat/completions／anthropic {base}/v1/messages）；
收到**格式正确且含可见回复文本**的回复才算通——非 2xx、体不符格式、空回复一律判失败，
400/422 类业务性拒绝不再放行（点名所试模型 id）；无可用模型 id（列表空且无候选）
判失败并提示填写模型名。

留痕（c-llm-call-log）：每个出网请求落一行 `llm_probe` 日志（llm.log 专项档＋
app.log 双写）——Gemini 401 定诊实锤：探针不落日志时远程只能靠推断。行只含
host＋path（丢弃 query；headers 含 Key 永不落）＋上游状态码＋耗时＋结果分类。

openai 格式的 base 全链路版本段归一（2026-10-09 kakou 中转案）：models 探测、对话
探针（主链＋404 降级）、生成调用（ai_client 传 SDK 的 base）共用 `normalize_openai_base`
单源——裸域名按 OpenAI 官方惯例补 /v1，自带版本段（含 Gemini 兼容层 /v1beta/openai
的中段形态）原样保留；此前只有 models 探测补 /v1，中转站网页壳对非 /v1 路径回 200
网页时呈「清单绿、测试红」半通形态。
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from http_client import build_async_client

# llm.log 专项档挂载点（logging_setup._LLM_LOGGERS 同名登记）
logger = logging.getLogger("llm_probe")

CONNECTION_TEST_TIMEOUT = int(os.environ.get("API_CONFIG_TEST_TIMEOUT", "10"))

# 降级探活请求的占位 model：仅验证鉴权与可达性，端点校验 model 在鉴权之后
_ANTHROPIC_PROBE_MODEL = "claude-sonnet-4-20250514"

# 「端点不提供 /models」时的候选起点（按 vendor）。
# 只放**有据**的 id（厂商官方文档或实测）；没有把握的 vendor 留空 → 前端只给手动输入。
# 候选**不自动写库**（用户点选才落 models），避免把猜测值塞进配置。
# 与前端 vendorDefaults.ts 的 VENDOR_DEFAULTS 登记表同族（那边是创建预填值）：
# 登记值/候选变更两处对齐。
# deepseek 2026-10-07 按官方文档刷新（api-docs.deepseek.com/api/list-models：
# 现返回 deepseek-flash 与 deepseek-v4-pro；deepseek-v4-flash 已不存在，vision 实验版无据撤下）。
VENDOR_MODEL_CANDIDATES: dict[str, list[str]] = {
    "deepseek": ["deepseek-flash", "deepseek-v4-pro"],
}

# 端点不提供模型列表时的统一说明（连接成功但列表为空的原因），按接口格式分文案：
# anthropic 版尾句引导「改成 openai 重测拉清单」；openai 格式下该尾句是自我循环，
# 故 openai 版只留手填出口（c-api-config-foreign-vendors 评审补查：消费点三处——
# test_connection 404 降级 / fetch-models anthropic 分支 / model-candidates 端点）。
NO_MODEL_LIST_NOTE_ANTHROPIC = (
    "该端点不提供模型列表（Anthropic 兼容端点常见）——可手动填模型 id，"
    "或把接口格式改成 openai 后重新测试即可自动获取"
)
NO_MODEL_LIST_NOTE_OPENAI = (
    "该端点不提供模型列表——可手动填模型 id 后重新测试"
)


def no_model_list_note(api_format: str) -> str:
    """按接口格式选「端点不提供模型列表」说明。"""
    return (
        NO_MODEL_LIST_NOTE_OPENAI
        if api_format == "openai"
        else NO_MODEL_LIST_NOTE_ANTHROPIC
    )

# 最小生成探针（2026-10-05 拍板）：「你好」＋禁思考＋短输出预算，格式正确回复才算通。
# c-thinking-config：思考开启（或端点强制思考、去参重试后）预算放大——强制思考模型
# （GLM-5.3）会把输出预算花在推理上，32 只够思考、正文为空，探针会误判「回复为空」。
_PROBE_PROMPT = "你好"
_PROBE_MAX_TOKENS = 32
_PROBE_MAX_TOKENS_THINKING = 1024
_THINKING_DISABLED = {"type": "disabled"}


def model_candidates_for(vendor_id: str) -> list[str]:
    """该 vendor 的候选模型 id（可能为空；不触网）。"""
    return list(VENDOR_MODEL_CANDIDATES.get(vendor_id, []))


# ── 留痕组件（c-llm-call-log）────────────────────────────────────────────────


def _probe_target(url: str) -> tuple[str, str]:
    """URL → (host, path)。query 永不落日志——某些网关支持 ?key= 传钥，整 URL
    与请求头一样按机密处理。

    urlparse 对畸形 URL（如未闭合 `[`，实测 httpx 0.28.1 接受并真实发起连接）
    会抛 ValueError——留痕调用点多在 except 处理器里，二次抛会把既有友好报错
    （network_error dict）500 化（评审 P2 实锤）。兜底 ("-", "-")：host/path 可缺，
    「出网即有行」与「报错不劣化」两条不变量保住。"""
    try:
        parts = urlparse(url)
    except ValueError:
        return "-", "-"
    return parts.netloc, parts.path or "/"


def _status_result(status_code: int) -> str:
    """上游 HTTP 状态码 → 机械结果分类（请求级事实，不掺业务判断——anthropic
    格式 models 404 在返回体里是合法形态，日志仍如实记 not_found）。"""
    if 200 <= status_code < 300:
        return "ok"
    if status_code in (401, 403):
        return "auth_error"
    if status_code == 404:
        return "not_found"
    if status_code == 429:
        return "rate_limited"
    if status_code >= 500:
        return "server_error"
    return "http_error"


def _log_probe(
    kind: str,
    *,
    vendor: str,
    api_format: str,
    url: str,
    start: float,
    status: int = 0,
    model: str = "",
    result: str | None = None,
    error: str | None = None,
) -> None:
    """一个出网请求一行留痕：成功 INFO / 失败 WARNING（ai_client 留痕行同款约定）。

    status=0 表示请求未完成（超时/连接失败）；result 缺省按状态码机械映射。
    """
    host, path = _probe_target(url)
    outcome = result or _status_result(status)
    # ollama 特例（同 _build_probe）：探测走 Ollama 原生 /api/tags，与接口格式
    # 无关——format 记 - 而非误记入参缺省 openai（评审 P3）
    fmt = "-" if vendor == "ollama" else (api_format or "-")
    logger.log(
        logging.INFO if outcome == "ok" else logging.WARNING,
        "event=llm_probe kind=%s vendor=%s format=%s host=%s path=%s model=%s"
        " status=%d duration_ms=%.0f result=%s%s",
        kind, vendor or "-", fmt, host, path, model or "-",
        status, (time.perf_counter() - start) * 1000, outcome,
        f" error={error[:120]}" if error else "",
    )


async def test_connection(
    vendor_id: str,
    api_key: str,
    base_url: str,
    api_format: str = "openai",
    timeout: int = CONNECTION_TEST_TIMEOUT,
    preferred_model: str | None = None,
    thinking_enabled: bool = False,
    thinking_effort: str = "low",
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

    start = time.perf_counter()
    try:
        async with build_async_client(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(endpoint, headers=headers)
            # 200 体判废先于留痕（评审二轮 P3，内测 405 案形态）：Base URL 填成网站
            # 首页等场景函数裁定 endpoint_mismatch，留痕行不得与之相悖机械记 ok；
            # 仅 200 做体判废——非 200 的错误体（鉴权失败 JSON 等）过 _non_api_response
            # 会误报「返回了错误」
            not_api = _non_api_response(
                resp, _v1_hint(api_format, vendor_id)
            ) if resp.status_code == 200 else ""
            _log_probe(
                "models_list", vendor=vendor_id, api_format=api_format,
                url=endpoint, start=start, status=resp.status_code,
                result="endpoint_mismatch" if not_api else None,
                error=not_api or None,
            )
            if resp.status_code == 404 and fallback is not None:
                # models 端点不存在 → 降级为「你好」最小生成探针（2026-10-05 拍板）。
                # 两格式同享降级（Gemini 官方 OpenAI 兼容层等无清单端点因此可用，
                # 2026-10-08 拍板）。payload 在此现解：404 时列表恒空，探针 id 链
                # ＝已选模型 > 候选首个 >（仅 anthropic）占位——存量分歧一并修齐
                # （原实现在 _build_probe 烤死占位 id，已选模型被无视）。openai 格式
                # 链尾不垫占位 id：凭空猜 id 对兼容端点是噪音，无 id 不降级、判负提示
                # 填写模型名。
                probe_model = _probe_model([], vendor_id, preferred_model)
                if not probe_model and api_format != "anthropic":
                    return {
                        "ok": False,
                        "status": "unknown",
                        "models": None,
                        "error": (
                            "该地址不提供模型列表（HTTP 404）且未填写模型名称——"
                            "请填写模型名称后重新测试"
                        ),
                    }
                probe = await _fallback_probe(
                    client,
                    fallback,
                    api_format,
                    vendor_id,
                    preferred_model,
                    thinking_enabled=thinking_enabled,
                    thinking_effort=thinking_effort,
                )
                if probe is not None:
                    return probe
                return {
                    "ok": True,
                    "status": "ok",
                    "models": [],
                    "error": None,
                    "candidates": model_candidates_for(vendor_id),
                    "note": no_model_list_note(api_format),
                }

            # 判定与探针必须全部在 client 存活期内执行——async with 退出即关，出块后
            # 再发请求会抛 RuntimeError（P0 回归钉：真 httpx 生命周期用例）
            if resp.status_code in (401, 403):
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

            if not_api:
                # 200 但体判废也可能是可用端点（网关对未知路径回首页，内测反馈#1 残余
                # ——ccswitch 类中转站对 /models 回 200 网页、对话接口正常）：与 404
                # 同享降级探对话接口，探通即放行（该端点不提供清单，按无清单端点口径
                # 返回空清单＋说明）；探不通（真网页站的对话接口也 HTML/不存在）保留
                # 判废原文案。探针 id 同 404 口径：无 id 的 openai 格式不降级。
                if fallback is not None:
                    probe_model = _probe_model([], vendor_id, preferred_model)
                    if probe_model or api_format == "anthropic":
                        probe = await _fallback_probe(
                            client,
                            fallback,
                            api_format,
                            vendor_id,
                            preferred_model,
                            thinking_enabled=thinking_enabled,
                            thinking_effort=thinking_effort,
                        )
                        if probe is None:
                            return {
                                "ok": True,
                                "status": "ok",
                                "models": [],
                                "error": None,
                                "candidates": model_candidates_for(vendor_id),
                                "note": no_model_list_note(api_format),
                            }
                return {
                    "ok": False,
                    "status": "endpoint_mismatch",
                    "models": None,
                    "error": not_api,
                }
            models = extract_fn(resp)
            # 「你好」最小生成探针（2026-10-05 拍板，双格式统一判据）：与生成同址同头
            # ——openai {base}/chat/completions／anthropic {base}/v1/messages
            probe_model = _probe_model(models, vendor_id, preferred_model)
            if api_format == "openai" and vendor_id != "ollama":
                if not probe_model:
                    # 无任何可用模型 id：仅凭可达性/鉴权不算通（2026-10-05 拍板）
                    return {
                        "ok": False,
                        "status": "unknown",
                        "models": None,
                        "error": "模型列表为空且无候选模型 id——请填写模型名称后重新测试",
                    }
                ping = await _probe_generation(
                    client,
                    # 与 models 探测/生成调用同源归一（裸域名补 /v1）——中转站
                    # 网页壳对非 /v1 路径回 200 网页，裸拼会把探针打到网页上
                    # （2026-10-09 kakou 案 llm.log 实锤）
                    f"{normalize_openai_base(base_url)}/chat/completions",
                    headers,
                    _generation_payload(
                        probe_model,
                        thinking_enabled=thinking_enabled,
                        thinking_effort=thinking_effort,
                    ),
                    _openai_reply_text,
                    vendor=vendor_id,
                    api_format=api_format,
                )
                if ping is not None:
                    # 探针失败仍带回已提取的清单（评审 P1：手填错 id 的自恢复闭环——
                    # 落库后书内选择面板立刻有正确候选可选，不必删配置重建）
                    return {**ping, "models": models}
            elif api_format == "anthropic" and fallback is not None:
                f_url, f_headers, f_reply = fallback
                ping = await _probe_generation(
                    client,
                    f_url,
                    f_headers,
                    _generation_payload(
                        probe_model or _ANTHROPIC_PROBE_MODEL,
                        thinking_enabled=thinking_enabled,
                        thinking_effort=thinking_effort,
                    ),
                    f_reply,
                    vendor=vendor_id,
                    api_format=api_format,
                )
                if ping is not None:
                    return {**ping, "models": models}
            return {"ok": True, "status": "ok", "models": models, "error": None}
    except httpx.TimeoutException:
        _log_probe(
            "models_list", vendor=vendor_id, api_format=api_format,
            url=endpoint, start=start, status=0, result="timeout",
        )
        return {"ok": False, "status": "timeout", "models": None, "error": "连接超时"}
    except httpx.ConnectError as exc:
        _log_probe(
            "models_list", vendor=vendor_id, api_format=api_format,
            url=endpoint, start=start, status=0, result="network_error",
            error=str(exc),
        )
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": "无法连接服务器",
        }
    except httpx.RequestError as exc:
        _log_probe(
            "models_list", vendor=vendor_id, api_format=api_format,
            url=endpoint, start=start, status=0, result="network_error",
            error=str(exc),
        )
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": f"网络错误: {exc}",
        }


async def fetch_models(
    vendor_id: str,
    api_key: str,
    base_url: str,
    api_format: str = "openai",
    timeout: int = CONNECTION_TEST_TIMEOUT,
) -> dict[str, Any]:
    """只拉清单轻探针（c-api-config-auto-models）：复用连接测试的端点/请求头构造，
    仅 GET 模型清单端点，**不发对话探针**（零生成调用）——表单「Key 失焦自动拉清单」用。

    与 test_connection 的关键差异：anthropic 格式 models 端点 404 时**不发生成请求**，
    直接返回空清单＋该 vendor 候选＋说明（手填兜底的入口数据）。失败语义与测试路径同口径
    （鉴权/限流/服务端错误/网络错误/网页判废），但不做「无模型 id 不算通」判定——
    这里只回答「清单是什么」，不回答「连接能不能用」。
    """
    requires_key = vendor_id != "ollama"
    if requires_key and not api_key.strip():
        return {
            "ok": False,
            "status": "auth_error",
            "models": None,
            "error": "API Key 为空，请填写后再获取",
        }

    endpoint, headers, extract_fn, _unused_fallback = _build_probe(
        api_format, vendor_id, api_key, base_url
    )

    start = time.perf_counter()
    try:
        async with build_async_client(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(endpoint, headers=headers)
            # 体判废先于留痕（评审二轮 P3，同 test_connection）
            not_api = _non_api_response(
                resp, _v1_hint(api_format, vendor_id)
            ) if resp.status_code == 200 else ""
            _log_probe(
                "models_list", vendor=vendor_id, api_format=api_format,
                url=endpoint, start=start, status=resp.status_code,
                result="endpoint_mismatch" if not_api else None,
                error=not_api or None,
            )
            # 「端点不提供清单」的 404 特判只限 anthropic 格式（与 test_connection 的
            # fallback 判据同源）——openai/ollama 格式的 404 更常见成因是 Base URL 路径
            # 填错，按异常响应报错并提示核对，不误诊为「无清单端点」（评审 P1）
            if resp.status_code == 404 and api_format == "anthropic":
                return {
                    "ok": True,
                    "status": "ok",
                    "models": [],
                    "error": None,
                    "candidates": model_candidates_for(vendor_id),
                    "note": no_model_list_note("anthropic"),
                }
            if resp.status_code in (401, 403):
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
            if not_api:
                return {
                    "ok": False,
                    "status": "endpoint_mismatch",
                    "models": None,
                    "error": not_api,
                }
            models = extract_fn(resp)
            return {"ok": True, "status": "ok", "models": models, "error": None}
    except httpx.TimeoutException:
        _log_probe(
            "models_list", vendor=vendor_id, api_format=api_format,
            url=endpoint, start=start, status=0, result="timeout",
        )
        return {"ok": False, "status": "timeout", "models": None, "error": "连接超时"}
    except httpx.ConnectError as exc:
        _log_probe(
            "models_list", vendor=vendor_id, api_format=api_format,
            url=endpoint, start=start, status=0, result="network_error",
            error=str(exc),
        )
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": "无法连接服务器",
        }
    except httpx.RequestError as exc:
        _log_probe(
            "models_list", vendor=vendor_id, api_format=api_format,
            url=endpoint, start=start, status=0, result="network_error",
            error=str(exc),
        )
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": f"网络错误: {exc}",
        }


# ── Protocol-based probe builder ────────────────────────────────────────────


# 「路径已含版本段」判据：段以 v+数字开头即算（/v1、/v4、/v1beta…）——行尾锚定
# /v\d+$ 会漏掉版本段在中段的形态（Gemini 官方兼容层 …/v1beta/openai 被误判
# 「无版本段」而追补出 …/v1beta/openai/v1/… 死址）
_VERSION_SEG = re.compile(r"/v\d+[a-z]*(/|$)")


def normalize_openai_base(base: str) -> str:
    """OpenAI 格式 base 的版本段归一——「与生成调用同源推导」的单源实现。

    models 探测、对话探针（主链＋404 降级）、生成调用（ai_client 传给 OpenAI SDK
    的 base）四处共用：裸域名（路径无任何版本段）按 OpenAI 官方惯例补 /v1，自带
    版本段的（/v1、/v4、compatible-mode/v1、Gemini 兼容层 /v1beta/openai）原样
    保留。2026-10-09 kakou 中转案实锤：SPA 网页壳对任意非 /v1 路径回 200 网页——
    只有 models 探测补 /v1 时清单拉得到，对话探针/生成却打到网页上，呈现
    「清单绿、测试红」半通形态；且 SDK 直传裸 base 生成必败，探针必须与生成
    同一归一，否则修出「测试绿、写作红」的假通。anthropic 格式不适用（惯例
    相反：SDK 自拼 /v1/messages）；落库值不改写，归一只在构造请求时发生。
    """
    base = base.rstrip("/")
    if not base or _VERSION_SEG.search(base):
        return base
    return f"{base}/v1"


def _openai_models_url(base: str) -> str:
    """OpenAI 格式探测端点：统一经版本段归一后拼 /models。"""
    return f"{normalize_openai_base(base)}/models"


def _build_probe(
    api_format: str, vendor_id: str, api_key: str, base_url: str
) -> tuple[
    str,
    dict[str, str],
    Any,
    tuple[str, dict[str, str], Any] | None,
]:
    """Return (endpoint_url, headers, response_extractor, auth_fallback).

    auth_fallback = (url, headers, reply_fn)：models 端点 404 时的降级探活请求
    （两格式同享）。探针 payload 不在此构造——id 链需 preferred_model 与候选，
    由 test_connection 在 404 分支按 `_probe_model([], vendor, preferred)` 现解；
    openai 格式无 id 时调用方判负不降级。
    """
    base = base_url.rstrip("/")

    # ollama 特例：本地服务、免 Key、自有 tags 端点，不按任一协议探测。
    # 一律打用户填的 base（裸填/空＝官方默认 11434）——旧实现见 "localhost" 就硬替
    # 11434，自定义端口（如 http://localhost:12345）被打去错端口（评审 P2 实锤）。
    # 登记预填值为 …/v1（SDK 生成调用需版本段），此处剥掉防打去 /v1/api/tags
    if vendor_id == "ollama":
        return (
            f"{base.removesuffix('/v1') or 'http://localhost:11434'}/api/tags",
            {},
            _extract_ollama_models,
            None,
        )

    if api_format == "anthropic":
        # Anthropic SDK 惯例：base 不带 /v1（SDK 自拼 /v1/messages），
        # 用户粘贴以 /v1 结尾的 base 时先剥防双拼
        base = base.removesuffix("/v1")
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        fallback = (f"{base}/v1/messages", dict(headers), _anthropic_reply_text)
        return f"{base}/v1/models", headers, _extract_openai_models, fallback

    # openai 格式（OpenAI 官方 / DeepSeek / GLM / Kimi / Qwen / 兼容端点）：
    # 404 同享降级（Gemini 官方 OpenAI 兼容层 /v1beta/openai 等无清单端点）
    return (
        _openai_models_url(base),
        {"Authorization": f"Bearer {api_key}"},
        _extract_openai_models,
        (
            # 降级地址同走版本段归一（与 models 探测/主链对话探针/生成调用同源）
            f"{normalize_openai_base(base)}/chat/completions",
            {"Authorization": f"Bearer {api_key}"},
            _openai_reply_text,
        ),
    )


# ── 「通」的判据组件：非 API 响应识别 / 对话路径探针 ──────────────────────────


def _v1_hint(api_format: str, vendor: str = "") -> str:
    """网页体误判文案的补救出口：仅 openai 兼容格式给「补 /v1」指引（评审 2026-10-09）。

    anthropic 惯例 base 不带 /v1（探针侧会把结尾 /v1 剥掉，补了是空操作）；
    ollama tags 探针同样剥 /v1——两者不出该指引。"""
    if api_format == "openai" and vendor != "ollama":
        return "（若地址确认无误，尝试在末尾补 /v1）"
    return ""


def _non_api_response(resp: httpx.Response, v1_hint: str = "") -> str:
    """200 响应但体不是 API JSON → 返回给用户的说明；是 JSON 则返回空串。

    典型：Base URL 填成网站首页，SPA 对任意路径回 200 HTML——旧实现按 200 判
    「连接正常」，坏配置到生成期才炸（内测 405 案）。v1_hint＝openai 格式专属
    补救出口（_v1_hint 按格式/vendor 分流）。
    """
    ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    try:
        body = resp.json()
    except (ValueError, TypeError):
        return (
            "该地址返回的不是 API 数据"
            + (f"（Content-Type: {ctype}）" if ctype else "")
            + "——看起来像网页。请检查 Base URL 是否填成了网站地址"
            + v1_hint
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


def _generation_payload(
    model: str,
    thinking_enabled: bool = False,
    thinking_effort: str = "low",
) -> dict[str, Any]:
    """「你好」最小生成探针请求体（双格式同形）：思考参数按配置＋短输出预算。

    开（c-thinking-config）＝thinking:{type:enabled}＋reasoning_effort（GLM-5.3 契约
    顶层参数，low/high/max）；关（默认）＝现状 disabled。思考开启时预算放大——
    推理会吃 max_tokens，32 可能只见思考不见正文。"""
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": _PROBE_PROMPT}],
        "max_tokens": _PROBE_MAX_TOKENS_THINKING if thinking_enabled else _PROBE_MAX_TOKENS,
        "thinking": {"type": "enabled"} if thinking_enabled else dict(_THINKING_DISABLED),
    }
    if thinking_enabled:
        payload["reasoning_effort"] = thinking_effort or "low"
    return payload


async def _fallback_probe(
    client: httpx.AsyncClient,
    fallback: tuple[str, dict[str, str], Any],
    api_format: str,
    vendor_id: str,
    preferred_model: str | None,
    thinking_enabled: bool = False,
    thinking_effort: str = "low",
) -> dict[str, Any] | None:
    """models 端点判废（404 缺失／200 非 API 体）后的降级「你好」探针。

    返回 None＝探通；dict＝探针失败形态（由调用方按其判废语义处置）。探针 id 链
    现解（列表在判废路径恒空）：已选模型 > 候选首个 >（仅 anthropic）占位 id——
    调用方 SHALL 先判 id 可用性（无 id 的 openai 不降级）。
    """
    f_url, f_headers, f_reply = fallback
    probe_model = _probe_model([], vendor_id, preferred_model)
    return await _probe_generation(
        client,
        f_url,
        f_headers,
        _generation_payload(
            probe_model or _ANTHROPIC_PROBE_MODEL,
            thinking_enabled=thinking_enabled,
            thinking_effort=thinking_effort,
        ),
        f_reply,
        vendor=vendor_id,
        api_format=api_format,
    )


async def _probe_generation(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    reply_fn: Any,
    vendor: str = "",
    api_format: str = "",
) -> dict[str, Any] | None:
    """最小生成探针（2026-10-05 拍板）：发一条「你好」，收到格式正确且含可见回复文本
    的回复才算通（reply_fn 按对应契约提取回复文本）。

    返回 None = 通过；非 2xx、体不符格式、空回复一律判失败（400/422 类业务性拒绝
    不再放行——点名所试模型 id），失败形态 dict = 直接作为连接测试结果返回。
    """
    model = payload.get("model", "")
    start = time.perf_counter()
    try:
        resp = await _post_with_thinking_retry(
            client, url, headers, payload,
            vendor=vendor, api_format=api_format, model=model,
        )
    except httpx.TimeoutException:
        _log_probe(
            "generation_probe", vendor=vendor, api_format=api_format,
            url=url, start=start, model=model, result="timeout",
        )
        return {
            "ok": False,
            "status": "timeout",
            "models": None,
            "error": "对话探针超时（连接超时）",
        }
    except httpx.RequestError as exc:
        _log_probe(
            "generation_probe", vendor=vendor, api_format=api_format,
            url=url, start=start, model=model, result="network_error",
            error=str(exc),
        )
        return {
            "ok": False,
            "status": "network_error",
            "models": None,
            "error": f"网络错误: {exc}",
        }
    verdict = _probe_verdict(
        resp, url, model, reply_fn, v1_hint=_v1_hint(api_format, vendor)
    )
    _log_probe(
        "generation_probe", vendor=vendor, api_format=api_format,
        url=url, start=start, model=model, status=resp.status_code,
        result=verdict["status"] if verdict else "ok",
        error=verdict["error"] if verdict else None,
    )
    return verdict


def _probe_verdict(
    resp: httpx.Response, url: str, model: str, reply_fn: Any, v1_hint: str = ""
) -> dict[str, Any] | None:
    """生成探针的响应判定（无副作用纯判定）：None = 通过；否则失败形态 dict。

    v1_hint＝网页体误判文案的格式分流出口（openai 兼容格式才有，见 _v1_hint）。"""
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
                f"对话接口不可达（HTTP {resp.status_code} @ {url}）——请核对 Base URL "
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
    not_api = _non_api_response(resp, v1_hint)
    if not_api:
        return {
            "ok": False,
            "status": "endpoint_mismatch",
            "models": None,
            "error": not_api,
        }
    if not reply_fn(resp):
        return {
            "ok": False,
            "status": "unknown",
            "models": None,
            "error": (
                f"模型回复格式不正确或回复为空（@ {url}）——所试模型 {model}，"
                "请核对模型 id 与接口格式"
            ),
        }
    return None


def _is_thinking_rejection_text(text: str) -> bool:
    """错误文案是否在说思考参数（选哪份 400 展示用，不决定是否重试）。

    判据含中文「思考」：GLM-5.3 拒关思考的报错是纯中文（「该模型始终思考，不支持
    关闭思考」），按英文字样判会漏。"""
    low = (text or "").lower()
    return "thinking" in low or "思考" in text or "reasoning" in low


def _has_thinking_params(payload: dict[str, Any]) -> bool:
    return "thinking" in payload or "reasoning_effort" in payload


async def _post_with_thinking_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    vendor: str = "",
    api_format: str = "",
    model: str = "",
) -> httpx.Response:
    """POST 最小生成探针；端点 400 且请求带思考参数时去参重试一次（ai_client 同款约定）。

    触发不看错误文案措辞（GLM-5.3 实锤：拒「关思考」的报错纯中文，文案匹配会漏判，
    用户配 GLM 的连接测试全挂在 400——c-thinking-config 定诊）；探针是一次性用户动作，
    多一次请求换判稳，值。去参时预算同步放大（去参后强制思考模型会把预算花在推理上）。
    两次都 400 时回更贴切的那份：原始 400 若在说思考参数、重试 400 说了别的真因，
    回重试的；否则回原始（原始文案更能代表配置的问题）。
    被拒的首个请求落一行 llm_probe（result=thinking_rejected，评审 P2：c-llm-call-log
    的「每个出网请求一行」不变量——重试不该制造 llm.log 里的隐身请求）。"""
    start = time.perf_counter()
    resp = await client.post(url, headers=headers, json=payload)
    if resp.status_code != 400 or not _has_thinking_params(payload):
        return resp
    _log_probe(
        "generation_probe", vendor=vendor, api_format=api_format, url=url,
        start=start, model=model, status=resp.status_code,
        result="thinking_rejected", error=_extract_error_detail(resp),
    )
    stripped = {
        k: v for k, v in payload.items() if k not in ("thinking", "reasoning_effort")
    }
    if stripped.get("max_tokens", 0) < _PROBE_MAX_TOKENS_THINKING:
        stripped["max_tokens"] = _PROBE_MAX_TOKENS_THINKING
    retry = await client.post(url, headers=headers, json=stripped)
    if retry.status_code == 400 and not _is_thinking_rejection_text(
        getattr(resp, "text", "") or ""
    ):
        return resp
    return retry


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
