"""知识视图谓词收口（c-kb-summarize）。

素材行（origin='material'）是拆书收录与手录落库的事实记录，不是知识：
星图装配、选择器、写法块、书级副本等消费端统一引用 `visible_knowledge_filter()`
排除素材；知识列表是素材的展示面（带「素材」标），默认视图不滤。
"""

from sqlalchemy import ColumnElement

from models.kb import KbEntry


def visible_knowledge_filter() -> ColumnElement[bool]:
    """知识可见性谓词：排除素材行。消费端一律引用本 helper，不得散落字面量。"""
    return KbEntry.origin != "material"
