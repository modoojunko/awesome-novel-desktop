"""文本规范化与段落切分（c-zhuque-ai-detect：切分口径后端单点）。

前后端唯一口径（spec：zhuque-detection「段落切分后端收口与上游对齐」）：
- 换行归一 ``\\r\\n|\\r`` → ``\\n``；NBSP ``\\u00a0`` → 空格（粘贴 Word/网页会把
  真实 U+00A0 插进编辑器文档，管道不含此步会让前端重算指纹恒不相等）；
- 「段落」谓词＝去除首尾空白后非空的行；``paragraph_index`` 按非空段 0 起编号；
- ``prose_hash``＝规范化文本（非空段 trim 后以 ``\\n`` join）的 sha256——哈希对象
  即请求体 text，可对请求体复算。
"""

from __future__ import annotations

import hashlib

MAX_PROSE_CHARS = 30_000


def normalize(text: str) -> str:
    """换行与 NBSP 归一（管道第一步）。"""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")


def split_paragraphs(text: str) -> list[str]:
    """按非空段切分：返回各段（已 trim、保序）。"""
    return [seg.strip() for seg in normalize(text).split("\n") if seg.strip()]


def canonical_text(text: str) -> str:
    """规范化文本＝非空段 trim 后以 ``\\n`` join（请求体 text 与指纹输入同源）。"""
    return "\n".join(split_paragraphs(text))


def fingerprint(text: str) -> str:
    """prose_hash＝规范化文本的 sha256（hex）。"""
    return hashlib.sha256(canonical_text(text).encode("utf-8")).hexdigest()
