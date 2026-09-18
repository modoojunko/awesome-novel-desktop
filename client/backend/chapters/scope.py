"""主线性（mainline）单源——「主线章 = ghost_of IS NULL」的唯一判定处。

背景：ghost_of 引入后，「哪些章属主线」散落在 frontier/树/统计/回退/导出各处；
任一处漏滤 = 旧稿支线章抢占主线语义（如 frontier 被旧稿顶掉致真端点章 409）。
所有主线语义查询 SHALL 经本模块构造，禁止再手写 `Chapter.project_id == ...`
而漏 `ghost_of`（新增消费面必须在此登记）。
"""

from __future__ import annotations

from sqlalchemy import Select, select

from models.chapter import Chapter

# 主线语义消费面登记（新增须在此列出并在测试矩阵覆盖）：
#   1. chapters/frontier.py    — 主线端点与写入门禁
#   2. volumes/service.py      — 卷章树（章列表）
#   3. novels/router.py        — 书架统计（字数/章数/归档数）
#   4. chapters/frontier.py    — revert 截断（回退基序）
#   5. chapters/rewrite.py     — 重写（源章校验与下游 stale 圈定）
#   6. manuscript/content.py   — 成稿下载（读者成稿内容装配，c-manuscript-download）


def mainline_stmt(novel_id: str) -> Select:
    """主线章查询（唯一构造入口）。"""
    return select(Chapter).where(
        Chapter.project_id == novel_id, Chapter.ghost_of.is_(None)
    )
