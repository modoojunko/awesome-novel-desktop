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
    """活跃伏笔过滤：只认 status==active、排除本章引入（章 id 相等）——**全量，不封顶**。

    c-ai-material-audit：旧实现 `[:8]` 与 spec「伏笔台账 active 全量」冲突——第 9 条以后的
    未收伏笔在写正文/拆卷展开/卷体检里全部不存在（漏还债、漏判"提前揭"）。
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
    return kept


def hook_view(h, current_chapter_id: str | None = None) -> dict:
    """NovelHook 行 → 注入用 dict：展示编号/优先级/类型标签按词表就绪。

    优先级非法 → 标注为空串（渲染时丢弃该标注，不静默吞错位）。
    due_now：计划收束章等于当前写作章 → 「建议本章收束」派生标记
    （style-settings-v2 评审 P1：只写 planned 不给信号，AI 写到那章不知道要还）。
    """
    seq = _get(h, "seq")
    planned = _get(h, "planned_chapter_id")
    return {
        "code": f"H-{seq:04d}" if isinstance(seq, int) and seq > 0 else "",
        "description": str(_get(h, "description") or ""),
        "priority_label": priority_label(_get(h, "priority")),
        "type_label": type_label(_get(h, "type")) if _get(h, "type") else "",
        "due_now": bool(
            current_chapter_id and planned and str(planned) == str(current_chapter_id)
        ),
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
        if h.get("due_now"):
            meta.append("建议本章收束")
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
    return [
        hook_view(h, current_chapter_id)
        for h in filter_active_hooks(rows, current_chapter_id)
    ]


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


# ── 模板安全渲染＋人物档案锚（c-write-prompt-layering）──────────────────


def render_template(text: str, **kwargs: str) -> str:
    """占位符安全渲染：逐个顺序 replace，SHALL NOT 用 str.format——
    素材/设定文本含 `{`/`}`（JSON、花括号修辞）时 format 会 KeyError。"""
    for key, value in kwargs.items():
        text = text.replace("{" + key + "}", value)
    return text


def cast_profile_block(items: list[dict], footer_template: str = "") -> str:
    """全人物档案原文块：名字（别名）＋类型＋人设原文＋档案八格原文（只列已填格）；
    认知六层逐格原文只给主角与反派。空名占位卡按展示口径显示「未命名」。

    不复用 volumes 的 cast_brief：那条 `persona[:80]` 截断，达不到「原封不动」。
    footer_template 可含 {n}（人数），主线起草传 arc 口径尾注，写正文不传。
    """
    from settings.character_model import COG_LAYERS, DOSSIER_FIELDS
    from settings.character_service import _display_name

    lines: list[str] = []
    for it in items:
        name = _display_name(str(it.get("name") or ""))
        aliases = [str(a).strip() for a in (it.get("aliases") or []) if str(a).strip()]
        head = f"- {name}（{it.get('role') or ''}"
        if aliases:
            head += "｜别名：" + "、".join(aliases)
        lines.append(head + "）")
        persona = str(it.get("persona") or "").strip()
        if persona:
            lines.append(f"  人设：{persona}")
        dossier = it.get("dossier") if isinstance(it.get("dossier"), dict) else {}
        cells = [
            f"{f['label']}：{str(dossier.get(f['k']) or '').strip()}"
            for f in DOSSIER_FIELDS
            if str(dossier.get(f["k"]) or "").strip()
        ]
        if cells:
            lines.append("  档案：" + "｜".join(cells))
        if it.get("role") in _CAST_DEPTH_ROLES:
            cog = it.get("cog") if isinstance(it.get("cog"), dict) else {}
            for layer in COG_LAYERS:
                filled = [
                    f"{f['label']}：{str(cog.get(f['k']) or '').strip()}"
                    for f in layer["fields"]
                    if str(cog.get(f["k"]) or "").strip()
                ]
                if filled:
                    lines.append(f"  认知·{layer['name']}：" + "｜".join(filled))
    if not lines:
        return ""
    if footer_template:
        lines.append(footer_template.replace("{n}", str(len(items))))
    return "\n".join(lines)


# 主角/反派给认知六层全量（与 ai_router 主线起草同口径）
_CAST_DEPTH_ROLES = ("主角", "反派")


def cast_anchors_block(items: list[dict]) -> str:
    """system 恒定层档案锚（c-cast-split-user-layer）：只收主角与反派。

    两张极性卡（含认知六层全量）逐章恒定吃前缀缓存；配角与未设角色卡
    按本章出场走 user 层（chapter_writer.to_user_material 的「本章出场配角」块），
    新增配角不再改写 system 缓存前缀。空集返回空串（恒定层不出空节）。
    """
    return cast_profile_block(
        [it for it in items if it.get("role") in _CAST_DEPTH_ROLES]
    )
