"""settings 相对路径 ↔ project_settings 表 key 的路由映射（纯函数零 IO）。

组合后端（ADR-001）按此映射把 settings 9 类路由到 DB，其余路径路由 LocalFileBackend。
key 用语义短名；字符目录按前缀 `character:`。
"""

# 单文件设定：相对路径 → DB key
# hooks 不在其中：伏笔已升级真表 novel_hooks（foreshadow-settings-v2），
# settings/hooks.yaml 通道整体退役（GET/PUT /settings/hooks 不再受理）。
PATH_TO_KEY = {
    "story.yaml": "story",
    "settings/world-setting.yaml": "world",
    "settings/writing-style.yaml": "style",
    "settings/anti-ai.yaml": "anti-ai",
    "settings/genre.yaml": "genre",
    "settings/ai-model.yaml": "ai-model",
    "settings/settings-status.yaml": "status",
}

CHARACTER_DIR = "settings/character-setting"
CHARACTER_PREFIX = "character:"  # DB key 前缀：character:{filename.yaml}

# threads.yaml → KV（PR④）：专用路由，不进 PATH_TO_KEY——否则会经 KEY_TO_PATH
# 泄漏进 settings 单文件端点白名单（SINGLE_FILE_TYPES），凭空多出 /settings/threads。
THREADS_PATH = "threads.yaml"
THREADS_KEY = "threads"

# 目录型设定：无单文件端点，/settings/{type} 泛化端点应拒绝（指引走 /character/{name} 等）
MULTI_FILE_SETTING_KEYS = {"characters"}

KEY_TO_PATH = {v: k for k, v in PATH_TO_KEY.items()}


def route_relative_path(relative_path: str) -> str | None:
    """settings/threads 相对路径 → DB key；其余路径返回 None（路由到 LocalFileBackend）。"""
    if relative_path in PATH_TO_KEY:
        return PATH_TO_KEY[relative_path]
    if relative_path == THREADS_PATH:
        return THREADS_KEY
    if relative_path.startswith(CHARACTER_DIR + "/"):
        return CHARACTER_PREFIX + relative_path[len(CHARACTER_DIR) + 1 :]
    return None


def is_character_dir(relative_path: str) -> bool:
    """字符目录本身（list_dir 特判入口）。"""
    return relative_path == CHARACTER_DIR
