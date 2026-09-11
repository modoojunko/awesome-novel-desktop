"""Context injection helpers for prompt assembly — world setting + active hooks.

分段链路（assembler）已退役（ai-prompt-crafting）：story/character 注入由
write/chapter_writer 素材包统一承载；世界观注入块与活跃伏笔过滤/渲染
（排除本章引入 + 状态过滤 + ≤8 上限）为两条写作消费方共享，保留于此。
"""

import re

from filesystem.storage import get_storage
from settings.world_model import render_world_block  # noqa: E402


def inject_world_setting(world: dict) -> str:
    """世界观 → v2 注入块（world-setting-v2，缺失安全；v1 旧数据内部归一）。

    供整章写作（chapter_writer 素材包与粗组兜底）消费。
    截断以整条为单元并显式从略；铁律不在本块（render_red_lines → 红线区）。
    """
    return render_world_block(world)


# ── 活跃伏笔（两条写作消费方共享的过滤与渲染）──────────────────────────


def _canonical_chapter_ref(ref: str) -> str:
    """把伏笔引入章节归一为规范 vol-N-ch-M 格式（兼容模板短格式 '1-1'）。"""
    ref = (ref or "").strip()
    if re.match(r"^vol-\d+-ch-\d+$", ref):
        return ref
    m = re.match(r"^(\d+)-(\d+)$", ref)
    if m:
        return f"vol-{m.group(1)}-ch-{m.group(2)}"
    return ref


_PRIORITY_LABELS = {1: "核心", 2: "重要", 3: "可选"}


def filter_active_hooks(hooks_data: dict, current_chapter_ref: str) -> list[dict]:
    """活跃伏笔过滤：pending/mentioned 状态、排除本章引入，≤8 条上限。"""
    hooks = [
        h
        for h in (hooks_data or {}).get("active", [])
        # 前端 active 项无 status 字段 → 默认 pending；resolved/abandoned 不在 active，天然排除
        if h.get("status", "pending") in ("pending", "mentioned")
        and _canonical_chapter_ref(h.get("introduced_in", "")) != current_chapter_ref
    ]
    return hooks[:8]


def render_hooks_block(hooks: list[dict]) -> str:
    """活跃伏笔 →「## 当前悬而未决的伏笔」注入块（优先级/类型/状态后缀）。"""
    if not hooks:
        return ""
    lines = ["## 当前悬而未决的伏笔"]
    for h in hooks:
        desc = h.get("description", "").strip()
        status = h.get("status", "待定")
        # 优先级 + 类型注入（键名兼容：前端存 type，语义键 hook_type）
        meta = []
        priority = h.get("priority")
        if priority is not None:
            try:
                meta.append(f"优先级：{_PRIORITY_LABELS.get(int(priority), priority)}")
            except (TypeError, ValueError):
                pass
        hook_type = h.get("hook_type") or h.get("type")
        if hook_type:
            meta.append(f"类型：{hook_type}")
        suffix = f"（{'，'.join(meta)}）" if meta else ""
        # 前端项无 id，用描述作为标识；旧格式有 id 保留 [id] 前缀
        if h.get("id"):
            lines.append(f"- [{h['id']}] {desc}{suffix}（状态：{status}）")
        else:
            lines.append(f"- {desc}{suffix}（状态：{status}）")
    return "\n".join(lines)


async def inject_active_hooks(root_path: str, current_chapter_ref: str) -> str:
    hooks_data = await get_storage().read_yaml(root_path, "settings/hooks.yaml")
    return render_hooks_block(filter_active_hooks(hooks_data, current_chapter_ref))
