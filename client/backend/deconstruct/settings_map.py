"""拆书产物 JSON → 开书设定的投影层（c-deconstruct-settings-contract）。

产物 JSON/md 是**分析稿**：证据章号、confidence、原文未明确都该保留在任务资料里；
设定页是**操作稿**：只留可执行文本，会进入写作提示词。本模块只读产物 JSON，
产出可直接写进设定 KV / 数据表的值——不修改源 JSON，也不反解 md。

所有设定文本统一过 `clean_settings_text`：
- 剥 `【第N章】`、`（第N章）`、裸 `第N章` 证据；
- 剥 `confidence:` / `evidence_ch:` / `note:` 分析尾巴；
- 单独「原文未明确」置空，句中该短语删除；
- 压单行、清理悬挂标点、按句界截断。

字段映射矩阵（每维度显式列明；未列出的产物字段只留任务资料）：
- style：role/rules/craft/examples/taboo → 叙事身份/硬约束/描写手法/例句/硬约束（避免…）
- world：stage/power/cost/history/factions/constraints/extra → 同名字段；history.origin 保留证据
- mainplot：fullstory/ending → story_arc；arcs 只留任务资料
- intro：intro → synopsis
- genre：genre → story.genre；promise → novel_genre.promise_note；tags 只留任务资料
- structure：volumes[].title/ch_range → 卷行；chapters/pacing_notes 只留任务资料
- techniques：techniques.repro_steps/emotion_chain → 文风 rules；borrowable → craft；
  avoid → rules（避免…）；reader_needs 只留任务资料
- foreshadow：desc/note/type/priority/plant_ch/payoff_ch/status → 台账；confidence 只留任务资料
- characters：name/role/persona/aliases/dossier 八格 → 角色卡；plot 末尾保留一条 evidence_ch
  供角色页回查，其余格不进证据；confidence 只留任务资料
- relations：edges → 关系行（按解析后的 owner/other 归并，同对多关系取并集；
  rel_type 放不下的类型并入 note「另含关系…」）；ch_ref 保留 evidence_ch；
  factions/quote/raw/confidence 只留任务资料
"""

from __future__ import annotations

import re

_EVIDENCE_TAG_RE = re.compile(r"【[^】]{0,50}章】")
# 括注证据：以「第」开头或括注内含「见/详见/参见 第N章」都算分析工件。
_EVIDENCE_PAREN_RE = re.compile(
    r"[（(][^）)]{0,60}?第\s*[0-9０-９][0-9０-９,，、\-—~～至\s]*章[^）)]*[）)]"
)
# 裸证据：可带「如/见/详见/参见」引导词；只认数字章号（「每3章」不匹配）。
# 连续引用（第1章和第2章／第1章至第258章）整段剥——只剥单个会留「和。」「至」残渣。
_CHAPTER_REF = r"第\s*[0-9０-９][0-9０-９,，、\-—~～至\s]*章"
# 证据后的指代尾巴（「如第3章所述」「见第3章所示」「第3章里的」）随引用一起剥
_REF_SUFFIX = r"(?:中所|所述|所示|所载|所记|里的|中的|内的|记载|提到|中(?![段后前]))?(?:的)?"
_EVIDENCE_BARE_RE = re.compile(
    rf"(?:如|见|详见|参见|参看)?\s*{_CHAPTER_REF}"
    rf"(?:\s*[和与及、,，\-—~～至到\s]\s*{_CHAPTER_REF})*{_REF_SUFFIX}"
)
# 分析元数据尾巴：confidence: high，note: … / evidence_ch: 第3章
_ANALYSIS_TAIL_RE = re.compile(
    r"(?:\s*[，,；;]\s*)?(?:confidence|evidence_ch|note)\s*[:：].*$", re.IGNORECASE
)
# 「原文未明确」连同同小句的分析尾巴一起剥（如「，原文未明确反例」「原文未明确刻意规避」）
_UNCLEAR_CLAUSE_RE = re.compile(r"[，,；;]?\s*原文未明确[^，。；;!?]*")
_SENT_END = "。！？；!?！？"
_EMPTY_PAREN_RE = re.compile(r"[（(]\s*[）)]")
_DANGLING_PUNCT_RE = re.compile(r"[，,；;、]\s*([。！？；!?]|$)")
_LEADING_PUNCT_RE = re.compile(r"^[，,；;、\s]+")
_SPACES_RE = re.compile(r"\s{2,}")
_TEXT_CHAR_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")


