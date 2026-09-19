"""SCHEMA_VERSION 单源（db-generation）。

库文件代数与代码一一对应：DATABASE_URL = .../novel-v{SCHEMA_VERSION}.db。
+1 纪律：仅破坏性 schema 变更（删表/删列/列改名/类型收窄/约束变更）升代；
additive（新表/可空列/带默认列）不升代，走 db_lifecycle.ADDITIVE_COLUMNS
代内幂等补列。与 backup.FORMAT_VERSION（包契约轴）各自演进、绝不共用。

独立零依赖叶子模块：config.py 拼 DATABASE_URL 引用（放 models 会 import 环）。
"""
import os

SCHEMA_VERSION = 1  # novel.db（无版本名）视为第 0 代

DB_FILENAME = f"novel-v{SCHEMA_VERSION}.db"

# 迁入候选世代门禁（db-generation）：低于该代的旧库存有盘上 yaml 设定
# （自存储 ADR 前），行级迁入会丢设定——引导走资产包导入通道。
# 第 0 代（novel.db / .legacy-*）需 inspect 后动态判定，此处不设静态下限。
MIN_ROW_MIGRATION_GENERATION = 0

# data 目录根（与 config.DATA_ROOT 同源；独立计算避免 import 环）
DATA_ROOT_ENV = os.getenv("CLIENT_DATA_DIR", "./data")
