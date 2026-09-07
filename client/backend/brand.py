"""品牌单源读取（brand-name-single-source）。

仓库根 brand/brand.json 是全仓品牌唯一声明处；本模块是 python 侧唯一入口。
定位顺序：RESOURCE_ROOT 环境变量（pywebview_app.start_server 注入）→ 冻结包
资源根双候选（onedir _internal / macOS .app Resources，与 get_resource_root 同款）
→ dev 仓库根。纪律：任何定位/读取/解析失败一律静默回落内置默认，绝不抛——
启动路径上（窗口标题、splash）品牌文件缺失 MUST NOT 阻塞应用（v0.15 教训）。
内置默认 MUST 与 brand.json 声明值一致（tests/test_brand.py 防漂移断言）。
"""

import json
import os
import sys
from pathlib import Path

# 与 brand/brand.json 逐键同值；改名只改 json，本表仅作文件缺失时的兜底
_DEFAULTS = {
    "name": "爱小说",
    "nameEn": "AI Novel",
    "mark": "爱",
    "tagline": "AI 辅助长篇小说写作",
}

_KEYS = ("name", "nameEn", "mark", "tagline")


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_root = os.environ.get("RESOURCE_ROOT")
    if env_root:
        dirs.append(Path(env_root))
    # 模块同目录（docker 等扁平布局：backend 与 brand.json 同层时直接命中）
    dirs.append(Path(__file__).resolve().parent)
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", "."))
        dirs.append(base)
        dirs.append(base.parent / "Resources")
    else:
        # Dev：client/backend/brand.py → 仓库根；扁平布局（/app/brand.py）祖先不足
        # 时越界，静默跳过——定位失败一律回落默认，绝不抛（启动路径纪律）
        try:
            dirs.append(Path(__file__).resolve().parents[2])
        except IndexError:
            pass
    return dirs


def _brand_files() -> list[Path]:
    # 冻结包 datas 落资源根（brand.json）；dev 布局为仓库根 brand/brand.json
    files: list[Path] = []
    for d in _candidate_dirs():
        files.append(d / "brand.json")
        files.append(d / "brand" / "brand.json")
    return files


def _load() -> dict:
    for path in _brand_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(raw, dict):
            continue
        # 白名单逐键取值：缺失或非字符串回落默认，绝不因脏数据抛异常
        return {k: raw[k] if isinstance(raw.get(k), str) and raw[k].strip() else _DEFAULTS[k] for k in _KEYS}
    return dict(_DEFAULTS)


_loaded = _load()

BRAND_NAME: str = _loaded["name"]
BRAND_NAME_EN: str = _loaded["nameEn"]
BRAND_MARK: str = _loaded["mark"]
BRAND_TAGLINE: str = _loaded["tagline"]
