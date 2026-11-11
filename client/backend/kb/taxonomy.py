"""发版知识树加载器（c-kb-tree-cdn：**树是 CDN 数据不是包内资产**）。

树的层次与定义从 CDN ``knowledge/tree`` 获取（``kb.tree_sync`` 验签后落
``{DATA_ROOT}/kb-tree/``），本模块只做加载与查询——改树＝内容仓改
``taxonomy/taxonomy.json`` 发新版，客户端静默同步。

- **空树安全**：缓存缺失/损坏/结构不对只 log 一次并返回规范化空树
  ``{"nodes": {}, "slot_map": {}}``，绝不抛异常、绝不回落包内文件（C 端
  不再打包 taxonomy——所有官方知识结构只从 CDN 获取）。总结/提炼据空树
  明确拒绝（``tree_not_ready``），不造本地知识。
- ``KB_TAXONOMY_PATH``：测试/dev 显式指定树文件（conftest 播种夹具）。
- 北极星：知识的层次、定义随 CDN 分发；实际案例由拆书输出；定期总结任务按
  ``slot_map`` 把案例归属到树的正确节点（懒物化——首次有案例落位才建知识点行）。
"""

from __future__ import annotations

import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

_EMPTY_TREE = {"nodes": {}, "slot_map": {}}

_lock = threading.Lock()
_cache: dict | None = None


def _tree_path() -> str | None:
    """树文件定位：KB_TAXONOMY_PATH 显式覆盖 → tree_sync 缓存。"""
    override = (os.environ.get("KB_TAXONOMY_PATH") or "").strip()
    if override:
        return override
    from kb.tree_sync import cached_tree_path

    return cached_tree_path()


def _normalize(data: object) -> dict:
    """结构归一：nodes/slot_map dict 化；脏数据剥除（dangling 指向不炸消费端）。"""
    if not isinstance(data, dict):
        return dict(_EMPTY_TREE)
    nodes = data.get("nodes") if isinstance(data.get("nodes"), dict) else {}
    slot_map = data.get("slot_map") if isinstance(data.get("slot_map"), dict) else {}
    nodes = {str(k): v for k, v in nodes.items() if isinstance(v, dict)}
    known = set(nodes)
    slot_map = {
        str(k): str(v) for k, v in slot_map.items()
        if str(v) in known
    }
    if not nodes:
        return dict(_EMPTY_TREE)
    return {"nodes": nodes, "slot_map": slot_map}


def _load() -> dict:
    """加载并缓存树（进程内一次；空树/损坏只在首次 log，不刷屏）。"""
    global _cache
    with _lock:
        if _cache is None:
            path = _tree_path()
            if not path:
                _cache = dict(_EMPTY_TREE)
            else:
                try:
                    with open(path, encoding="utf-8") as f:
                        _cache = _normalize(json.load(f))
                except FileNotFoundError:
                    logger.info("event=kb_tree_absent——树未同步，知识整理不可用")
                    _cache = dict(_EMPTY_TREE)
                except (OSError, ValueError) as exc:
                    logger.warning("event=kb_tree_unreadable path=%s err=%s", path, exc)
                    _cache = dict(_EMPTY_TREE)
        return _cache


def reload() -> None:
    """清进程内缓存（tree_sync 安装新版本后必须调用，否则进程内永远是旧树）。"""
    global _cache
    with _lock:
        _cache = None


def nodes() -> dict[str, dict]:
    """发版节点表：key → {concept, title, definition, parent}；未就绪＝空 dict。"""
    return _load()["nodes"]


def is_ready() -> bool:
    """树是否就绪（有节点可用）——总结/提炼的准入闸。"""
    return bool(_load()["nodes"])


def node_for(concept: str, slot_value: str) -> tuple[str, dict] | None:
    """(类别, 槽位值) → (节点 key, 节点 dict)；未收录返 None（总结回落自建）。

    查序：slot_map 精确命中 → 类别下按标题命中槽位值（角色定位值等直名槽）。
    """
    data = _load()
    key = data["slot_map"].get(f"{concept}|{slot_value}")
    if not key or key not in data["nodes"]:
        for k, node in data["nodes"].items():
            if node.get("concept") == concept and node.get("title") == slot_value:
                return k, node
        return None
    return key, data["nodes"][key]


def parent_chain(key: str) -> list[str]:
    """节点 key 的父链（顶层在前、自身不在内）；未知键/环/断链一律截断为空。"""
    nodes_map = nodes()
    if key not in nodes_map:
        return []
    out: list[str] = []
    seen = {key}
    cur = str(nodes_map[key].get("parent") or "")
    while cur and cur in nodes_map and cur not in seen:
        out.append(cur)
        seen.add(cur)
        cur = str(nodes_map[cur].get("parent") or "")
    out.reverse()
    return out
