"""知识映射纯核心（SDK 首模块——boss 2026-11-09 拍板 SDK 化）。

拆书产物 → 知识对象（dataclass EntryData）的映射逻辑，自 C 端
kb/deconstruct_import 机械迁入：映射口径/正则/闸门与 C 端逐字同源（C 端
kb/deconstruct_import 已改薄壳调本模块——两链共用一份映射，永不漂移）。

零应用层依赖：不引 ORM/DB/AI 客户端/应用配置——AI 调用与落库由调用方
（C 端编排层 / 知识仓批量驱动）承接。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .concepts import emotion_phrase, normalize_scene
from .payloads import validate_payload


@dataclass
class EntryData:
    """映射产出的知识对象；字段名与 C 端知识 ORM 的业务列一一对应。"""

    user_id: str = ""
    genre: str = ""
    concept: str = ""
    concept_id: str = ""
    title: str = ""
    payload_json: str = "{}"
    payload_version: int = 1
    instruction: str = ""
    example: str = ""
    negative_example: str = ""
    when_json: str = "{}"
    evidence: str = ""
    evidence_json: str = "{}"
    src_kind: str = "deconstruct"
    src_ref: str = ""
    src_key: str = ""
    src_novel_name: str = ""


# ── 自 C 端 kb/deconstruct_import 机械迁入（逐字同源；勿在此另起口径）──

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
) -> EntryData | None:
    """构造条目（EntryData 形态）；payload 不合契约返回 None（由调用方记 warning）。"""
    try:
        clean_payload = validate_payload(concept, payload)
    except ValueError:
        return None
    return EntryData(
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


# 世界正文里粘尾的元数据：可信度 token 与章证据锚（剥出分立落字段，正文保持干净案例）
_WORLD_CONF_RE = None  # 延迟初始化（避免模块加载期正则编译开销？量小直接编）
import re as _re

_WORLD_CONF_RE = _re.compile(r"[（(；;]\s*confidence[:：]\s*(high|mid|low)\s*[）)]?")
# 拆书产物「原文未明确」哨兵片段——与证据列哨兵同口径（c-kb-char-evidence 判例）
_WORLD_VAGUE_RE = _re.compile(r"[，,；;（(]\s*[^，,。；;（）()]{0,8}原文未明确\s*[）)?]?")

_WORLD_EV_RE = _re.compile(
    r"（(?=[^（）]*第[\d零一二三四五六七八九十百、，,；;\s～\-—至/]+章)[^（）]*(?:（[^（）]*）[^（）]*)*）"
)
# 产物还有一种「缺右括号」的残形：正文以「（第115、116、117、118章。」结尾（真机 13路 实锤，
# 81/168 条世界实例粘这种尾巴）——闭形剥不动，补开形（吞到串尾）
_WORLD_EV_OPEN_RE = _re.compile(
    r"（第[\d零一二三四五六七八九十百、，,；;\s～\-—至/]+[^（）]*$"
)


def _clean_style_text(text: str) -> tuple[str, str, str]:
    """文风/文笔正文净化：剥粘尾章证据锚与可信度（世界同源正则）。

    返回 (净文, 章证据, 可信度)——剥出的元数据由调用方挂进 payload 字段。
    """
    raw = _line(text, 340)
    ev_parts = [mm.group(0)[1:-1] for mm in _WORLD_EV_RE.finditer(raw)]
    raw = _WORLD_EV_RE.sub("", raw)
    m_open = _WORLD_EV_OPEN_RE.search(raw)
    if m_open:
        ev_parts.append(m_open.group(0)[1:].rstrip("。；;").strip())
        raw = raw[: m_open.start()].rstrip("；;").strip()
    conf = ""
    m_conf = _WORLD_CONF_RE.search(raw)
    if m_conf:
        conf = m_conf.group(1)
        raw = _WORLD_CONF_RE.sub("", raw)
    ev = "；".join(p for p in ev_parts if p)
    if not conf and ev:
        m_c2 = _WORLD_CONF_RE.search(ev)
        if m_c2:
            conf = m_c2.group(1)
            ev = _WORLD_CONF_RE.sub("", ev).rstrip("；;").strip()
    return raw.rstrip("；;").strip(), ev, conf


def _attach_style_meta(payload: dict, item: object) -> None:
    """把产物条目（或正文剥出）的章证据/可信度挂进 payload 字段。"""
    if not isinstance(item, dict):
        return
    ch = _line(str(item.get("evidence_ch") or "").strip(), 60)
    if ch:
        payload.setdefault("evidence_ch", ch)
    conf = str(item.get("confidence") or "").strip()
    if conf in ("high", "mid", "low"):
        payload.setdefault("confidence", conf)


def genre_from_products(products: dict) -> str:
    """产物题材维度 → 目录大类（未命中返回空串＝未定题材）。"""
    from .theme_catalog import normalize_theme

    data = _data(products.get("genre")) if isinstance(products, dict) else {}
    return normalize_theme(str(data.get("genre") or "").strip())


def map_deconstruct_products(
    user_id: str,
    task_id: str,
    genre: str,
    products: dict,
    *,
    src_ref: str | None = None,
) -> tuple[list[EntryData], list[str]]:
    """拆书产物 → 知识条目列表。返回 (entries, warnings)。

    src_ref：幂等来源键，默认 task_id；批量脚本传内容指纹，使同一本书重拆后
    再收录仍是同一批条目（src_key 序号稳定，重复项跳过不重复写）。
    """
    entries: list[EntryData] = []
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
        conf = str(item.get("confidence") or "").strip()
        if conf in ("high", "mid", "low"):
            payload["confidence"] = conf
        # 打法类型（知识树 v2 场面打法分家）：归一到五类，未收录/看不清不落→兜底桶
        _kind_norm = {
            "大招": "大招", "大招打法": "大招", "终局": "大招",
            "体术": "体术", "体术打法": "体术", "肉搏": "体术", "武技": "体术",
            "兵器": "兵器", "兵器打法": "兵器", "武器": "兵器",
            "异能": "异能", "异能打法": "异能", "法术": "异能", "超能力": "异能",
            "群战": "群战", "群战打法": "群战", "混战": "群战",
        }
        raw_kind = _kind_norm.get(str(item.get("kind") or "").strip())
        if raw_kind:
            payload["kind"] = raw_kind
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
        # 证据串拼原文例（评审 P2：与主卡同语义）；老产物无 example 回落 note
        evidence, ev_json = _ev(
            item.get("evidence_ch") if isinstance(item, dict) else "",
            (item.get("example") or item.get("note")) if isinstance(item, dict) else "",
        )
        add(
            "technique", "手法", text, {"instruction": text, "scene": "日常"},
            instruction=text,
            # boss 2026-11-08：每个手法都要有原文案例——可借鉴套路也带 example
            example=str(item.get("example") or "") if isinstance(item, dict) else "",
            evidence=evidence, evidence_json=ev_json,
        )

    for item in _items(tech.get("avoid")):
        text = _text_of(item, "item", "content", "text", limit=200)
        if not text:
            continue
        # 证据串拼原文例（评审 P2：与主卡同语义）；老产物无 example 回落 note
        evidence, ev_json = _ev(
            item.get("evidence_ch") if isinstance(item, dict) else "",
            (item.get("example") or item.get("note")) if isinstance(item, dict) else "",
        )
        add(
            "technique", "手法", f"避免：{text}",
            {"instruction": _line(f"避免：{text}", 240), "negative": text, "scene": "日常"},
            instruction=f"避免：{text}", negative_example=text,
            # 不建议模仿的原文案例（新契约 example；老产物 note 里的原文表现不混入）
            example=str(item.get("example") or "") if isinstance(item, dict) else "",
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
            # 原文案例优先；老产物 example 缺位回落 transferable（不回归）
            example=str(
                (item.get("example") or item.get("transferable") or "")
                if isinstance(item, dict) else ""
            ),
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
    # rules 原落文笔（旧口径）；「战斗短句」「悲喜交替」这类场景规则是文风的声音侧面。
    # 2026-11-08 结构化：name/how/章证据/可信度分立（正文粘尾元数据与世界同剥）
    for i, item in enumerate(_items(style.get("rules"))):
        name = _text_of(item, "name", "title", limit=40)
        how, ev_ext, conf_ext = _clean_style_text(_text_of(item, "how", "rule", "craft", "content", limit=280))
        text = _line(f"{name}：{how}" if name and how else (how or name), 500)
        if not text:
            continue
        payload = {"slot": "rule", "text": text}
        if name:
            payload["name"] = name
        if how:
            payload["how"] = how
        if ev_ext:
            payload["evidence_ch"] = ev_ext
        if conf_ext:
            payload["confidence"] = conf_ext
        _attach_style_meta(payload, item)
        evidence, ev_json = _ev(item.get("evidence_ch") if isinstance(item, dict) else "")
        if payload.get("evidence_ch") and not evidence:
            evidence = payload["evidence_ch"]
        add(
            "style.rule", "文风", name or f"场景规则 {i + 1}",
            payload,
            instruction=text, evidence=evidence, evidence_json=ev_json,
        )

    # ─── 文笔（写法 / 忌用）── 2026-11-08 结构化：name/how/章证据/可信度分立
    for section, prefix, slot, label in (
        ("craft", "craft.craft", "craft", "写法"),
    ):
        for i, item in enumerate(_items(style.get(section))):
            name = _text_of(item, "name", "title", limit=40)
            how, ev_ext, conf_ext = _clean_style_text(_text_of(item, "how", "rule", "craft", "content", limit=200))
            text = _line(f"{name}：{how}" if name and how else (how or name), 160)
            if not text:
                continue
            payload = {"slot": slot, slot: text}
            if name:
                payload["name"] = name
            if how:
                payload["how"] = _line(how, 160)
            if ev_ext:
                payload["evidence_ch"] = ev_ext
            if conf_ext:
                payload["confidence"] = conf_ext
            _attach_style_meta(payload, item)
            evidence, ev_json = _ev(item.get("evidence_ch") if isinstance(item, dict) else "")
            if payload.get("evidence_ch") and not evidence:
                evidence = payload["evidence_ch"]
            add(
                prefix, "文笔", name or f"{label} {i + 1}",
                payload,
                instruction=text, evidence=evidence, evidence_json=ev_json,
            )

    for i, item in enumerate(_items(style.get("taboo"))):
        name = _text_of(item, "name", "title", limit=40)
        how, ev_ext, conf_ext = _clean_style_text(_text_of(item, "how", "rule", "content", limit=140))
        text = _line(f"{name}：{how}" if name and how else (how or name), 160)
        if not text:
            continue
        # name 实数据常自带「忌」（忌书面长句）；已带就不再叠「忌用·」，否则读成病句。
        if not text.startswith("忌"):
            text = _line(f"忌用·{text}", 160)
        payload = {"slot": "rule", "rule": text}
        if name:
            payload["name"] = name
        if how:
            payload["how"] = _line(how, 140)
        if ev_ext:
            payload["evidence_ch"] = ev_ext
        if conf_ext:
            payload["confidence"] = conf_ext
        _attach_style_meta(payload, item)
        evidence, ev_json = _ev(item.get("evidence_ch") if isinstance(item, dict) else "")
        if payload.get("evidence_ch") and not evidence:
            evidence = payload["evidence_ch"]
        add(
            "craft.taboo", "文笔", name or f"忌用 {i + 1}",
            payload,
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
        raw = _WORLD_VAGUE_RE.sub("", _line(content, 340)).rstrip("，,；; ").strip()
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
        conf = str(item.get("confidence") or "").strip()
        if conf in ("high", "mid", "low"):
            payload["confidence"] = conf
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
