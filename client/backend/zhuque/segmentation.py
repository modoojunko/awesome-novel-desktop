"""文本规范化与段落切分（c-zhuque-ai-detect：切分口径后端单点）。

前后端唯一口径（spec：zhuque-detection「段落切分后端收口与上游对齐」）：
- 换行归一 ``\\r\\n|\\r`` → ``\\n``；NBSP ``\\u00a0`` → 空格（粘贴 Word/网页会把
  真实 U+00A0 插进编辑器文档，管道不含此步会让前端重算指纹恒不相等）；
- 「段落」谓词＝去除首尾空白后非空的行；``paragraph_index`` 按非空段 0 起编号；
- ``prose_hash``＝规范化文本（非空段 trim 后以 ``\\n`` join）的 sha256——哈希对象
  即请求体 text，可对请求体复算。
"""

from __future__ import annotations

import bisect
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


def align_segments(paragraphs: list[str], seg_labels: list[dict]) -> list[dict]:
    """上游段 → 本地段映射（c-zhuque-seg-align）。

    上游（EdgeOne 朱雀网关）按自身规则合并/切分文本，segment 数与本地非空段数
    无恒等关系（实测：231 字 10 段整章并 1 段；1512 字 34 段只回 2 段）——段数
    比对不可用。对齐物是各段的 ``text``，两层校验：
    1) 精确层：各段 text 按响应序拼接恰等于请求规范化文本（实测上游保留段间换行）；
    2) 容错层：精确不等时，去全部空白后逐字相等仍接受（防上游吞段边界换行误杀）。
    段落归属＝其首字符在拼接流中的位置所在上游段（被合并段落共享该段 label/conf）；
    段落逐个在流上消费校验，无法命中（截断/改写）→ ValueError("segment_mismatch")，
    502 语义保留为防御。``position`` 区间终点实测不可靠，不作对齐键。
    """
    canonical = "\n".join(paragraphs)
    texts = [str(seg.get("text") or "") for seg in seg_labels]
    joined = "".join(texts)
    exact = joined == canonical
    if not exact and _compact(joined) != _compact(canonical):
        raise ValueError("segment_mismatch")

    starts: list[int] = []
    acc = 0
    for t in texts:
        starts.append(acc)
        acc += len(t)

    out: list[dict] = []
    cursor = 0
    for idx, para in enumerate(paragraphs):
        if not exact:
            while cursor < len(joined) and joined[cursor].isspace():
                cursor += 1
        if not joined.startswith(para, cursor):
            raise ValueError("segment_mismatch")
        # 段落首字符所在上游段（bisect_right：恰落边界归后段；零长段自然跳过）
        ri = bisect.bisect_right(starts, cursor) - 1
        seg = seg_labels[ri]
        out.append({
            "paragraph_index": idx,
            "label": int(seg.get("label", 0)),
            "confidence": float(seg.get("conf", 0) or 0),
        })
        cursor += len(para)
        if exact and cursor < len(joined):
            cursor += 1  # 精确模式跳过段间 \n（canonical 同构，必为换行）
    return out


def _compact(s: str) -> str:
    return "".join(ch for ch in s if not ch.isspace())
