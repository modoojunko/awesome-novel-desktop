"""Prompt loader — reads .prompt files from this directory.

**分层协议（用户 2026-09-27 定，逐模板独立、不做跨模板共享层）**：
每个 `.prompt` 文件用两行标记切成两段——
    `<<system>>` 角色＋永久约束＋优先级＋禁止项＋输出契约（同一功能每次调用**恒定不变**）
    `<<user>>`   每次调用动态替换的内容（设定素材/前文/本次任务/临时要求）
调用方用 `load_layers(name)` 取两段，分别送 `system=` 与 `messages[0].content`。
为什么恒定段必须单独成 system：① 供应商 prompt 缓存只认恒定前缀（省钱提速）；
② 永久约束不被几千字素材稀释；③ 每个功能可以独立调自己的 system，不被别的功能牵动。
过渡期：未分层的文件 `load_layers` 返回 `("", 全文)`（向后兼容），进度由回归测试
（`test_prompt_layering`）用名单跟踪，逐族清零。
"""

import os
import re

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Only allow safe prompt names — alphanumeric, underscores, hyphens
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

SYSTEM_MARK = "<<system>>"
USER_MARK = "<<user>>"


def load(name: str) -> str:
    """Load a prompt template by name (without .prompt extension).

    Raises ValueError if *name* contains unsafe characters (path traversal).
    """
    if not _SAFE_NAME_RE.match(name):
        raise ValueError(f"Invalid prompt name: {name!r}")
    # 纵深防御：解析后必须仍在 prompts 目录内（防路径穿越；对静态分析亦可证安全）
    path = os.path.realpath(os.path.join(_PROMPTS_DIR, f"{name}.prompt"))
    if os.path.dirname(path) != os.path.realpath(_PROMPTS_DIR):
        raise ValueError(f"Invalid prompt name: {name!r}")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _strip_comment_lines(text: str) -> str:
    """剥掉文件头的 `## ` 版本注释行（changelog 用，不入提示词）。"""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("##")):
        i += 1
    return "\n".join(lines[i:]).strip()


def is_layered(name: str) -> bool:
    """该模板是否已按分层协议拆好（两个标记都在）。"""
    raw = load(name)
    return SYSTEM_MARK in raw and USER_MARK in raw


def load_layers(name: str) -> tuple[str, str]:
    """分层加载 → (system, user)。

    未分层的文件返回 `("", 全文)`：迁移期向后兼容（调用方行为不变）。
    已分层的文件剥掉 `## ` 注释行后按标记切段；system 段里剩下的标记行一并去掉。
    """
    raw = load(name)
    if USER_MARK not in raw:
        return "", _strip_comment_lines(raw)
    head, _, tail = raw.partition(USER_MARK)
    system = _strip_comment_lines(head.replace(SYSTEM_MARK, ""))
    return system, _strip_comment_lines(tail)
