from pathlib import Path

from config import REFERENCE_DIR

TEMPLATE_DIR = (
    Path(REFERENCE_DIR)
    if REFERENCE_DIR
    else (Path(__file__).resolve().parent.parent / "reference")
)

# settings 模板 → (相对路径, DB key)：只进 DB 不进盘（ADR-003）
# hooks 不在其中：伏笔已升级真表 novel_hooks（foreshadow-settings-v2），种子随之摘除。
# anti-ai 不在其中：禁用词已并入文风模板（banned-words-into-style）——保留种子会给
# 新书写空 anti-ai KV 行、误触发迁移存在性判定，故随面板一起退役。
SETTINGS_TEMPLATES = {
    "story.yaml.template": ("story.yaml", "story"),
    "world-setting.yaml.template": ("settings/world-setting.yaml", "world"),
    "writing-style.yaml.template": ("settings/writing-style.yaml", "style"),
}
