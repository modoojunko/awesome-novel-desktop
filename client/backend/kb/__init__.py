"""写作知识库（c-knowledge-base）。

分层：L0 元模型（models.py）→ L1 概念注册表（concepts.py）
     → L2 条目（payloads.py 校验）→ L3 库（service.py）
依赖方向：kb/ SHALL NOT import write/、deconstruct/。
"""
