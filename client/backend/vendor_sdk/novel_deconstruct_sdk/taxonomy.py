"""知识树索引（SDK 注入式——树配置由调用方传入，不绑包内文件）。"""

from __future__ import annotations

import json
from pathlib import Path


class TaxonomyIndex:
    """树索引：nodes/slot_map 只读视图；node_for/parent_chain 与 C 端 kb.taxonomy 同口径。"""

    def __init__(self, data: dict):
        self._data = data or {}
        self._nodes = self._data.get("nodes") or {}
        self._slot_map = self._data.get("slot_map") or {}

    @classmethod
    def from_file(cls, path: str | Path) -> TaxonomyIndex:
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    @classmethod
    def empty(cls) -> TaxonomyIndex:
        return cls({})

    def is_empty(self) -> bool:
        return not self._nodes

    def nodes(self) -> dict:
        return self._nodes

    def node_for(self, concept: str, slot_value: str) -> tuple[str, dict] | None:
        key = self._slot_map.get(f"{concept}|{slot_value}")
        if not key:
            for k, node in self._nodes.items():
                if node.get("concept") == concept and node.get("title") == slot_value:
                    return k, node
            return None
        return key, self._nodes[key]

    def parent_chain(self, key: str) -> list[str]:
        out: list[str] = []
        seen = {key}
        cur = (self._nodes.get(key) or {}).get("parent")
        while cur and cur not in seen:
            out.append(cur)
            seen.add(cur)
            cur = (self._nodes.get(cur) or {}).get("parent")
        out.reverse()
        return out
