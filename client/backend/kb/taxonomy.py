"""发版知识树加载器（boss 2026-11-08 拍板：**知识是数据不是代码**）。

树的层次与定义住 ``kb/data/taxonomy.json``（随 C 端发版分发，打包进安装包）；
本模块只做加载与查询——改树＝改那份数据随版本走，不动代码。

北极星：知识的层次、定义随发版分发；实际案例由拆书输出；定期总结任务按
``slot_map`` 把案例归属到树的正确节点（懒物化——首次有案例落位才建知识点行）。
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path


def _data_path() -> Path:
    """数据文件定位：源码态 kb/data/；冻结态资源根 kb/data/（datas 目标段）。"""
    if getattr(sys, "frozen", False):  # PyInstaller
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        cand = base / "kb" / "data" / "taxonomy.json"
        if cand.exists():
            return cand
        return Path(sys.executable).parent / "kb" / "data" / "taxonomy.json"
    return Path(__file__).parent / "data" / "taxonomy.json"


_lock = threading.Lock()
_cache: dict | None = None


def _load() -> dict:
    """加载并缓存 taxonomy.json（进程内一次；数据文件随包只读）。"""
    global _cache
    with _lock:
        if _cache is None:
            with open(_data_path(), encoding="utf-8") as f:
                _cache = json.load(f)
        return _cache


def nodes() -> dict[str, dict]:
    """发版节点表：key → {concept, title, definition, parent}。"""
    return _load()["nodes"]


def node_for(concept: str, slot_value: str) -> tuple[str, dict] | None:
    """(类别, 槽位值) → (节点 key, 节点 dict)；未收录返 None（总结回落自建）。

    查序：slot_map 精确命中 → 类别下按标题命中槽位值（角色定位值等直名槽）。
    """
    data = _load()
    key = data["slot_map"].get(f"{concept}|{slot_value}")
    if not key:
        for k, node in data["nodes"].items():
            if node["concept"] == concept and node["title"] == slot_value:
                return k, node
        return None
    return key, data["nodes"][key]


def parent_chain(key: str) -> list[str]:
    """节点 key 的父链（顶层在前、自身不在内）；环与断链截断。"""
    out: list[str] = []
    seen = {key}
    cur = nodes()[key]["parent"]
    while cur and cur not in seen:
        out.append(cur)
        seen.add(cur)
        cur = nodes()[cur]["parent"]
    out.reverse()
    return out
