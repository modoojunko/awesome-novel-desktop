"""Context injection helpers for prompt assembly — world setting + active hooks.

分段链路（assembler）已退役（ai-prompt-crafting）：story/character 注入由
write/chapter_writer 素材包统一承载；世界观注入块与活跃伏笔过滤/渲染
（排除本章引入 + 状态过滤 + ≤8 上限）为两条写作消费方共享，保留于此。

伏笔注入口径（foreshadow-settings-v2，prompt-crafting）：数据源为真表
`novel_hooks`——只注入 status==active；「排除本章引入」按 introduced_chapter_id
与当前章 id 相等判断（替代 ref 字符串比较）；展示编号 [H-####] 派生自 seq；
优先级以「高/中/低」标注（存储 Integer，映射唯一，非法值丢弃该标注）。
"""

from sqlalchemy import select

from settings.hooks_model import priority_label, type_label
from settings.world_model import render_world_block  # noqa: E402


def inject_world_setting(world: dict) -> str:
    """世界观 → v2 注入块（world-setting-v2，缺失安全；v1 旧数据内部归一）。

    供整章写作（chapter_writer 素材包与粗组兜底）消费。
    截断以整条为单元并显式从略；铁律不在本块（render_red_lines → 红线区）。
    """
    return render_world_block(world)


# ── 活跃伏笔（真表 novel_hooks；两条写作消费方共享的过滤与渲染）──────────


def _get(h, key):
    """行/字典两用取值（服务层返回行，测试与调用方可传 dict 同形）。"""
    if isinstance(h, dict):
        return h.get(key)
    return getattr(h, key, None)


def filter_active_hooks(hooks, current_chapter_id: str | None = None) -> list:
    """活跃伏笔过滤：只认 status==active、排除本章引入（章 id 相等），≤8 条上限。

    引入章为空（未定期）的伏笔照常注入；当前章行解析不出（id=None）时不排除任何条。
    """
    kept = []
    for h in hooks or []:
        if _get(h, "status") != "active":
            continue
        introduced = _get(h, "introduced_chapter_id")
        if introduced and current_chapter_id and introduced == current_chapter_id:
            continue
        kept.append(h)
    return kept[:8]


def hook_view(h) -> dict:
    """NovelHook 行 → 注入用 dict：展示编号/优先级/类型标签按词表就绪。

    优先级非法 → 标注为空串（渲染时丢弃该标注，不静默吞错位）。
    """
    seq = _get(h, "seq")
    return {
        "code": f"H-{seq:04d}" if isinstance(seq, int) and seq > 0 else "",
        "description": str(_get(h, "description") or ""),
        "priority_label": priority_label(_get(h, "priority")),
        "type_label": type_label(_get(h, "type")) if _get(h, "type") else "",
    }


def render_hooks_block(hooks: list[dict]) -> str:
    """活跃伏笔 →「## 当前悬而未决的伏笔」注入块（[H-####] + 优先级/类型标注）。"""
    if not hooks:
        return ""
    lines = ["## 当前悬而未决的伏笔"]
    for h in hooks:
        desc = str(h.get("description", "") or "").strip()
        meta = []
        if h.get("priority_label"):
            meta.append(f"优先级：{h['priority_label']}")
        if h.get("type_label"):
            meta.append(f"类型：{h['type_label']}")
        suffix = f"（{'，'.join(meta)}）" if meta else ""
        code = h.get("code") or ""
        prefix = f"[{code}] " if code else ""
        lines.append(f"- {prefix}{desc}{suffix}")
    return "\n".join(lines)


async def load_active_hooks(
    novel_id: str | None, current_chapter_id: str | None = None
) -> list[dict]:
    """真表活跃伏笔：status==active 按 seq 序取全 → 过滤 → 视图整形。

    无 novel_id（纯文件态/旧测试桩）降级为空列表——KV 通道已退役，无兜底读。
    """
    if not novel_id:
        return []
    from db import async_session
    from models.hook import NovelHook

    async with async_session() as session:
        rows = (
            await session.scalars(
                select(NovelHook)
                .where(NovelHook.novel_id == novel_id, NovelHook.status == "active")
                .order_by(NovelHook.seq)
            )
        ).all()
    return [hook_view(h) for h in filter_active_hooks(rows, current_chapter_id)]


async def active_hooks_for_chapter(
    root_path: str, chapter_ref: str, novel_id: str | None
) -> list[dict]:
    """写章消费方唯一入口：root_path + ref 解析当前章 id 后加载活跃伏笔。

    章行缺失（未入库的纯文件章）时 current id 为 None → 不做本章排除。
    """
    if not novel_id:
        return []
    from chapters.store import _get_chapter_by_root
    from db import async_session

    async with async_session() as session:
        ch_row = await _get_chapter_by_root(session, root_path, chapter_ref)
    return await load_active_hooks(novel_id, ch_row.id if ch_row else None)
