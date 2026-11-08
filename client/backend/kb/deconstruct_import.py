"""拆书产物 → 知识库条目映射（c-kb-import 批4；2026-11-03 对齐真实产物形状）。

产物形状单源 = `deconstruct/pipeline.py` 写 `products_json` 的契约：
    {dim: {"file": 文件名, "data": {...}}}
各维度 data 键（真机产物实证）：techniques=reader_needs/techniques/borrowable/avoid；
style=role/rules/craft/examples/taboo；world=no_power/stage/power/cost/history/
factions/constraints/extra；characters=characters[]；genre=genre/tags/promise。

映射口径：
- 手法 ← techniques.techniques（名称＋复现步骤）＋borrowable/avoid/reader_needs
- 文风 ← style.role（叙事身份）＋style.examples（逐字示范段）
- 文笔 ← style.rules/craft/taboo（规则/写法/忌用）
- 世界设定 ← world 各分区（constraint 分区落 hard）
- 角色设定 ← characters[].persona/档案八格
- mainplot/structure/relations/intro 不收（P1，消费链未建）

每条 payload 都过 `kb.payloads.validate_payload` 强校验（写法块/选择器读的就是这些键）；
不合契约的条目跳过并进 warnings，MUST NOT 把脏 payload 写进库。
幂等键 = (user_id, src_ref, src_key)；src_ref 默认 task_id，批量脚本可传内容指纹。
"""

from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kb.concepts import emotion_phrase, normalize_scene
from kb.payloads import validate_payload
from models.kb import KbKnowledge

_WS_RE = re.compile(r"\s+")
# 行首结构标记（# - * > · 或整段【…】）：写法块结构消毒同口径——
# 指令含换行/以结构标记开头会在组装期被跳过，入库前就拍平成单行。
_LEAD_MARK_RE = re.compile(r"^(?:[-*#>·]+|【[^】]*】)\s*")

_MAX_CHARACTERS = 10
# world.extra 是书内道具/零散设定（一条 60+ 个）：限量收，避免批量灌库时道具淹没分区事实
_MAX_WORLD_EXTRA = 20


def _data(product) -> dict:
    """维度产物 → data 字典（兼容老任务直接是平铺 dict 的形状）。"""
    if isinstance(product, dict):
        inner = product.get("data")
        if isinstance(inner, dict):
            return inner
        return product
    return {}


