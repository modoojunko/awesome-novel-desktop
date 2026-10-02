"""AI 反推编排：步骤 1（并行）+ 步骤 2（大纲）。"""

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger("app.backfill")

PROMPT_DIR = Path(__file__).parent.parent / "prompts"

# ── Prompt 加载 ──

_PROMPTS: dict[str, str] = {}


def _load_prompt(name: str) -> str:
    if name not in _PROMPTS:
        path = PROMPT_DIR / f"{name}.prompt"
        if path.exists():
            _PROMPTS[name] = path.read_text(encoding="utf-8")
        else:
            _PROMPTS[name] = ""
    return _PROMPTS[name]


# ── 工具函数 ──


async def _collect_prose(root_path: str) -> str:
    """收集所有章节正文（章族入库：DB 直查拼接）。"""
    from chapters.store import collect_prose_by_root

    return await collect_prose_by_root(root_path)


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数。"""
    return len(text)


def _truncate(text: str, max_chars: int = 50000) -> tuple[str, bool]:
    """截断超长文本，返回 (text, truncated)。"""
    if len(text) <= max_chars:
        return text, False
    # 保留最后 max_chars 字符 + 开头 500 字符作为梗概
    head = text[:500]
    tail = text[-max_chars:]
    return f"[全文梗概]\n{head}\n\n[主要正文]\n{tail}", True


async def _call_ai(prompt_name: str, context: str) -> str:
    """调用 AI 客户端。"""
    from prompts import load_layers

    # 分层协议（c-ai-material-audit 同期治理）：system/user 两段一起取——
    # 旧实现找 backfill_<name>_system（不存在）→ system 恒为空串的 bug 在此修复
    system, user = load_layers(f"backfill_{prompt_name}")
    # 拼接 context 到 user prompt
    full_prompt = f"{user}\n\n---\n{context[:30000]}"

    try:
        from ai_client import aio_ai_client

        result = await asyncio.wait_for(
            aio_ai_client.generate(
                system_prompt=system,
                messages=[{"role": "user", "content": full_prompt}],
                max_tokens=2048,
            ),
            timeout=90.0,
        )
        return result or ""
    except TimeoutError:
        logger.warning("AI backfill call timed out: %s", prompt_name)
        return ""
    except Exception as e:
        logger.warning("AI backfill call failed: %s — %s", prompt_name, e)
        return ""


# ── 步骤 1：三路并行 ──


async def step1_backfill(root_path: str, novel_id: str) -> dict:
    """三路并行 AI 调用，返回合并设定结果。"""
    # 1. 收集正文
    prose = await _collect_prose(root_path)
    if not prose.strip():
        return {
            "synopsis": "",
            "genre_profile": "",
            "world_setting": {},
            "writing_style": {},
            "characters": [],
            "truncated": False,
        }

    # 2. 截断
    context, truncated = _truncate(prose)

    # 3. 并行三路 AI
    async def call_synopsis() -> str:
        return await _call_ai("synopsis_world", context)

    async def call_style() -> str:
        return await _call_ai("style", context)

    async def call_characters() -> str:
        return await _call_ai("characters", context)

    results = await asyncio.gather(
        call_synopsis(), call_style(), call_characters(),
        return_exceptions=True,
    )

    # 4. 合并结果
    synopsis_raw = results[0] if isinstance(results[0], str) else ""
    style_raw = results[1] if isinstance(results[1], str) else ""
    chars_raw = results[2] if isinstance(results[2], str) else ""

    return {
        "synopsis": synopsis_raw[:500],
        "genre_profile": "",
        "world_setting": {"raw": style_raw[:2000]} if style_raw else {},
        "writing_style": {"raw": style_raw[:2000]} if style_raw else {},
        "characters": _parse_characters(chars_raw) if chars_raw else [],
        "truncated": truncated,
    }


def _parse_characters(text: str) -> list[dict]:
    """简单解析角色列表。"""
    chars = []
    for line in text.strip().split("\n"):
        line = line.strip().strip("-* ")
        if not line or "：" not in line and ":" not in line:
            continue
        sep = "：" if "：" in line else ":"
        name = line.split(sep)[0].strip()
        desc = line.split(sep, 1)[1].strip() if len(line.split(sep, 1)) > 1 else ""
        if name and len(name) < 20:
            chars.append({"name": name, "role": desc[:50], "description": desc[:200]})
    return chars


# ── 步骤 2：大纲生成 ──


async def step2_backfill(root_path: str, novel_id: str, step1_result: dict) -> dict:
    """基于步骤 1 的设定生成卷纲和章纲。"""
    context_parts = []
    if step1_result.get("synopsis"):
        context_parts.append(f"简介：{step1_result['synopsis']}")
    if step1_result.get("world_setting"):
        context_parts.append(f"设定：{step1_result['world_setting']}")
    if step1_result.get("characters"):
        context_parts.append(
            f"角色：{', '.join(c.get('name', '') for c in step1_result['characters'])}"
        )
    context = "\n".join(context_parts)

    raw = await _call_ai("outlines", context)
    return {
        "volume_outlines": _parse_volumes(raw) if raw else [],
        "chapter_outlines": [],
    }


def _parse_volumes(text: str) -> list[dict]:
    """简单解析卷结构。"""
    volumes = []
    current_vol = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("# "):
            if current_vol:
                volumes.append(current_vol)
            current_vol = {"title": line[2:], "chapters": []}
        elif line.startswith("## ") and current_vol is not None:
            current_vol["chapters"].append(
                {"title": line[3:], "summary": ""}
            )
    if current_vol:
        volumes.append(current_vol)
    return volumes
