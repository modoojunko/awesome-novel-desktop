"""settings 相对路径 ↔ project_settings 表 key 的路由映射（纯函数零 IO）。

这些 `.yaml` 字符串是文件时代的键名，仅作 KV 路由键、永不落盘（c-retire-local-file-storage）：命中映射的路径进 project_settings KV，其余路径不经本映射——storage 读 `{}` 写 no-op。
key 用语义短名；字符目录按前缀 `character:`。
"""

# 单文件设定：相对路径 → DB key
# hooks 不在其中：伏笔已升级真表 novel_hooks（foreshadow-settings-v2），
# settings/hooks.yaml 通道整体退役（GET/PUT /settings/hooks 不再受理）。
# anti-ai 映射保留（banned-words-into-style）：面板/写端点已退役，但迁移函数要读
# 原键、导出/导入兜底与回滚安全都依赖它；清理属后续版本。
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

# style-quant（style-settings-v2）：量化层专用键，同 threads 先例——不进 PATH_TO_KEY
# （通用 /settings/{type} 天然拒绝），只走 settings/style_quant_router.py 专用端点；
# PUT 仅受理锁定切换，基线数值服务端只写（评审 P0：防表单整卡覆盖回踩只读基线）。
STYLE_QUANT_PATH = "settings/style-quant.yaml"
STYLE_QUANT_KEY = "style-quant"

# 目录型设定：无单文件端点，/settings/{type} 泛化端点应拒绝（指引走 /character/{name} 等）
MULTI_FILE_SETTING_KEYS = {"characters"}

KEY_TO_PATH = {v: k for k, v in PATH_TO_KEY.items()}


def route_relative_path(relative_path: str) -> str | None:
    """settings/threads 相对路径 → DB key；其余路径返回 None（storage 读 `{}` 写 no-op）。"""
    if relative_path in PATH_TO_KEY:
        return PATH_TO_KEY[relative_path]
    if relative_path == THREADS_PATH:
        return THREADS_KEY
    if relative_path == STYLE_QUANT_PATH:
        return STYLE_QUANT_KEY
    if relative_path.startswith(CHARACTER_DIR + "/"):
        return CHARACTER_PREFIX + relative_path[len(CHARACTER_DIR) + 1 :]
    return None


def is_character_dir(relative_path: str) -> bool:
    """字符目录本身（list_dir 特判入口）。"""
    return relative_path == CHARACTER_DIR
