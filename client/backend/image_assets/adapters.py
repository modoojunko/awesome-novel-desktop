"""图像供应商适配层（c-image-generation）。

三套 wire：
- OpenAI images 形态：火山 Seedream / 智谱 CogView / OpenAI / OpenAI 兼容
- DashScope multimodal-generation：阿里云百炼 Qwen-Image
- MiniMax image_generation

纪律：
- 全部出网走 ``http_client.build_async_client``（晚绑定 + kwargs 透传）。
- 日志只写 host/path/model/status/duration/result；失败时另记供应商错误体的
  code/message/param 字段子集（c-image-volc-size-contract）。绝不写 Key、prompt、图片字节。
- 供应商 URL 只允许 http(s)、不跟重定向、≤10MB；b64 与 URL 两种回包都收敛成字节。
- 错误统一 ``ImageProviderError(kind)``：auth/quota/rate_limit/moderation/timeout/
  network/invalid/empty。上游 5xx 归 network（本地图像是同步调用，重试策略由任务层管）。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import ipaddress
import logging
import os
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from http_client import build_async_client

logger = logging.getLogger("image_gen")

ERROR_KINDS = {
    "auth", "quota", "rate_limit", "moderation", "timeout",
    "network", "invalid", "empty",
}
DEFAULT_TIMEOUT_SECONDS = float(os.environ.get("IMAGE_GENERATION_TIMEOUT", "300"))
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024


class ImageProviderError(Exception):
    """供应商调用失败。kind 属于 ERROR_KINDS；message 可直接给任务层展示。"""

    def __init__(self, kind: str, message: str, status: int | None = None):
        if kind not in ERROR_KINDS:
            kind = "invalid"
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status


@dataclass(slots=True)
class ImageGenerationSpec:
    """一次供应商调用的 canonical request（能力裁剪后的 effective request）。"""

    provider: str
    model: str
    prompt: str
    negative_prompt: str
    kind: str  # cover | avatar | sketch
    n: int
    seed: int | None
    watermark: bool = False
    capabilities: dict[str, bool] | None = None


@dataclass(slots=True)
class GeneratedImage:
    data: bytes
    native_width: int | None
    native_height: int | None
    url: str | None = None


_BASE_CAPABILITIES: dict[str, dict[str, bool]] = {
    "volcengine": {"negative_supported": True, "seed_supported": True, "watermark_supported": True},
    "aliyun": {"negative_supported": True, "seed_supported": True, "watermark_supported": False},
    "zhipu": {"negative_supported": True, "seed_supported": True, "watermark_supported": False},
    "openai": {"negative_supported": False, "seed_supported": False, "watermark_supported": False},
    "minimax": {"negative_supported": False, "seed_supported": True, "watermark_supported": False},
    "openai-compat": {"negative_supported": True, "seed_supported": True, "watermark_supported": False},
}


def capabilities_for(provider: str, declared: dict | None = None) -> dict[str, bool]:
    caps = dict(_BASE_CAPABILITIES.get(provider, _BASE_CAPABILITIES["openai-compat"]))
    if provider == "openai-compat" and isinstance(declared, dict):
        for key in caps:
            if key in declared:
                caps[key] = bool(declared[key])
    return caps


def _normalize_base(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ImageProviderError("invalid", "Base URL 未配置")
    if not base.startswith(("http://", "https://")):
        base = f"https://{base}"
    return base


def _host_path(url: str) -> str:
    try:
        u = urlsplit(url)
        return f"{u.hostname or '?'}{u.path or '/'}"
    except ValueError:
        return "<malformed>"


def _text_of(payload: Any) -> str:
    try:
        import json

        return json.dumps(payload, ensure_ascii=False)[:1000]
    except Exception:  # noqa: BLE001 — 只用于错误归因
        return str(payload)[:1000]


def _error_detail(body: Any) -> str:
    """供应商错误体里可留痕的字段子集（code/message/param），绝不回显请求内容。"""
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            parts = [str(err[k]) for k in ("code", "message", "param") if err.get(k)]
            if parts:
                return " ".join(parts)
        for key in ("error", "message"):
            if isinstance(body.get(key), str):
                return body[key]
    return ""


def _classify_payload(status: int, text: str) -> ImageProviderError:
    low = text.lower()
    if status in (401, 403):
        return ImageProviderError("auth", "供应商拒绝访问：API Key 无效或无权限", status)
    if status == 402 or "quota" in low or "insufficient" in low or "balance" in low:
        return ImageProviderError("quota", "供应商账户额度不足", status)
    if status == 429:
        return ImageProviderError("rate_limit", "供应商限流，请稍后重试", status)
    if (
        "content_policy" in low or "content policy" in low
        or "content filter" in low or "moderation" in low
        or "敏感" in text or "违规" in text
    ):
        return ImageProviderError("moderation", "图片提示词被供应商内容策略拒绝", status)
    if status >= 500:
        return ImageProviderError("network", "供应商服务异常，请稍后重试", status)
    return ImageProviderError("invalid", f"供应商返回错误（HTTP {status}）", status)


def _native_size(provider: str, kind: str) -> tuple[str, int | None, int | None]:
    if provider == "volcengine":
        # Ark 只收 WIDTHxHEIGHT 像素写法且面积 ≥921600 px²（比例字符串/768x1024 均 400
        # InvalidParameter，2026-10-24 实测）；960x1280 为实测 200 的最小合规 3:4。
        return ("960x1280", 960, 1280) if kind != "avatar" else ("1024x1024", 1024, 1024)
    if provider == "zhipu":
        return ("864x1152", 864, 1152) if kind != "avatar" else ("1024x1024", 1024, 1024)
    if provider == "openai":
        return ("1024x1536", 1024, 1536) if kind != "avatar" else ("1024x1024", 1024, 1024)
    if provider == "aliyun":
        return ("1728*2368", 1728, 2368) if kind != "avatar" else ("2048*2048", 2048, 2048)
    if provider == "minimax":
        return ("3:4", 768, 1024) if kind != "avatar" else ("1:1", 1024, 1024)
    # OpenAI 兼容口中转站差异大：给最通用的尺寸字符串，由后置 normalize 收敛。
    return ("1024x1536", 1024, 1536) if kind != "avatar" else ("1024x1024", 1024, 1024)


def _openai_ish_payload(spec: ImageGenerationSpec, provider: str) -> tuple[str, dict]:
    size, _, _ = _native_size(provider, spec.kind)
    payload: dict[str, Any] = {
        "model": spec.model,
        "prompt": spec.prompt,
        "size": size,
        "n": spec.n,
    }
    caps = spec.capabilities or capabilities_for(provider)
    if provider == "volcengine":
        payload["response_format"] = "b64_json"
        payload["watermark"] = spec.watermark
    if caps["seed_supported"] and spec.seed is not None:
        payload["seed"] = spec.seed
    if caps["negative_supported"] and spec.negative_prompt:
        # OpenAI images 官方口无 negative；火山/智谱同样以 prompt 拼接为最稳口径。
        payload["prompt"] = f"{spec.prompt}\n避免出现：{spec.negative_prompt}"
    return "/images/generations", payload


def _dashscope_payload(spec: ImageGenerationSpec) -> tuple[str, dict]:
    size, _, _ = _native_size("aliyun", spec.kind)
    parameters: dict[str, Any] = {"size": size, "n": spec.n}
    caps = spec.capabilities or capabilities_for("aliyun")
    if caps["seed_supported"] and spec.seed is not None:
        parameters["seed"] = spec.seed
    if caps["negative_supported"] and spec.negative_prompt:
        parameters["negative_prompt"] = spec.negative_prompt
    return "/services/aigc/multimodal-generation/generation", {
        "model": spec.model,
        "input": {"messages": [{"role": "user", "content": [{"text": spec.prompt}]}]},
        "parameters": parameters,
    }


def _minimax_payload(spec: ImageGenerationSpec) -> tuple[str, dict]:
    size, _, _ = _native_size("minimax", spec.kind)
    caps = spec.capabilities or capabilities_for("minimax")
    payload: dict[str, Any] = {
        "model": spec.model,
        "prompt": spec.prompt,
        "aspect_ratio": size,
        "response_format": "base64",
    }
    if caps["seed_supported"] and spec.seed is not None:
        payload["seed"] = spec.seed
    if caps["negative_supported"] and spec.negative_prompt:
        payload["negative_prompt"] = spec.negative_prompt
    return "/image_generation", payload


def _walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _decode_b64(value: str) -> bytes:
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ImageProviderError("invalid", "供应商返回的图片数据无法解码") from e
    if not data:
        raise ImageProviderError("empty", "供应商返回空图片")
    return data


def _validate_download_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
    except ValueError as e:
        raise ImageProviderError("invalid", "供应商返回非法图片链接") from e
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImageProviderError("invalid", "供应商返回非法图片链接")
    if "@" in url or parsed.username or parsed.password:
        raise ImageProviderError("invalid", "供应商图片链接带凭据，已拒绝")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
        if not ip.is_global:
            raise ImageProviderError("invalid", "供应商图片链接指向内网地址，已拒绝")
    except ValueError:
        pass  # 域名交给 _assert_public_download_host 解析后再判
    if parsed.hostname in ("localhost", "localhost.localdomain"):
        raise ImageProviderError("invalid", "供应商图片链接指向本机，已拒绝")


async def _resolve_host(host: str, port: int) -> list[str]:
    """异步 DNS 解析（独立函数便于测试桩）；返回所有 A/AAAA 地址。"""
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM,
    )
    return [str(info[4][0]) for info in infos]


async def _assert_public_download_host(url: str) -> None:
    """域名解析后再判内网：只查 IP 字面量会被 ``foo.localhost``/``nip.io`` 绕过。

    解析失败不在此拒绝（交给 HTTP 层按 network 归因）；任一解析结果非 global
    （私网/回环/链路本地/保留/多播/CGNAT）即拒绝。DNS rebinding 的 TOCTOU 残余
    面由「禁重定向 + 单次解析」收敛，真机如需更严可换 pinning 客户端。
    """
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if not host:
        raise ImageProviderError("invalid", "供应商返回非法图片链接")
    try:
        ipaddress.ip_address(host)
        return  # 字面量已由 _validate_download_url 校验
    except ValueError:
        pass
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as e:
        raise ImageProviderError("invalid", "供应商返回非法图片链接") from e
    try:
        addresses = await _resolve_host(host, port)
    except (socket.gaierror, OSError):
        return
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw.split("%", 1)[0])
        except ValueError:
            continue
        if not ip.is_global:
            raise ImageProviderError("invalid", "供应商图片链接指向内网地址，已拒绝")


async def _download(client: httpx.AsyncClient, url: str, width: int | None, height: int | None) -> GeneratedImage:
    _validate_download_url(url)
    await _assert_public_download_host(url)
    resp = await client.get(url, follow_redirects=False)
    if resp.status_code != 200:
        raise _classify_payload(resp.status_code, resp.text[:500])
    if (resp.headers.get("content-type") or "").split(";", 1)[0].strip() not in (
        "image/png", "image/jpeg", "image/webp", "application/octet-stream",
    ):
        raise ImageProviderError("invalid", "供应商图片链接返回非图片内容")
    if len(resp.content) > MAX_DOWNLOAD_BYTES:
        raise ImageProviderError("invalid", "供应商图片超过 10MB")
    if not resp.content:
        raise ImageProviderError("empty", "供应商返回空图片")
    return GeneratedImage(resp.content, width, height)


def _collect_payload_images(payload: Any, width: int | None, height: int | None) -> list[GeneratedImage]:
    """按响应出现顺序收敛 b64/URL；URL 先占位，由调用方统一下载。"""
    out: list[GeneratedImage] = []
    seen_urls: set[str] = set()
    for obj in _walk_dicts(payload):
        for key, value in obj.items():
            if value in (None, ""):
                continue
            lk = str(key).lower()
            if isinstance(value, str) and ("b64" in lk or "base64" in lk):
                out.append(GeneratedImage(_decode_b64(value), width, height))
            elif isinstance(value, list):
                for item in value:
                    if (
                        isinstance(item, str)
                        and item.startswith(("http://", "https://"))
                        and "url" in lk
                        and item not in seen_urls
                    ):
                        seen_urls.add(item)
                        out.append(GeneratedImage(b"", width, height, item))
            elif (
                isinstance(value, str)
                and ("url" in lk or "image" in lk)
                and value.startswith(("http://", "https://"))
                and value not in seen_urls
            ):
                seen_urls.add(value)
                out.append(GeneratedImage(b"", width, height, value))
    return out


async def generate_images(
    *, base_url: str, api_key: str, spec: ImageGenerationSpec,
) -> list[GeneratedImage]:
    """调用供应商并返回 ``spec.n`` 张以内的事实图片。"""
    if spec.provider not in _BASE_CAPABILITIES:
        raise ImageProviderError("invalid", f"未支持的图像供应商：{spec.provider}")
    if not spec.model:
        raise ImageProviderError("invalid", "图像模型未配置")
    if not api_key:
        raise ImageProviderError("auth", "图像配置缺少 API Key")
    base = _normalize_base(base_url)
    if spec.provider == "aliyun":
        path, payload = _dashscope_payload(spec)
    elif spec.provider == "minimax":
        path, payload = _minimax_payload(spec)
    else:
        path, payload = _openai_ish_payload(spec, spec.provider)
    url = f"{base}{path}"
    started = time.monotonic()
    status = 0
    result = "ok"
    produced = 0
    try:
        timeout = httpx.Timeout(connect=10.0, read=DEFAULT_TIMEOUT_SECONDS, write=60.0, pool=10.0)
        async with build_async_client(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            status = resp.status_code
            if status != 200:
                try:
                    body = resp.json()
                    text = _text_of(body)
                except Exception:  # noqa: BLE001 — 非 JSON 错误体也要归因
                    body = None
                    text = resp.text[:500]
                logger.warning(
                    "event=image_call_error provider=%s model=%s target=%s status=%s detail=%.500s",
                    spec.provider, spec.model, _host_path(url), status,
                    _error_detail(body) or text,
                )
                raise _classify_payload(status, text)
            try:
                body = resp.json()
            except Exception as e:
                raise ImageProviderError("invalid", "供应商返回非 JSON 内容", status) from e
            images = _collect_payload_images(body, *_native_size(spec.provider, spec.kind)[1:])
            out: list[GeneratedImage] = []
            for image in images:
                if image.url:
                    image = await _download(client, image.url, image.native_width, image.native_height)
                out.append(image)
            if not out:
                raise ImageProviderError("empty", "供应商未返回任何图片")
            produced = len(out[: spec.n])
            return out[: spec.n]
    except ImageProviderError as e:
        result = e.kind
        raise
    except httpx.TimeoutException as e:
        result = "timeout"
        raise ImageProviderError("timeout", "图像生成超时，请稍后重试") from e
    except httpx.ConnectError as e:
        result = "network"
        raise ImageProviderError("network", "无法连接图像供应商") from e
    except httpx.RequestError as e:
        result = "network"
        raise ImageProviderError("network", "图像供应商网络请求失败") from e
    finally:
        logger.info(
            "event=image_call provider=%s model=%s target=%s status=%s duration_ms=%d result=%s images=%d",
            spec.provider, spec.model, _host_path(url), status,
            int((time.monotonic() - started) * 1000), result, produced,
        )


def variant_prompt(prompt: str, index: int, seed: int | None, seed_supported: bool) -> str:
    """无 seed 供应商的确定性变体：同一 prompt 不因候选数重复成同图请求。"""
    if seed_supported or index == 0:
        return prompt
    variants = (
        "构图变体一：主体略偏左，前景留出呼吸空间",
        "构图变体二：主体居中偏下，背景层次更强",
        "构图变体三：低角度视角，主体轮廓更清晰",
    )
    return f"{prompt}。{variants[index % len(variants)]}"
