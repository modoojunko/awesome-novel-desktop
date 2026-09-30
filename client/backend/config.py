# backend/config.py
"""本地应用配置 — C/S 架构"""

import os

# 数据目录
DATA_ROOT = os.environ.get("DATA_ROOT", "./data")
PROJECTS_DIR = os.path.join(DATA_ROOT, "projects")


def book_root(slug: str) -> str:
    """书级 root_path 单源：project_settings 的 KV 分区键，环境无关相对方案。

    三个建书入口（novels/service 建书、novels/router import_persist、
    backup/importer 备份导入）统一走这里——不取 DATA_ROOT 绝对路径，
    同一份库文件跨环境（本机/docker/演示栈）搬运时分区键不变。
    存量行不迁移：root_path 逐书独立、不透明，新旧格式混排互不影响。
    """
    return f"./data/{slug}"

# 数据库路径
# c-db-per-version：库文件名＝C端 版本（novel-v{版本}.db；dev/PR 构建＝固定哨兵名）
# —— 命名与版本比较单源在 schema_version.py；显式 DATABASE_URL 仍优先
# （测试 conftest 用独立库文件注入）
from schema_version import active_db_filename as _active_db_filename

DATABASE_URL = os.environ.get(
    "DATABASE_URL", f"sqlite+aiosqlite:///{DATA_ROOT}/{_active_db_filename()}"
)

# AI 配置（通过 C端 UI 配置，写入 config.json）

# 设定模板路径 — 相对于 config.py 的位置 (client/backend/config.py → reference/)。
# 只有 seed_settings_to_db 消费的 3 个 *.yaml.template；冻结包由 pywebview_app 注入 env 覆盖。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REFERENCE_DIR = os.environ.get(
    "REFERENCE_DIR", os.path.join(_THIS_DIR, "reference")
)

# S 端 CloudBase API 地址
SERVER_API_BASE = os.environ.get(
    "SERVER_API_BASE", "https://your-cloudbase-app.com/api"
)

# ── 发布期注入（打包链路专用）─────────────────────────────────────────
# CI 构建 exe/dmg 时把线上 S端 域名写成 release.json 放进资源目录并随包分发；
# 本地开发没有这个文件 → 以下读取永远返回 {}，行为与历史完全一致。
# 运行时优先级仍以 用户手工修改 > 环境变量 为先，见 pywebview_app.start_server。
RELEASE_OVERRIDE_KEYS = (
    "server_api_base",
    "server_api_fallback",
    "public_server_api",
    # client-update-notify：版本自报与更新检测地址（只读值，update_check 模块消费）
    "client_version",
    "client_update_url",
    "client_update_url_fallback",
    # c-version-build-info：构建信息（分支/commit 短串，只读值，build_info 模块消费；
    # 仅非 tag 构建烘入）。**白名单必含**——load_release_overrides 只返回本元组内的键，
    # 漏登记则打包链静默断链（评审 P0）
    "client_build_branch",
    "client_build_commit",
)


def load_release_overrides(resource_dir: str) -> dict:
    """读取资源目录下的 release.json，仅返回合法键的非空字符串值；文件缺失/损坏返回 {}。"""
    import json

    try:
        with open(os.path.join(resource_dir, "release.json"), "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: str(raw[k]).strip() for k in RELEASE_OVERRIDE_KEYS if str(raw.get(k) or "").strip()}