def _items(value) -> list:
    """列表归一：list 原样；dict 取常见包裹键；其余空表。"""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("items", "list", "entries"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def _line(text, limit: int) -> str:
    """单行化＋去行首结构标记＋截断。"""
    t = _WS_RE.sub(" ", str(text or "")).strip()
    t = _LEAD_MARK_RE.sub("", t).strip()
    return t[:limit]


def _sentence(text: str, limit: int) -> str:
    """知识文案第一要求是念得通顺：超长按分句标点收尾，不留悬空分隔符，句末补句号。

    与内容仓 `tools/deconstruct_batch.py::_sentence` 同口径（写进提示词的就是这句，
    腰斩/悬空在写法块里会读成半句话）。
    """
    t = str(text or "").strip()
    if len(t) > limit:
        window = t[:limit]
        cut = max(window.rfind(p) for p in "；。！？，")
        if cut >= limit // 2:
            window = window[: cut + 1]
        t = window.rstrip("；，、：; ")
        if len(t) > limit:
            t = t[:limit]
    t = t.rstrip("；，、：; ")
    if t and t[-1] not in "。！？…":
        t = t[: limit - 1] + "。" if len(t) >= limit else t + "。"
    return t


def _text_of(item, *keys: str, limit: int = 300) -> str:
    """条目取文本：dict 按候选键取，str 原样。"""
    if isinstance(item, str):
        return _line(item, limit)
    if isinstance(item, dict):
        for key in keys:
            if item.get(key):
                return _line(item[key], limit)
    return ""


def _ev(chapter, quote: str = "", limit: int = 500) -> tuple[str, dict]:
    """证据串＋证据 JSON（章号原样保留；quote 截断）。"""
    chapter = _line(chapter, 80)
    quote = _line(quote, 200)
    # evidence_ch 在真机产物里本身就是「第1章」「第2、6章」；只有裸章号才补包装
    head = chapter if chapter.startswith("第") else (f"第{chapter}章" if chapter else "")
    evidence = f"{head} {quote}".strip()[:limit]
    ev_json = {"quotes": [{"loc": chapter, "text": quote}]} if quote else {}
    return evidence, ev_json


def _mk_entry(
    user_id: str,
    src_ref: str,
    src_key: str,
    genre: str,
    concept: str,
    title: str,
    payload: dict,
    *,
    instruction: str = "",
    example: str = "",
    negative_example: str = "",
    evidence: str = "",
    evidence_json: dict | None = None,
    when_json: dict | None = None,
) -> KbKnowledge | None:
    """构造条目；payload 不合契约返回 None（由调用方记 warning）。"""
    try:
        clean_payload = validate_payload(concept, payload)
    except ValueError:
        return None
    return KbKnowledge(
        user_id=user_id,
        genre=genre,
        concept=concept,
        concept_id=f"{genre}:{concept}",
        title=_line(title, 40) or concept,
        payload_json=json.dumps(clean_payload, ensure_ascii=False),
        payload_version=1,
        instruction=_sentence(_line(instruction, 240), 240),
        example=str(example or "")[:500],
        negative_example=_line(negative_example, 200),
        when_json=json.dumps(when_json or {}, ensure_ascii=False),
        evidence=str(evidence or "")[:500],
        evidence_json=json.dumps(evidence_json or {}, ensure_ascii=False),
        src_kind="deconstruct",
        src_ref=src_ref,
        src_key=src_key,
        src_novel_name="",
    )


def genre_from_products(products: dict) -> str:
    """产物题材维度 → 目录大类（未命中返回空串＝未定题材）。"""
    from genres.theme_catalog import normalize_theme

    data = _data(products.get("genre")) if isinstance(products, dict) else {}
    return normalize_theme(str(data.get("genre") or "").strip())


# 世界正文里粘尾的元数据：可信度 token 与章证据锚（剥出分立落字段，正文保持干净案例）
_WORLD_CONF_RE = None  # 延迟初始化（避免模块加载期正则编译开销？量小直接编）
import re as _re

_WORLD_CONF_RE = _re.compile(r"[（(；;]\s*confidence[:：]\s*(high|mid|low)\s*[）)]?")
_WORLD_EV_RE = _re.compile(
    r"（(?=[^（）]*第[\d零一二三四五六七八九十百、，,；;\s～\-—至/]+章)[^（）]*(?:（[^（）]*）[^（）]*)*）"
)
# 产物还有一种「缺右括号」的残形：正文以「（第115、116、117、118章。」结尾（真机 13路 实锤，
# 81/168 条世界实例粘这种尾巴）——闭形剥不动，补开形（吞到串尾）
_WORLD_EV_OPEN_RE = _re.compile(
    r"（第[\d零一二三四五六七八九十百、，,；;\s～\-—至/]+[^（）]*$"
)


def map_deconstruct_products(
    user_id: str,
    task_id: str,
    genre: str,
    products: dict,
    *,
    src_ref: str | None = None,
) -> tuple[list[KbKnowledge], list[str]]:
    """拆书产物 → 知识条目列表。返回 (entries, warnings)。

    src_ref：幂等来源键，默认 task_id；批量脚本传内容指纹，使同一本书重拆后
    再收录仍是同一批条目（src_key 序号稳定，重复项跳过不重复写）。
    """
    entries: list[KbKnowledge] = []
    warnings: list[str] = []
    ref = src_ref or task_id
    seq = 0

    def add(
        prefix: str,
        concept: str,
        title: str,
        payload: dict,
        **kwargs,
    ) -> None:
        nonlocal seq
        seq += 1
        entry = _mk_entry(
            user_id, ref, f"{prefix}:{seq}", genre, concept, title, payload, **kwargs
        )
        if entry is None:
            warnings.append(f"{concept}·{title or prefix} 字段不完整，已跳过")
            return
        entries.append(entry)

    # ─── 手法（techniques / borrowable / avoid / reader_needs）───
    tech = _data(products.get("techniques"))
    for item in _items(tech.get("techniques")):
        if not isinstance(item, dict):
            continue
        name = _line(item.get("name") or item.get("title"), 40)
        steps = [_line(s, 120) for s in _items(item.get("repro_steps")) if _line(s, 120)][:5]
        if not name and not steps:
            continue
        instruction = _line(f"{name}：{'；'.join(steps)}", 240) if steps else name
        if not instruction:
            continue
        model_scene = normalize_scene(str(item.get("scene") or ""))
        emotion = emotion_phrase(str(item.get("emotion_chain") or ""))
        payload = {"instruction": instruction, "scene": model_scene or "日常"}
        if steps:
            payload["steps"] = steps
        if emotion:
            payload["emotion"] = emotion
        evidence, ev_json = _ev(item.get("evidence_ch"), item.get("example") or "")
        # when 是「适用范围」不是记录字段：模型没给场面就不写，保持全章适用；
        # 硬填「日常」会让条目在打斗/对峙/无场景信号章全部落选（_match_score 丢弃 m<=0）。
        when = {}
        if model_scene:
            when["scene"] = model_scene
        if emotion:
            when["emotion"] = emotion
        add(
            "technique", "手法", name or instruction, payload,
            instruction=instruction,
            example=str(item.get("example") or item.get("swappable") or ""),
            negative_example=str(item.get("no_copy") or ""),
            evidence=evidence, evidence_json=ev_json,
            when_json=when,
        )

    for item in _items(tech.get("borrowable")):
        text = _text_of(item, "item", "content", "text", limit=240)
        if not text:
            continue
        evidence, ev_json = _ev(
            item.get("evidence_ch") if isinstance(item, dict) else "",
            item.get("note") if isinstance(item, dict) else "",
        )
        add(
            "technique", "手法", text, {"instruction": text, "scene": "日常"},
            instruction=text, evidence=evidence, evidence_json=ev_json,
        )

    for item in _items(tech.get("avoid")):
        text = _text_of(item, "item", "content", "text", limit=200)
        if not text:
            continue
        evidence, ev_json = _ev(
            item.get("evidence_ch") if isinstance(item, dict) else "",
            item.get("note") if isinstance(item, dict) else "",
        )
        add(
            "technique", "手法", f"避免：{text}",
            {"instruction": _line(f"避免：{text}", 240), "negative": text, "scene": "日常"},
            instruction=f"避免：{text}", negative_example=text,
            evidence=evidence, evidence_json=ev_json,
        )

    for item in _items(tech.get("reader_needs")):
        need = _text_of(item, "need", "name", limit=40)
        how = _text_of(item, "how", "content", limit=240)
        if not how:
            continue
        evidence, ev_json = _ev(item.get("evidence_ch") if isinstance(item, dict) else "")
        add(
            "technique", "手法", f"读者需求：{need}" if need else how,
            {"instruction": how, "scene": "日常"},
            instruction=how,
            example=str(item.get("transferable") or "") if isinstance(item, dict) else "",
            evidence=evidence, evidence_json=ev_json,
        )

    # ─── 文风（叙事身份＋逐字示范段）───
    style = _data(products.get("style"))
    role = _line(style.get("role") or style.get("identity"), 120)
    if role:
        add(
            "style.role", "文风", "叙事身份", {"slot": "role", "role": role},
            instruction=role, evidence="文风蒸馏·叙事身份",
        )

    # 原文示范段＝逐字原文：按 2026-11-04 真机反馈不进知识库（版权红线＋作家阅读噪音），
    # 与内容仓批量工具同口径；只计数并进 warnings。写作侧的文风示范由拆书产物的
    # style_samples（书内设定 style_samples 键）承接，不经知识库。
    n_samples = len(_items(style.get("examples") or style.get("samples") or style.get("style_samples") or []))
    if n_samples:
        warnings.append(f"原文示范段 {n_samples} 条不入库（逐字原文，版权红线）")

    # ─── 文风（场景规则：一条规则一条实例——boss 2026-11-07 承接表）───
    # rules 原落文笔（旧口径）；「战斗短句」「悲喜交替」这类场景规则是文风的声音侧面
    for i, item in enumerate(_items(style.get("rules"))):
        name = _text_of(item, "name", "title", limit=40)
        how = _text_of(item, "how", "rule", "craft", "content", limit=240)
        text = _line(f"{name}：{how}" if name and how else (how or name), 500)
        if not text:
            continue
        evidence, ev_json = _ev(item.get("evidence_ch") if isinstance(item, dict) else "")
        add(
            "style.rule", "文风", name or f"场景规则 {i + 1}",
            {"slot": "rule", "text": text},
            instruction=text, evidence=evidence, evidence_json=ev_json,
        )

    # ─── 文笔（写法 / 忌用）───
    for section, prefix, slot, label in (
        ("craft", "craft.craft", "craft", "写法"),
    ):
        for i, item in enumerate(_items(style.get(section))):
            name = _text_of(item, "name", "title", limit=40)
            how = _text_of(item, "how", "rule", "craft", "content", limit=160)
            text = _line(f"{name}：{how}" if name and how else (how or name), 160)
            if not text:
                continue
            evidence, ev_json = _ev(item.get("evidence_ch") if isinstance(item, dict) else "")
            add(
                prefix, "文笔", name or f"{label} {i + 1}",
                {"slot": slot, slot: text},
                instruction=text, evidence=evidence, evidence_json=ev_json,
            )

    for i, item in enumerate(_items(style.get("taboo"))):
        name = _text_of(item, "name", "title", limit=40)
        how = _text_of(item, "how", "rule", "content", limit=140)
        text = _line(f"{name}：{how}" if name and how else (how or name), 160)
        if not text:
            continue
        # name 实数据常自带「忌」（忌书面长句）；已带就不再叠「忌用·」，否则读成病句。
        # 前缀必须参与长度截断：CraftPayload.rule 上限 160，前缀后再超会被 payload
        # 校验整条丢掉（静默消失）。
        if not text.startswith("忌"):
            text = _line(f"忌用·{text}", 160)
        evidence, ev_json = _ev(item.get("evidence_ch") if isinstance(item, dict) else "")
        add(
            "craft.taboo", "文笔", name or f"忌用 {i + 1}",
            {"slot": "rule", "rule": text},
            instruction=text, negative_example=f"{name}：{how}".strip("："),
            evidence=evidence, evidence_json=ev_json,
        )

    # ─── 世界设定（按分区；constraint 落 hard）───
    world = _data(products.get("world"))

    def add_world(part: str, title: str, content: str, *, hard: bool = False,
                  evidence: str = "", name: str = "") -> None:
        """世界条目＝结构化字段（boss 2026-11-08：内容是实际案例、元数据分立）。

        拆书产物常把章证据与可信度粘在正文尾（「（第41章；confidence:mid）」）——
        先剥出再分立落字段，正文保持干净案例；名字独立（势力名/事件名/规则名）。
        """
        raw = _line(content, 340)
        # 先剥完整章证据锚（「（第41章；confidence:mid）」整体一组——先剥可信度会吞掉
        # 锚的闭括号导致锚解不开），再剥游离的可信度 token
        # 章证据锚：全文任意位置的闭形全部剥出（真机实锤锚常嵌在句中而非仅尾），
        # 另补缺右括号的尾形
        ev_parts = [m.group(0)[1:-1] for m in _WORLD_EV_RE.finditer(raw)]
        raw = _WORLD_EV_RE.sub("", raw)
        m_open = _WORLD_EV_OPEN_RE.search(raw)
        if m_open:
            ev_parts.append(m_open.group(0)[1:].rstrip("。；;").strip())
            raw = raw[: m_open.start()].rstrip("；;").strip()
        ev_anchor = "；".join(p for p in ev_parts if p)
        conf = ""
        m_conf = _WORLD_CONF_RE.search(raw)
        if m_conf:
            conf = m_conf.group(1)
            raw = _WORLD_CONF_RE.sub("", raw)
        if not conf and ev_anchor:
            # 可信度常嵌在锚内（「第41章；confidence:mid」）——从锚里提，锚串留纯章号
            m_c2 = _WORLD_CONF_RE.search(ev_anchor)
            if m_c2:
                conf = m_c2.group(1)
                ev_anchor = _WORLD_CONF_RE.sub("", ev_anchor).rstrip("；;").strip()
        raw = raw.rstrip("；;").strip()
        if not raw:
            return
        content = _line(raw, 300)
        ch_evidence = _line(f"{ev_anchor}；{evidence}".strip("；"), 60) if (ev_anchor or evidence) else ""
        payload = {"part": part, "content": content}
        if name:
            payload["name"] = _line(name, 60)
        if ch_evidence:
            payload["evidence_ch"] = ch_evidence
        if conf:
            payload["confidence"] = conf
        if hard:
            payload["hard"] = True
        instruction = _line(f"{name}：{content}" if name else content, 320)
        add(
            f"world.{part}", "世界设定", name or title or content, payload,
            instruction=instruction, evidence=ch_evidence,
        )

    add_world("stage", "舞台", _text_of(world.get("stage"), "content", "text", limit=300))
    add_world("power", "力量/规则", _text_of(world.get("no_power"), "content", "text", limit=300))

    for part, key, hard in (
        ("power", "power", False),
        ("cost", "cost", False),
        ("history", "history", False),
        ("factions", "factions", False),
        ("constraint", "constraints", True),
    ):
        for item in _items(world.get(key)):
            # 裸串条目（constraints 常见）无名字——整串即内容（锚剥出在 add_world）；
            # 名字只在 dict 形取（否则名字带上锚像「月球…（第2章）」当标题）
            name = _text_of(item, "name", "title", "key", limit=60) if isinstance(item, dict) else ""
            body = _text_of(item, "rule", "note", "content", "value", limit=280) if isinstance(item, dict) else _text_of(item, limit=280)
            if not body and not name:
                continue
            evidence, _ = _ev(item.get("evidence_ch") if isinstance(item, dict) else "")
            add_world(part, name or f"{part} {len(entries) + 1}", body or name,
                      hard=hard, evidence=evidence, name=name)

    for item in _items(world.get("extra"))[:_MAX_WORLD_EXTRA]:
        key = _text_of(item, "key", "name", limit=60)
        value = _text_of(item, "value", "content", "note", limit=260)
        if not key and not value:
            continue
        content = f"{key}：{value}" if key and value else (value or key)
        add_world("extra", key or "补充", content)

    # ─── 角色设定（原型＋档案八格）───
    characters = _data(products.get("characters"))
    rows = characters.get("characters") or characters.get("items") or []
    if isinstance(rows, dict):
        rows = rows.get("characters") or []
    for item in _items(rows)[:_MAX_CHARACTERS]:
        if not isinstance(item, dict):
            continue
        name = _line(item.get("name") or item.get("title"), 50)
        if not name:
            continue
        payload: dict = {"archetype": name}
        for key in ("persona", "gender", "age", "race", "faction", "look",
                    "speech", "background", "plot"):
            value = _text_of(item.get(key), "value", "text", limit=300)
            if value:
                payload[key] = value
        aliases = [
            _line(a, 50) for a in _items(item.get("aliases")) if _line(a, 50)
        ][:20]
        if aliases:
            payload["aliases"] = aliases
        role = _line(item.get("role"), 10)
        if role:
            payload["role"] = role
        persona = payload.get("persona") or name
        # 证据＝产物 evidence_ch（章号口径同其他节）；「原文未明确」哨兵不过 _ev
        # （否则包成「第原文未明确章」），置空＝抽屉不出证据节；裸产物 plot 无粘尾
        raw_ch = str(item.get("evidence_ch") or "").strip()
        evidence, ev_json = ("", {}) if not raw_ch or raw_ch == "原文未明确" else _ev(raw_ch)
        add(
            "character", "角色设定", name, payload,
            instruction=persona, evidence=evidence, evidence_json=ev_json,
        )

    return entries, warnings


async def collect_task_to_kb(
    db: AsyncSession,
    user_id: str,
    task,
    *,
    genre_override: str = "",
    src_ref: str = "",
) -> dict:
    """拆书任务 → 知识库（幂等）：映射＋去重＋默认库＋标签物化。

    返回 {collected, skipped, total_mapped, warnings, genre}；
    产物为空抛 ValueError（端点转 422，脚本按失败记账）。
    """
    try:
        products = json.loads(getattr(task, "products_json", "") or "{}")
    except ValueError:
        products = {}
    if not isinstance(products, dict) or not products:
        raise ValueError("这批产物为空，无法收录")

    if genre_override:
        from genres.theme_catalog import normalize_theme

        genre = normalize_theme(str(genre_override).strip())
    else:
        genre = genre_from_products(products)

    entries, warnings = map_deconstruct_products(
        user_id, str(task.id), genre, products, src_ref=src_ref or None
    )

    existing_keys: set[str] = set()
    if entries:
        # 兼容两种来源键（脚本按书内容指纹、界面按 task_id）：任一已入库即跳过，
        # 防止同一份产物经两条入口各收一遍。src_key 序号在两次映射间稳定（同一产物）。
        refs = {src_ref or str(task.id)}
        if src_ref:
            refs.add(str(task.id))
        stmt = select(KbKnowledge.src_key).where(
            KbKnowledge.user_id == user_id,
            KbKnowledge.src_ref.in_(refs),
            KbKnowledge.src_key.in_([e.src_key for e in entries]),
        )
        existing_keys = set((await db.execute(stmt)).scalars().all())

    new_entries = [e for e in entries if e.src_key not in existing_keys]
    for entry in new_entries:
        # c-kb-summarize：收录落素材行（origin='material'）——产物卡是事实记录，
        # 经总结采纳才成为知识。不物化标签、不长默认库（素材不进选择器/星图）。
        entry.origin = "material"
        # 出处书名（c-kb-collect-dims）：此前恒空致实例出处行结构性无值——
        # 落任务书名，素材/转生实例的「源自：书名」从此有源
        entry.src_novel_name = str(getattr(task, "book_name", "") or "")[:100]
        db.add(entry)
        await db.flush()
    await db.commit()

    return {
        "collected": len(new_entries),
        "skipped": len(entries) - len(new_entries),
        "total_mapped": len(entries),
        "warnings": warnings,
        "genre": genre,
    }