def clip_sentences(text: str, limit: int | None) -> str:
    """超限时退到上限内最后一个句界；宁短一句，不切半句。"""
    if not limit or len(text) <= limit:
        return text
    cut = text[:limit]
    last = max(cut.rfind(ch) for ch in _SENT_END)
    return cut[: last + 1] if last >= limit // 2 else cut


def clean_settings_text(value, limit: int | None = None) -> str:
    """产物文本 → 设定安全文本（证据/分析工件不进设定）。"""
    text = str(value or "")
    if not text.strip():
        return ""
    text = _EVIDENCE_TAG_RE.sub("", text)
    text = _EVIDENCE_PAREN_RE.sub("", text)
    text = _EVIDENCE_BARE_RE.sub("", text)
    text = _ANALYSIS_TAIL_RE.sub("", text)
    text = _UNCLEAR_CLAUSE_RE.sub("", text)
    text = _EMPTY_PAREN_RE.sub("", text)
    text = re.sub(r"\s*\n+\s*", " ", text)
    text = _DANGLING_PUNCT_RE.sub(r"\1", text)
    text = _LEADING_PUNCT_RE.sub("", text)
    text = _SPACES_RE.sub(" ", text).strip()
    text = text.strip("，,；;、 ")
    if not text or not _TEXT_CHAR_RE.search(text):
        return ""
    return clip_sentences(text, limit)


def first_sentence(value, limit: int = 100) -> str:
    """叙事身份只取第一句（旧 narration 是整段分析稿）。"""
    text = clean_settings_text(value)
    stop = re.search(r"[。！？；!?]", text)
    if stop:
        text = text[: stop.end()]
    return clip_sentences(text, limit)


def _entry_line(name, how, limit: int = 500) -> str:
    name = clean_settings_text(name, 60)
    how = clean_settings_text(how, limit)
    return f"{name}：{how}" if name and how else (name or how)


def entries(values) -> list[str]:
    """规则/手法条目 → 「名：怎么用」单行；兼容字符串/单对象/字典映射。"""
    if isinstance(values, dict):
        if any(k in values for k in ("name", "how", "example", "description", "rule")):
            items = [values]
        else:
            items = [f"{k}：{v}" for k, v in values.items() if str(v or "").strip()]
    elif isinstance(values, list):
        items = values
    else:
        items = [values] if values else []
    out: list[str] = []
    for r in items:
        if isinstance(r, dict):
            how = (
                r.get("how")
                or r.get("rule")
                or r.get("example")
                or r.get("description")
                or ""
            )
            line = _entry_line(r.get("name", ""), how)
        else:
            line = clean_settings_text(r, 500)
        if line and line not in out:
            out.append(line)
    return out


def _items(value) -> list:
    """产物数组容错：str/单对象按一条；None/其他标量给空。"""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return [value] if isinstance(value, str) and value.strip() else []


def style_body(data: dict) -> dict:
    """style 产物 → put_style body（三区＋例句；taboo 并入硬约束）。"""
    if not isinstance(data, dict):
        return {}
    role = first_sentence(data.get("role")) or first_sentence(data.get("narration"))
    rules = entries(data.get("rules"))
    if not rules:
        for label, key in (("对话", "dialogue"), ("节奏", "rhythm")):
            text = clean_settings_text(data.get(key), 500)
            if text:
                rules.append(f"{label}：{text}")
    craft = entries(data.get("craft")) or entries(data.get("features"))

    # taboo 没有独立设定字段，归入硬约束（「避免…」）；去掉原文未明确等分析尾巴。
    for t in _items(data.get("taboo")):
        if isinstance(t, dict):
            line = _entry_line(t.get("name", ""), t.get("how", ""))
            line = f"避免{line}" if line else ""
        else:
            line = clean_settings_text(t, 500)
        if line and line not in rules:
            rules.append(line)

    examples: list[str] = []
    for e in _items(data.get("examples")):
        text = e.get("example") if isinstance(e, dict) else e
        text = clean_settings_text(text, 300)
        if text and text not in examples:
            examples.append(text)

    body: dict = {}
    if role:
        body["role"] = role
    if rules:
        body["rules"] = rules
    if craft:
        body["craft"] = craft
    if examples:
        body["few_shot_examples"] = examples[:3]
    return body


