import os
from pathlib import Path

from config import REFERENCE_DIR

TEMPLATE_DIR = (
    Path(REFERENCE_DIR)
    if REFERENCE_DIR
    else (Path(__file__).resolve().parent.parent / "reference")
)

# settings 模板 → (相对路径, DB key)：只进 DB 不进盘（ADR-003）
# hooks 不在其中：伏笔已升级真表 novel_hooks（foreshadow-settings-v2），种子随之摘除。
SETTINGS_TEMPLATES = {
    "story.yaml.template": ("story.yaml", "story"),
    "world-setting.yaml.template": ("settings/world-setting.yaml", "world"),
    "writing-style.yaml.template": ("settings/writing-style.yaml", "style"),
    "anti-ai.yaml.template": ("settings/anti-ai.yaml", "anti-ai"),
}


def _init_project_skeleton_local(root_path: str):
    """创建项目根目录（业务数据全量入库后，盘上不再铺任何骨架文件/子目录）。"""
    # Normalise path to prevent traversal outside the intended directory
    root_path = os.path.normpath(os.path.abspath(root_path))
    os.makedirs(root_path, exist_ok=True)
