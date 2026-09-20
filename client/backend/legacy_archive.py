"""legacy_archive — 兼容薄层（db-generation 已迁移至 db_lifecycle）。

本模块的历史职责（指纹/体检/差异分类/留档改名）已全部迁入 db_lifecycle.py；
「升级即整库留档」机制随版本化命名退役。保留此文件仅为既有 import 兼容
（main.py / backup/router.py / tests），新代码一律 import db_lifecycle。
"""

from db_lifecycle import (  # noqa: F401
    SCHEMA_ID_KEY,
    classify_drift,
    compute_schema_fingerprint,
    inspect_library,
    inspect_schema,
)
