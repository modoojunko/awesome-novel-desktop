"""Prompt loader — reads .prompt files from this directory."""

import os
import re

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Only allow safe prompt names — alphanumeric, underscores, hyphens
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


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