def merge_relation_labels(types, note, rel_limit: int = 20, note_limit: int = 300) -> tuple[str, str]:
    """同对多关系 → (rel_type, note)。

    DB 的 rel_type 只有 20 字：能放下的类型进 rel_type，放不下的整条并入 note
    （「另含关系：…」），不静默丢类型。
    """
    cleaned: list[str] = []
    for t in _items(types):
        t = clean_settings_text(t, 40)
        if t and t not in cleaned:
            cleaned.append(t)
    kept: list[str] = []
    overflow: list[str] = []
    used = 0
    for t in cleaned:
        add = len(t) + (1 if kept else 0)
        if used + add <= rel_limit:
            kept.append(t)
            used += add
        else:
            overflow.append(t)
    note = clean_settings_text(note, note_limit)
    if overflow:
        extra = "另含关系：" + "、".join(overflow)
        note = f"{note}；{extra}" if note else extra
    return "、".join(kept) or "关系", note[:note_limit]


def _paragraph(entries_value, value_limit: int | None) -> str:
    if not isinstance(entries_value, list):
        return clean_settings_text(entries_value, value_limit)
    parts: list[str] = []
    for i in entries_value:
        if isinstance(i, dict):
            name = clean_settings_text(i.get("name", ""), 60)
            rule = clean_settings_text(i.get("rule", i.get("note", "")), value_limit)
            line = f"{name}：{rule}" if name and rule else (name or rule)
        else:
            line = clean_settings_text(i, value_limit)
        if line:
            parts.append(line)
    return "\n".join(parts)


def world_body(data: dict, unclamped: bool = False) -> dict:
    """world 产物 → normalize_world 输入（修复 extra 的 key/value 形状）。"""
    if not isinstance(data, dict):
        return {}
    para_limit, value_limit = (None, None) if unclamped else (800, 200)
    no_power_txt = str(data.get("no_power", ""))
    return {
        "no_power": "无超凡" in no_power_txt or "原文未明确" in no_power_txt,
        "stage": clean_settings_text(data.get("stage", ""), para_limit),
        "power": _paragraph(data.get("power"), para_limit),
        "cost": _paragraph(data.get("cost"), para_limit),
        "history": [
            {
                "key": clean_settings_text(i.get("name", ""), 40),
                "value": clean_settings_text(i.get("note", ""), value_limit),
                # origin 是设定数据模型里明确的证据字段，保留章号便于回查
                "origin": (
                    "" if str(i.get("evidence_ch", "")).strip() == "原文未明确"
                    else str(i.get("evidence_ch", ""))[:40]
                ),
            }
            for i in (data.get("history") or []) if isinstance(i, dict)
        ],
        "factions": [
            {
                "name": clean_settings_text(i.get("name", ""), 20),
                "note": clean_settings_text(i.get("rule", i.get("note", "")), value_limit),
            }
            for i in (data.get("factions") or []) if isinstance(i, dict)
        ],
        "constraints": [
            {
                "key": clean_settings_text(i.get("name", ""), 20),
                "value": clean_settings_text(i.get("rule", i.get("note", "")), value_limit),
            }
            for i in (data.get("constraints") or []) if isinstance(i, dict)
        ],
        # 新契约 extra 是 {key,value}（旧代码按 name/note 读，74 条会全空）
        "extra": [
            {
                "key": clean_settings_text(i.get("key", i.get("name", "")), 40),
                "value": clean_settings_text(i.get("value", i.get("note", "")), value_limit),
            }
            for i in (data.get("extra") or []) if isinstance(i, dict)
        ],
    }


def mainplot_body(data: dict) -> dict:
    """mainplot 产物 → story_arc 两键（fullstory/ending）。"""
    if not isinstance(data, dict):
        return {}
    fullstory = clean_settings_text(data.get("fullstory"), 2000)
    if not fullstory:
        arcs = [
            f"{a.get('title', '')}：{a.get('summary', '')}"
            for a in (data.get("arcs") or []) if isinstance(a, dict)
        ]
        fullstory = clean_settings_text("；".join(arcs), 2000)
    if not fullstory:
        fullstory = clean_settings_text(data.get("ending"), 2000)
    ending = data.get("ending") if isinstance(data.get("ending"), dict) else {}

    def _cell(v) -> str:
        return clean_settings_text(v, 150)

    return {
        "fullstory": fullstory or "原文未明确",
        "ending": {f: _cell(ending.get(f, "")) for f in ("scene", "hero", "tone")},
    }


