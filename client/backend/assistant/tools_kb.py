"""知识库工具（c-writing-agent 批B 余项：能力围栏承诺的 KB 读/写/改域）。

知识库＝作家自己的资产（拍板④围栏内的合法操作域）。读类（kb_search/kb_read）
登录即可；写/改（kb_create_entry/kb_update_entry）走 write_gate 授权梯度＋既有
闸门（kb update_entry 自带 GateResult＋乐观并发，校验链原样生效）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from assistant.tools import Tool, ToolContext, ToolResult, _clip, _jsonable

_KB_ITEM_BUDGET = 500


async def _kb_search(ctx: ToolContext, q: str = "", genre: str = "", concept: str = "") -> ToolResult:
    """按关键词/题材/概念检索知识库条目（只读；官方层需 kb-official）。"""
    from auth_local.deps import ai_access_granted
    from db import async_session
    from kb.router import _entry_dict
    from kb.service import list_entries

    async with async_session() as session:
        entries, _cursor = await list_entries(
            session,
            user_id=ctx.user_id,
            genre=str(genre or "").strip(),
            concept=str(concept or "").strip(),
            q=str(q or "").strip(),
            limit=10,
            include_baseline=ai_access_granted("kb-official"),
        )
    if not entries:
        return ToolResult(ok=True, summary="（知识库没有匹配的条目）")
    lines = []
    for e in entries:
        it = _entry_dict(e)
        lines.append(
            f"- [{it.get('genre')}/{it.get('concept')}] {it.get('title') or it.get('id')}"
            f"（{_clip(str(it.get('instruction') or ''), 120)}）"
        )
    return ToolResult(ok=True, summary=_clip("\n".join(lines), _KB_ITEM_BUDGET * 2))


async def _kb_read(ctx: ToolContext, entry_id: str) -> ToolResult:
    """读一条知识库条目全文。"""
    from db import async_session
    from kb.router import _entry_dict
    from kb.service import get_entry

    entry_id = str(entry_id or "").strip()
    async with async_session() as session:
        entry = await get_entry(session, user_id=ctx.user_id, entry_id=entry_id)
    if entry is None:
        return ToolResult(ok=False, summary=f"条目不存在：{entry_id}")
    data = _entry_dict(entry)
    return ToolResult(ok=True, summary=_clip(json.dumps(data, ensure_ascii=False, default=str), _KB_ITEM_BUDGET * 2))


async def _kb_create_entry(
    ctx: ToolContext,
    genre: str,
    concept: str,
    title: str,
    payload: dict[str, Any],
    instruction: str = "",
    example: str = "",
) -> ToolResult:
    """新建知识库条目（写类：write_gate 授权梯度；走既有 create_entry 校验链）。"""
    from db import async_session
    from kb.service import create_entry

    if not str(genre or "").strip() or not str(concept or "").strip():
        return ToolResult(ok=False, summary="genre 与 concept 必填（先 read_settings/kb_search 确认题材与概念归属）。")
    if not isinstance(payload, dict) or not payload:
        return ToolResult(ok=False, summary="payload 必须是非空对象（条目内容）。")
    async with async_session() as session:
        entry = await create_entry(
            session,
            user_id=ctx.user_id,
            genre=str(genre).strip(),
            concept=str(concept).strip(),
            title=str(title or "").strip(),
            payload=payload,
            instruction=str(instruction or ""),
            example=str(example or ""),
            src_kind="assistant",
            src_ref="c-writing-agent",
        )
    return ToolResult(
        ok=True,
        summary=f"已新建知识库条目（{genre}/{concept}）：{_clip(str(title) or str(entry.id), 60)}",
        meta={"write_log": {"entity": f"kb:{entry.id}", "fields": {"genre": genre, "concept": concept, "payload": payload}, "previous": None}},
    )


async def _kb_update_entry(ctx: ToolContext, entry_id: str, fields: dict[str, Any]) -> ToolResult:
    """改知识库条目（写类：授权梯度；既有闸门 GateResult＋乐观并发原样生效）。"""
    from db import async_session
    from kb.service import get_entry, update_entry

    entry_id = str(entry_id or "").strip()
    fields = fields or {}
    if not fields:
        return ToolResult(ok=False, summary="没有要改的字段。")
    allowed = ("title", "instruction", "payload", "example", "negative_example", "genre")
    bad = [k for k in fields if k not in allowed]
    if bad:
        return ToolResult(ok=False, summary=f"字段不在白名单：{bad}（可改：{list(allowed)}）")

    async with async_session() as session:
        from kb.router import _entry_dict

        entry = await get_entry(session, user_id=ctx.user_id, entry_id=entry_id)
        if entry is None:
            return ToolResult(ok=False, summary=f"条目不存在：{entry_id}")
        prev = _entry_dict(entry)
        previous = {k: prev.get(k) for k in fields}
        entry2, gate, _detail = await update_entry(
            session, user_id=ctx.user_id, entry_id=entry_id,
            **{k: fields[k] for k in fields},
        )
        if gate is not None and not getattr(gate, "ok", True):
            return ToolResult(ok=False, summary=f"闸门未通过：{getattr(gate, 'reasons', '') or '条目校验未过'}")
        if entry2 is None:
            return ToolResult(ok=False, summary="更新失败（并发冲突或条目已删）。")
    return ToolResult(
        ok=True,
        summary=f"已更新条目 {entry_id}：{'、'.join(fields)}",
        meta={
            "write_log": {
                "entity": f"kb:{entry_id}",
                "fields": fields,
                "previous": {k: _jsonable(v) for k, v in previous.items()},
            }
        },
    )


# ── 写法候选检索（c-agent-dialog-prose）：按本章剧情确定性检索题材写法条目 ─────

_CRAFT_CONCEPTS = ("手法", "文风", "文笔")
_CRAFT_LIMIT_DEFAULT = 12
_CRAFT_LIMIT_MAX = 30


def _craft_terms(text: str) -> set[str]:
    """检索词（确定性）：CJK 二字串＋ASCII 词。中文无空格，决策档案的 split()
    分词 AND 用不上——与 chapter_writer lint 的 bigram 覆盖代理同思路。"""
    import re

    text = (text or "").lower()
    words = set(re.findall(r"[a-z0-9]{2,}", text))
    cjk = re.sub(r"[^\u4e00-\u9fff]", "", text)
    if len(cjk) > 1:
        words |= {cjk[i: i + 2] for i in range(len(cjk) - 1)}
    elif cjk:
        words.add(cjk)
    return words


def _when_zh(entry) -> str:
    """when_json → 「场面=打斗；情绪=燃」人话（空＝无适用条件）。"""
    try:
        w = json.loads(entry.when_json or "{}")
    except ValueError:
        return ""
    if not isinstance(w, dict):
        return ""
    parts = []
    for key, label in (("scene", "场面"), ("emotion", "情绪"), ("chapter_pos", "章位")):
        v = str(w.get(key) or "").strip()
        if v:
            parts.append(f"{label}={v}")
    return "；".join(parts)


def _book_style_draft_lines(entries: list, *, theme: str, limit: int = 6) -> list[str]:
    """全书级文风/文笔草稿行（c-agent-prose-kb-picks）。

    只在本书文风三区未配置时使用：同题材优先，文风/文笔按概念交替取（各占一半），
    不做剧情词打分——全书级声音不是本章场景条目，按剧情筛会挑出不贴调性的条目。
    行格式与检索候选同形，但明确「不进 picks」。只读，不写设定。
    """
    same = [e for e in entries if str(getattr(e, "genre", "") or "") == theme]
    pool = same or entries
    by_concept: dict[str, list] = {}
    for e in pool:
        by_concept.setdefault(str(getattr(e, "concept", "") or ""), []).append(e)
    concepts = sorted(by_concept)  # 稳定：文风/文笔各一桶
    picked: list = []
    idx = 0
    while len(picked) < limit and any(by_concept[c] for c in concepts):
        bucket = by_concept[concepts[idx % len(concepts)]]
        if bucket:
            picked.append(bucket.pop(0))
        idx += 1
        if idx > limit * len(concepts) * 2:  # 防御空桶死循环
            break
    return [
        f"- [{getattr(e, 'concept', '')}] {getattr(e, 'title', '') or getattr(e, 'id', '')}"
        f"｜{_clip(str(getattr(e, 'instruction', '') or ''), 120)}"
        for e in picked
    ]


async def _book_base_style_entries(db, novel_id: str, genre: str) -> list:
    """书级副本里的全书级文风/文笔条目（when 空）——草稿与计数用。

    书副本（kb_book_entries）是开书时的快照，`load_style_entries` 只查账号库＋基线，
    不覆盖副本；这里补上，避免启用库的书被误报「库内没有文笔/文风条目」。
    """
    from models.kb import KbBookEntry

    rows = (
        await db.execute(
            select(KbBookEntry).where(
                KbBookEntry.novel_id == novel_id,
                KbBookEntry.status == "active",
                KbBookEntry.concept.in_(("文风", "文笔")),
            )
        )
    ).scalars().all()
    out = []
    for e in rows:
        try:
            when = json.loads(e.when_json or "{}")
        except ValueError:
            when = {}
        if isinstance(when, dict) and when:
            continue
        if str(getattr(e, "genre", "") or "") not in (genre, ""):
            continue
        out.append(e)
    out.sort(key=lambda e: 0 if str(getattr(e, "genre", "") or "") == genre else 1)
    return out


async def _kb_search_craft(
    ctx: ToolContext,
    chapter_ref: str = "",
    query: str = "",
    concept: str = "",
    limit: int = _CRAFT_LIMIT_DEFAULT,
) -> ToolResult:
    """按剧情检索写法候选（题材内；写法块同源候选域；只读，零成本）。

    候选域与写法块同源（kb.match.digest_candidates：书级副本或账号库＋官方基线
    merged 视图）——这里返回的条目 id 才能进方案卡 picks 并被 write 链注入。
    打分＝查询词与条目标题＋指令的 bigram 重合度×有用率×新鲜度（确定性平序）。"""
    from db import async_session
    from kb.match import _freshness, _usefulness, digest_candidates
    from models.kb import KbBookEntry, KbKnowledge, KbPref

    concept = str(concept or "").strip()
    if concept and concept not in _CRAFT_CONCEPTS:
        return ToolResult(
            ok=False, summary=f"concept 只认：{'、'.join(_CRAFT_CONCEPTS)}（留空＝全部）。"
        )
    try:
        limit = max(1, min(int(limit or _CRAFT_LIMIT_DEFAULT), _CRAFT_LIMIT_MAX))
    except (TypeError, ValueError):
        limit = _CRAFT_LIMIT_DEFAULT
    query = str(query or "").strip()
    chapter_ref = str(chapter_ref or "").strip()

    async with async_session() as db:
        # 域解析（同 write_block.prepare_write_block 口径）：书级副本非空＝书域；
        # 否则账号域＋基线层，题材必须就绪（空题材＝跨题材串味，宁可不检）
        copy_exists = (
            await db.execute(
                select(KbBookEntry.id).where(
                    KbBookEntry.novel_id == ctx.novel_id, KbBookEntry.status == "active"
                )
            )
        ).scalars().first()
        book_scope = None
        genre = ""
        if copy_exists is None:
            from filesystem.paths import KEY_TO_PATH
            from filesystem.storage import get_storage

            story = await get_storage().read_yaml(ctx.root_path, KEY_TO_PATH["story"]) or {}
            genre = str(story.get("genre") or "").strip()
            if not genre:
                return ToolResult(
                    ok=True,
                    summary="本书还没设定题材——先在设定里定题材，我再按题材匹配写法条目。",
                )
        else:
            book_scope = ctx.novel_id

        # 查询文本：显式 query 优先；缺省用本章素材（概要/剧情条目/挑战）
        parts: list[str] = []
        if chapter_ref:
            from models.chapter import Chapter

            ch = (
                await db.execute(
                    select(Chapter).where(
                        Chapter.project_id == ctx.novel_id,
                        Chapter.ref == chapter_ref,
                        Chapter.ghost_of.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if ch is not None:
                try:
                    items = json.loads(ch.plot_items or "[]")
                except ValueError:
                    items = []
                parts = [ch.summary or "", ch.challenge or ""] + [
                    str(i) for i in items if isinstance(i, str) and i.strip()
                ]
        query_text = query or "；".join(p for p in parts if p.strip())
        if not query_text.strip():
            return ToolResult(
                ok=False,
                summary="缺查询内容——给一段剧情描述，或指定 chapter_ref（我按本章概要与剧情条目匹配）。",
            )

        groups = await digest_candidates(
            db, user_id=ctx.user_id, genre=genre, book_scope=book_scope
        )
        if concept == "手法":
            wanted = groups["tech"]
        elif concept in ("文风", "文笔"):
            wanted = groups["style"]
        else:
            wanted = groups["tech"] | groups["style"]
        if not wanted:
            return ToolResult(
                ok=True,
                summary=(
                    "（写法候选域为空——可直接出方案卡不带写法条目，"
                    "正文会按本书文风设定生成。）"
                ),
            )
        entry_model = KbBookEntry if book_scope else KbKnowledge
        stmt = select(entry_model).where(
            entry_model.id.in_(sorted(wanted)), entry_model.status == "active"
        )
        if not book_scope:
            stmt = stmt.where(entry_model.user_id == ctx.user_id)
        rows = (await db.execute(stmt.order_by(entry_model.id))).scalars().all()
        if not rows:
            from kb.merged import load_baseline_entries

            rows = list(await load_baseline_entries(db, user_id=ctx.user_id, ids=sorted(wanted)))
        if not rows:
            return ToolResult(
                ok=True,
                summary=(
                    "（写法候选域为空——可直接出方案卡不带写法条目，"
                    "正文会按本书文风设定生成。）"
                ),
            )
        prefs = {
            p.entry_id: p
            for p in (
                await db.execute(
                    select(KbPref).where(
                        KbPref.user_id == ctx.user_id, KbPref.entry_id.in_(sorted(wanted))
                    )
                )
            ).scalars()
        }
        # 分桶说明与书级草稿（c-agent-prose-kb-picks）：style 段为零时给出原因；
        # 本书文风三区未配置时附全书级草稿（只读、不进 picks）。
        include_tech = concept in ("", "手法")
        include_style = concept in ("", "文风", "文笔")
        base_style_count = 0
        draft_lines: list[str] = []
        if include_style:
            from assistant.style_gap import style_three_zones_empty
            from settings.style_kb import load_style_entries

            base_entries = (
                await _book_base_style_entries(db, book_scope, genre)
                if book_scope
                else await load_style_entries(db, user_id=ctx.user_id, theme=genre)
            )
            base_style_count = len(base_entries)
            if base_entries and await style_three_zones_empty(db, ctx.root_path):
                draft_lines = _book_style_draft_lines(base_entries, theme=genre)

    import datetime as _dt

    now = _dt.datetime.utcnow()
    q_terms = _craft_terms(query_text)

    def _scored(rows_: list) -> list:
        out = []
        for e in rows_:
            et = _craft_terms(
                f"{getattr(e, 'title', '') or ''} {getattr(e, 'instruction', '') or ''}"
            )
            overlap = len(q_terms & et)
            if overlap == 0:
                continue  # 零重合＝纯噪声（不进候选——宁缺毋滥，未命中如实回话）
            score = (
                (overlap / max(1, len(q_terms)))
                * _usefulness(prefs.get(e.id))
                * _freshness(e, now)
            )
            out.append((score, e))
        out.sort(
            key=lambda t: (
                -t[0],
                str(getattr(t[1], "title", "") or ""),
                str(getattr(t[1], "id", "")),
            )
        )
        return out

    # 分桶（c-agent-prose-kb-picks）：手法与场面级文笔/文风分开打分与呈现，
    # 避免手法按剧情词天然霸榜后把文笔/文风整段挤掉。
    tech_scored = _scored([e for e in rows if getattr(e, "concept", "") == "手法"])
    style_scored = _scored(
        [e for e in rows if getattr(e, "concept", "") in ("文风", "文笔")]
    )
    if not tech_scored and not style_scored:
        return ToolResult(
            ok=True,
            summary=(
                "（写法候选里没有与这段剧情相关的条目——可直接出方案卡不带写法条目，"
                "正文会按本书文风设定生成。）"
            ),
        )

    def _fmt(scored: list) -> list[str]:
        # 每段上限 6：两段候选＋草稿合计要落进 2600 字回执预算，否则段头/草稿
        # 会被 _clip 从尾部截掉（分桶就白分了）。
        cap = min(limit, 6)
        out = []
        for _score, e in scored[:cap]:
            when = _when_zh(e)
            line = f"- [{e.concept}] {e.title or e.id}（id: {e.id}）"
            line += f"｜{_clip(str(e.instruction or ''), 90)}"
            if when:
                line += f"｜适用：{when}"
            out.append(line)
        return out

    lines = [
        (
            f"写法候选（题材{genre or '书内副本'}，按与剧情重合度排序；"
            "选中后在方案卡 picks 里给条目 id 与一句理由）："
        )
    ]
    if include_tech:
        lines.append("【手法候选】")
        lines.extend(_fmt(tech_scored) or ["（本轮没有与剧情相关的手法候选）"])
    if include_style:
        lines.append("【场面级文笔/文风候选】")
        if style_scored:
            lines.extend(_fmt(style_scored))
        elif base_style_count:
            lines.append(
                f"（无场面级文笔/文风条目；库内 {base_style_count} 条文笔/文风均为全书级，"
                "不参与写章检索）"
            )
        else:
            lines.append("（库内没有文笔/文风条目）")
        if draft_lines:
            lines.append("")
            lines.append("【本书文风三区未配置】")
            lines.append(
                "知识库里的全书级文笔/文风草稿（按题材列出，需按本书基调筛选；"
                "与基调撕裂的不选；非写章块条目、不进 picks；"
                "建议在设定·文风 → 按题材填文风采纳，长期生效）："
            )
            lines.extend(draft_lines)
    return ToolResult(ok=True, summary=_clip("\n".join(lines), 2600))


KB_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="kb_search",
        kind="read",
        parameters={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "关键词"},
                "genre": {"type": "string", "description": "题材（可空）"},
                "concept": {"type": "string", "description": "概念（可空）"},
            },
        },
        description="检索作家的知识库条目（按关键词/题材/概念；只读）。",
        fn=_kb_search,
    ),
    Tool(
        name="kb_read",
        kind="read",
        parameters={
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "条目 id"},
            },
            "required": ["entry_id"],
        },
        description="读一条知识库条目全文（只读）。",
        fn=_kb_read,
    ),
    Tool(
        name="kb_create_entry",
        kind="write",
        feature_key="ai-plan",
        requires_feature="assistant-execute",
        parameters={
            "type": "object",
            "properties": {
                "genre": {"type": "string", "description": "题材"},
                "concept": {"type": "string", "description": "概念"},
                "title": {"type": "string", "description": "标题"},
                "payload": {"type": "object", "description": "条目内容（对象）"},
                "instruction": {"type": "string", "description": "补充说明（可空）"},
            },
            "required": ["genre", "concept", "title", "payload"],
        },
        description="新建知识库条目（受作家授权梯度管控；写入后有回执可撤销）。",
        fn=_kb_create_entry,
    ),
    Tool(
        name="kb_update_entry",
        kind="write",
        feature_key="ai-plan",
        requires_feature="assistant-execute",
        parameters={
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "条目 id"},
                "fields": {
                    "type": "object",
                    "description": "要改的字段",
                    "properties": {
                        "title": {"type": "string"},
                        "instruction": {"type": "string"},
                        "payload": {"type": "object"},
                    },
                },
            },
            "required": ["entry_id", "fields"],
        },
        description="改知识库条目（受作家授权梯度管控；既有闸门校验原样生效；写入后有回执可撤销）。",
        fn=_kb_update_entry,
    ),
Tool(
        name="kb_search_craft",
        kind="read",
        risk_level="low",
        feature_key="kb-official",
        parameters={
            "type": "object",
            "properties": {
                "chapter_ref": {"type": "string", "description": "章 ref（缺省查询时按本章概要/剧情条目匹配）"},
                "query": {"type": "string", "description": "剧情描述关键词（可空）"},
                "concept": {"type": "string", "enum": ["手法", "文风", "文笔"], "description": "只要某一类（可空＝全部）"},
                "limit": {"type": "integer", "description": "条数上限（默认 12，最大 30）"},
            },
        },
        description=(
            "按本章剧情检索知识库里的写法候选（题材内；返回条目 id 供方案卡 picks 用）。"
            "结果分「手法候选」与「场面级文笔/文风候选」两段；全书级文笔/文风不进写章检索"
            "（走本书设定·文风三区），本书三区未配置时本工具会附全书级草稿提示（不进 picks）。"
            "生成正文前必调：先 read_chapter 看本章素材，再拿剧情调本工具；没命中会明说。"
        ),
        fn=_kb_search_craft,
    ),
)