def intro_genre_body(data_intro: dict, data_genre: dict) -> dict:
    """简介/题材 → create_project 参数＋novel_genre.promise_note。"""
    intro = data_intro if isinstance(data_intro, dict) else {}
    genre = data_genre if isinstance(data_genre, dict) else {}
    return {
        "synopsis": clean_settings_text(intro.get("intro"), 600),
        "genre": clean_settings_text(genre.get("genre"), 40),
        # tags 是题材标签（不是「读者预期」短句），只留任务资料；promise 是真正的承诺句
        "promise_note": clean_settings_text(genre.get("promise"), 200),
    }


def structure_volume(value: dict) -> dict:
    """单卷产物 → {title, summary}；带「原文未明确」的标题交给服务端兜底。"""
    if not isinstance(value, dict):
        return {"title": "", "summary": ""}
    title = clean_settings_text(value.get("title"), 60)
    if "原文未明确" in str(value.get("title", "")):
        title = ""
    rng = str(value.get("ch_range", "") or "").strip()
    note = clean_settings_text(value.get("note"), 260)
    summary = "；".join(x for x in (rng, note) if x)[:300]
    return {"title": title, "summary": summary}


def technique_lines(data: dict) -> tuple[list[str], list[str]]:
    """techniques 产物 → (rules, craft)。

    techniques[].how 在新契约里是 repro_steps/emotion_chain/example；只取 name
    会把最有价值的「怎么复现」整段丢掉。
    """
    if not isinstance(data, dict):
        return [], []
    rules: list[str] = []
    craft: list[str] = []

    def _add(target: list[str], line: str) -> None:
        if line and line not in target:
            target.append(line)

    for t in _items(data.get("techniques")):
        if not isinstance(t, dict):
            continue
        name = clean_settings_text(t.get("name"), 60)
        steps = t.get("repro_steps")
        if isinstance(steps, list):
            how = "；".join(
                x for x in (clean_settings_text(s, 240) for s in steps) if x
            )
        elif isinstance(steps, str):
            how = clean_settings_text(steps, 480)
        else:
            how = clean_settings_text(t.get("how") or t.get("example"), 480)
        chain = t.get("emotion_chain")
        if isinstance(chain, list):
            chain_txt = "→".join(
                x for x in (clean_settings_text(c, 60) for c in chain) if x
            )
            if chain_txt and chain_txt not in how:
                how = f"{how}；情绪链：{chain_txt}" if how else f"情绪链：{chain_txt}"
        line = _entry_line(name, how)
        _add(rules, line)

    for b in _items(data.get("borrowable")):
        text = b.get("item") if isinstance(b, dict) else b
        _add(craft, clean_settings_text(text, 500))

    for a in _items(data.get("avoid")):
        text = a.get("item") if isinstance(a, dict) else a
        line = clean_settings_text(text, 500)
        _add(rules, f"避免：{line}" if line else "")
    return rules, craft


def hook_items(data: dict) -> list[dict]:
    """foreshadow 产物 → NovelHook 条目；note 并入描述，不再整段丢弃。"""
    if not isinstance(data, dict):
        return []
    out: list[dict] = []
    for h in _items(data.get("hooks")):
        if not isinstance(h, dict):
            continue
        plant = h.get("plant_ch")
        payoff = h.get("payoff_ch")
        resolved = str(h.get("status", "")) == "paid" or payoff not in (None, "原文未明确")
        tags: list[str] = []
        if plant not in (None, "原文未明确"):
            tags.append(f"（埋设于第{plant}章）")
        if resolved and payoff not in (None, "原文未明确"):
            tags.append(f"（收于第{payoff}章）")
        tags_txt = "".join(tags)
        # 先给埋设/回收章留位置——note 再长也不能把台账章号挤出 300 字上限
        base = clean_settings_text(h.get("desc"), max(0, 300 - len(tags_txt)))
        note = clean_settings_text(h.get("note"), 120)
        if note and note not in base:
            room = 300 - len(tags_txt) - len(base) - 2
            if room > 10:
                base = f"{base}（{note[:room]}）" if base else note[:room]
        desc = f"{base}{tags_txt}"[:300]
        hook_type = str(h.get("type", "")).strip()
        priority = {"high": 1, "mid": 2, "low": 3}.get(str(h.get("priority", "")).strip(), 2)
        out.append({
            "description": desc,
            "planned_volume_no": None,
            "type": hook_type,
            "priority": priority,
            "status": "resolved" if resolved else "active",
        })
    return out
