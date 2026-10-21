"""拆书出口编排（c-deconstruct-book 3.x）——建书灌设定与本地导出。

建书幂等键 = task.book_id（**项目创建成功即先落 book_id**，后续任一写入失败重试
不再重复建书，评审 P1-7）；写入一律经既有域服务，清洗越界降级并入提示清单（不中断）：

- 简介/题材 → `novels/service.create_project(synopsis=…, genre=…)` 创建参数直入；
- 世界设定 → `settings.world_model.normalize_world/put_world_merged`（factions clamp≤6，
  截断进降级清单）；no_power 仅在文本含「无超凡/原文未明确」时置真（评审 P1-2）；
- 角色 → `settings.character_service.create_character`（role 白名单映射：核心→配角；
  同名 409 → 自动改名「名（拆书N）」重试，降级清单记录）；
- 主线 → story.yaml 的 story_arc.fullstory＝各弧拼接（评审 P0-1：直读模型 JSON）；
- 文风 → `settings.style_model.put_style` 白名单键（role=叙事身份；rules=对话/节奏条目）；
- 伏笔 → `settings.hooks_service.batch_create_hooks`（新书无章：章号并入描述文本）。

产物消费 **模型 JSON**（products_json[dim].data）——md 只是渲染展示，不做反解
（评审 P0-1：渲染键来自模型契约，反解会静默丢维度）。人物关系/章卷结构/写作技法
不建书内表：任务详情即查看处（spec v1 明示）。
"""

from __future__ import annotations

import json
import os
import re

from sqlalchemy.ext.asyncio import AsyncSession

from filesystem.paths import KEY_TO_PATH
from models.deconstruct import SETTING_DIMENSION_KEYS, DeconstructJob

# 角色 role 白名单映射（character_model.ROLES = 主角/配角/反派/路人）
_ROLE_MAP = {"主角": "主角", "反派": "反派", "核心": "配角", "配角": "配角", "功能": "配角", "路人": "路人"}
# 越界归一扫描序（真机 13路 258 章实测：模型会写「核心反派」「反派→求助者」这类
# 复合 role）——主角/反派优先于核心/配角，防「核心反派」错标配角
_ROLE_SCAN_ORDER = ("主角", "反派", "配角", "核心", "功能", "路人")


def _role_normalize(raw: str) -> str:
    """产物 role → 白名单五档：精确映射优先，越界值按包含词扫描，兜底配角。"""
    if raw in _ROLE_MAP:
        return _ROLE_MAP[raw]
    for key in _ROLE_SCAN_ORDER:
        if key in raw:
            return _ROLE_MAP[key]
    return "配角"

# 建书可勾项＝7 设定项＋三项扩展（章卷结构→卷行；人物关系→关系行；写作技法→文风 rules）
IMPORT_ITEM_KEYS = (*SETTING_DIMENSION_KEYS, "structure", "relations", "techniques")


def _raw(task: DeconstructJob) -> dict:
    try:
        return json.loads(task.products_json or "{}")
    except ValueError:
        return {}


def _data(task: DeconstructJob, dim: str) -> dict:
    obj = _raw(task).get(dim)
    return obj.get("data") if isinstance(obj, dict) else {}


def _md_map(task: DeconstructJob) -> dict[str, str]:
    out: dict[str, str] = {}
    for obj in _raw(task).values():
        if isinstance(obj, dict) and obj.get("file"):
            out[obj["file"]] = obj.get("md", "")
    return out


def _selected(task: DeconstructJob) -> list[str]:
    try:
        picked = json.loads(task.selected_dims_json or "[]")
    except ValueError:
        picked = []
    return [k for k in SETTING_DIMENSION_KEYS if k in picked]


_EVIDENCE_RE = re.compile(r"【[^】]{0,50}章】")
# 括注证据：旧/新文风产物都会把「（第76章）」「（第1-258章…）」写进描述段——
# 这是分析工件，不能随文风设定注入写作提示词。
_EVIDENCE_PAREN_RE = re.compile(
    r"[（(]\s*第\s*[0-9０-９][0-9０-９,，、\-—~～至\s]*章[^）)]*[）)]"
)
_SENT_END = "。！？；!?\n"


def _clean_para(text, limit: int) -> str:
    """设定正文清洗：剥证据章标（【第N章】类分析工件，该留在任务资料）＋
    句界截断——书内段落契约有字数上限，宁可短一句也不切半句（真机实证）。"""
    text = _EVIDENCE_RE.sub("", str(text or "")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last = max(cut.rfind(ch) for ch in _SENT_END)
    return cut[: last + 1] if last >= limit // 2 else cut


def _style_text(value, limit: int) -> str:
    """文风文本清洗：剥证据章标（含括注形态）＋压成单行＋句界截断。

    旧产物（narration/dialogue/rhythm）是整段分析稿；文风三区要直接注入写作
    提示词——半句截断和「（第N章）」都会污染后续生成。
    """
    text = _EVIDENCE_RE.sub("", str(value or ""))
    text = _EVIDENCE_PAREN_RE.sub("", text)
    text = re.sub(r"\s*\n+\s*", " ", text).strip()
    return _clean_para(text, limit)


def _style_role(value) -> str:
    """叙事身份只取第一句（旧 narration 是整段分析稿，不能整段灌进 role）。"""
    text = _style_text(value, 10**9)
    stop = re.search(r"[。！？；!?]", text)
    if stop:
        text = text[: stop.end()]
    return _style_text(text, 100)


def _entries_paragraph(entries) -> str:
    """条目列表 → 段落文本。world.power/cost 的书内契约是 str 段落（非列表）——
    直接灌列表会被 normalize_world str() 成 repr 乱码（真机实证）。"""
    if not isinstance(entries, list):
        return str(entries or "").strip()
    parts: list[str] = []
    for i in entries:
        if isinstance(i, dict):
            name = str(i.get("name", "")).strip()
            rule = str(i.get("rule", i.get("note", ""))).strip()
            parts.append(f"{name}：{rule}" if name and rule else (name or rule))
        elif str(i or "").strip():
            parts.append(str(i).strip())
    return "\n".join(parts)


def _files(task: DeconstructJob) -> list[str]:
    return [obj.get("file", "") for obj in _raw(task).values() if isinstance(obj, dict)]


def _world_source_over(data: dict) -> bool:
    """拆书产物世界设定是否超字段契约（段落>300／条目 value>200／条数超限）——
    超了才值得花一次 AI 精炼；契约内直接机械灌入零调用。"""
    for k in ("stage", "power", "cost"):
        if len(_clean_para(data.get(k), 10**9)) > 300:
            return True
    specs = {"history": 8, "factions": 6, "constraints": 8, "extra": 8}
    for key, cap in specs.items():
        entries = [i for i in (data.get(key) or []) if isinstance(i, dict)]
        if len(entries) > cap:
            return True
        for i in entries:
            if len(_clean_para(i.get("value", i.get("rule", i.get("note", ""))), 10**9)) > 200:
                return True
    return False


async def _condense_world(task: DeconstructJob, source_body: dict, warnings: list[str]) -> dict | None:
    """AI 精炼：产物分析稿 → 书内字段形态（一次轻量调用）。失败降级返回 None
    （调用方退机械句界截断）。"""
    try:
        from deconstruct.service import resolve_client
        from prompts import load_layers

        client, model = await resolve_client(task.user_id, task.api_config_id, task.ai_model)
        sys_t, usr_t = load_layers("deconstruct_condense")
    except Exception as e:  # noqa: BLE001 — 模型/模板不可用：机械截断兜底
        warnings.append(f"AI 精炼不可用（{str(e)[:60]}），世界设定按句界截断适配字段")
        return None
    try:
        from deconstruct.pipeline import _parse_json_response
        from settings.world_model import PARAGRAPH_MAX, normalize_world

        raw = await client.chat(
            model=model, system=sys_t,
            messages=[{"role": "user",
                       "content": usr_t.format(source_json=json.dumps(source_body, ensure_ascii=False))}],
            max_tokens=3000, json_mode=True, operation="deconstruct_condense",
        )
        data = _parse_json_response(raw)
        # 完整句收口（模板铁律的代码兜底）：AI 半句停笔的字段截到最后一个句号
        for k in ("stage", "power", "cost"):
            if isinstance(data.get(k), str):
                data[k] = _clean_para(data[k], PARAGRAPH_MAX)
        for set_key in ("history", "constraints", "extra"):
            entries = data.get(set_key)
            if isinstance(entries, list):
                for e in entries:
                    if isinstance(e, dict) and isinstance(e.get("value"), str):
                        e["value"] = _clean_para(e["value"], 200)
        facs = data.get("factions")
        if isinstance(facs, list):
            for e in facs:
                if isinstance(e, dict) and isinstance(e.get("note"), str):
                    e["note"] = _clean_para(e["note"], 200)
        out = normalize_world(data)
        if not any(str(out.get(k, "")).strip() for k in ("stage", "power", "cost")) and not any(
            out.get(s) for s in ("history", "factions", "constraints", "extra")
        ):
            raise ValueError("精炼结果为空")
        return out
    except Exception as e:  # noqa: BLE001 — 精炼失败：机械截断兜底
        warnings.append(f"AI 精炼失败（{str(e)[:60]}），世界设定按句界截断适配字段")
        return None


def _world_body(data: dict, unclamped: bool = False) -> dict:
    """产物 world.data → 书内世界设定 body（对齐 v2 产物形状与 world 契约）。

    unclamped=True＝只剥证据章标不截字数（AI 精炼的输入源；精炼按契约
    重写形态，机械截断只作不可用时的兜底）。
    """
    para_limit, value_limit = (10**9, 10**9) if unclamped else (800, 200)
    no_power_txt = str(data.get("no_power", ""))
    return {
        # 评审 P1-2 口径：仅当模型输出含「无超凡/原文未明确」才置真，不凭空断言力量体系
        "no_power": "无超凡" in no_power_txt or "原文未明确" in no_power_txt,
        "stage": _clean_para(data.get("stage", ""), para_limit),
        # power/cost 契约＝段落 str：条目列表拼「名：规则」段落（v2 产物是列表）
        "power": _clean_para(_entries_paragraph(data.get("power")), para_limit),
        "cost": _clean_para(_entries_paragraph(data.get("cost")), para_limit),
        # 历史条目契约＝{key,value[,origin]}：产物是 {name,note[,evidence_ch]}
        "history": [
            {"key": str(i.get("name", ""))[:40],
             "value": str(i.get("note", ""))[:value_limit],
             "origin": str(i.get("evidence_ch", ""))[:40]}
            for i in (data.get("history") or []) if isinstance(i, dict)
        ],
        # 势力备注在产物的 rule 键（note 是旧形状假设，真机实证全丢成「原文未明确」）
        "factions": [
            {"name": _clean_para(i.get("name", ""), 20),
             "note": _clean_para(i.get("rule", i.get("note", "")), value_limit)}
            for i in (data.get("factions") or []) if isinstance(i, dict)
        ],
        "constraints": [
            {"key": _clean_para(i.get("name", ""), 20),
             "value": _clean_para(i.get("rule", i.get("note", "")), value_limit)}
            for i in (data.get("constraints") or []) if isinstance(i, dict)
        ],
        "extra": [
            {"key": _clean_para(i.get("name", ""), 20),
             "value": _clean_para(i.get("note", ""), value_limit)}
            for i in (data.get("extra") or []) if isinstance(i, dict)
        ],
    }


async def import_book(
    db: AsyncSession, task: DeconstructJob, user_id: str, items: list[str] | None = None
) -> tuple[dict, list[str]]:
    """建书：返回 ({book_id, name, skipped}, 降级提示清单)。幂等：book_id 已存在直接返回。

    items＝作家在弹窗勾选的灌入项（7 设定项＋章卷结构/人物关系/写作技法）；
    None＝旧口径（任务勾选维度里的设定项）——二创默认轻量，自书续写勾三项。
    """
    from novels.service import create_project

    if task.book_id:
        return {"book_id": task.book_id, "name": task.book_name, "skipped": []}, []

    if items is None:
        selected = _selected(task)
    else:
        picked = set(items)
        selected = [k for k in IMPORT_ITEM_KEYS if k in picked]

    warnings: list[str] = []
    synopsis = str(_data(task, "intro").get("intro", ""))[:600] if "intro" in selected else ""
    genre = str(_data(task, "genre").get("genre", ""))[:40] if "genre" in selected else ""

    project = await create_project(
        db,
        user_id,
        name=task.book_name,
        synopsis=synopsis,
        genre=genre,
        source="manual",
    )
    # 幂等键先落（评审 P1-7）：后续任一写入失败，重试不再重复建书
    task.book_id = project.id
    await db.commit()

    root = project.root_path
    from filesystem.storage import get_storage

    storage = get_storage()

    if "world" in selected:
        data = _data(task, "world")
        raw = await storage.read_yaml(root, KEY_TO_PATH["world"]) or {}
        from settings.world_model import normalize_world, put_world_merged

        body = _world_body(data)
        if _world_source_over(data):
            # 产物超字段契约：一次 AI 精炼按字段形态重写（失败退机械句界截断）
            condensed = await _condense_world(task, _world_body(data, unclamped=True), warnings)
            if condensed is not None:
                body = condensed
        fac_before = len(body["factions"])
        merged = put_world_merged(raw, normalize_world(body))
        if fac_before > 6:
            warnings.append(f"世界设定势力 {fac_before} 方超出上限 6，已截断保留前 6 方")
        await storage.write_yaml(root, KEY_TO_PATH["world"], merged)

    if "characters" in selected:
        from settings.character_service import Conflict, create_character

        for i, card in enumerate(_cards(task), start=1):
            name = str(card.get("name") or "").strip() or f"未命名{i}"
            role = _ROLE_MAP.get(str(card.get("role", "")), "配角")
            for attempt in range(1, 6):
                try:
                    await create_character(
                        db,
                        project.id,
                        name=name,
                        role=role,
                        persona=str(card.get("persona", ""))[:300] or None,
                        aliases=card.get("aliases") or None,
                        dossier={
                            k: str(card.get(k, ""))[:300]
                            for k in ("plot", "background", "faction", "look", "speech",
                                      "gender", "age", "race")
                            if str(card.get(k, "")).strip()
                        },
                    )
                    break
                except Conflict:
                    if attempt == 5:
                        warnings.append(f"角色「{name}」多次同名冲突，已跳过")
                        break
                    name = f"{name}（拆书{attempt}）"

    if "mainplot" in selected:
        data = _data(task, "mainplot")
        story = await storage.read_yaml(root, KEY_TO_PATH["story"]) or {}
        arc = story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {}
        # fullstory＝全书主线全景叙述（契约直读）；产物缺格回退弧条目串（旧产物兼容）
        fullstory = str(data.get("fullstory", "") or "").strip()
        if not fullstory:
            arcs = [
                f"{a.get('title', '')}：{a.get('summary', '')}"
                for a in (data.get("arcs") or []) if isinstance(a, dict)
            ]
            fullstory = "；".join(arcs)
        if not fullstory:
            # 旧产物（#906 前）ending 是字符串：arcs 也空时结局文案就是唯一主线线索，
            # 兜底链保住它（评审 P3：#907 曾把这一档收窄成恒「原文未明确」）。
            fullstory = str(data.get("ending", "") or "").strip()
        arc["fullstory"] = (fullstory or "原文未明确")[:2000]
        # 结局三格（场景/主角结局/收束基调）——设定页契约字段，此前从未回填。
        # 「原文未明确」置空（与角色格同口径：原文没写的不硬填）。
        ending = data.get("ending") if isinstance(data.get("ending"), dict) else {}

        def _ending_cell(v) -> str:
            t = str(v or "").strip()
            return "" if t == "原文未明确" else t[:150]

        arc["ending"] = {f: _ending_cell(ending.get(f, "")) for f in ("scene", "hero", "tone")}
        story["story_arc"] = arc
        await storage.write_yaml(root, KEY_TO_PATH["story"], story)

    if "style" in selected:
        from settings.style_model import put_style

        data = _data(task, "style")
        raw = await storage.read_yaml(root, KEY_TO_PATH["style"]) or {}

        def _entries(values) -> list[str]:
            """规则/手法条目 → 「名：怎么用」单行。

            模型偶尔把数组写成字符串/单对象（按单条处理——逐字符迭代会产出一串
            单字条目）；字典映射形态按「键：值」展开。
            """
            if isinstance(values, dict):
                if any(k in values for k in ("name", "how", "example", "description")):
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
                    name = _style_text(r.get("name", ""), 60)
                    how = _style_text(r.get("how", r.get("example", r.get("description", ""))), 500)
                    line = f"{name}：{how}" if name and how else (name or how)
                else:
                    line = _style_text(r, 500)
                if line and line not in out:
                    out.append(line)
            return out

        # 三区契约：role＝叙事身份一句话；rules/craft＝「名：怎么用」条目。
        # 旧形状降级双认：narration/dialogue/rhythm 描述段＋features 特征表——
        # features 是旧提示词包产物里唯一的技法账，只认描述段会把最有价值的条目整段丢掉。
        role = _style_role(data.get("role")) or _style_role(data.get("narration"))
        rules = _entries(data.get("rules"))
        if not rules:
            for label, key in (("对话", "dialogue"), ("节奏", "rhythm")):
                text = _style_text(data.get(key), 500)
                if text:
                    rules.append(f"{label}：{text}")
        craft = _entries(data.get("craft")) or _entries(data.get("features"))

        # 空格不写：put_style 收到空数组会覆盖新书种子里的默认硬约束/手法；
        # 旧产物缺格时保留现有设定，不把文风页清空。
        body: dict = {}
        if role:
            body["role"] = role
        if rules:
            body["rules"] = rules
        if craft:
            body["craft"] = craft
        if body:
            await storage.write_yaml(root, KEY_TO_PATH["style"], put_style(raw, body))
        else:
            warnings.append("写作文风产物为空，已保留新书原有文风设定")

    if "foreshadow" in selected:
        from settings.hooks_service import batch_create_hooks

        items = _hooks_items(task)
        result = await batch_create_hooks(db, project.id, items)
        if result.get("truncated"):
            warnings.append(f"伏笔超出单次上限，已收 {result['truncated']} 条")

    if "structure" in selected:
        # 章卷结构 → 卷行（title 产物常写「原文未明确」→ 落「第N卷」由服务端兜底）
        from volumes.service import create_volume

        data_v = _data(task, "structure")
        for v in data_v.get("volumes") or []:
            if not isinstance(v, dict):
                continue
            title = str(v.get("title", "")).strip()
            title = "" if title == "原文未明确" else title
            note = str(v.get("note", "")).strip()
            rng = str(v.get("ch_range", "")).strip()
            summary = "；".join(x for x in (rng, note) if x)[:300]
            try:
                await create_volume(db, project, title=title, summary=summary)
            except Exception as e:  # noqa: BLE001 — 套餐卷数上限等：降级提示不中断（详情在任务资料）
                warnings.append(f"卷「{title or '未命名'}」未导入（{str(e)[:60]}），章卷结构详见任务资料")
                break

    if "relations" in selected:
        # 人物关系 → 关系行：边端点名解析到已导入角色（名/别名/去括注变体），未入库/自环跳过留痕
        from sqlalchemy import select

        from models.character import Character, CharacterRelation

        chars = (await db.execute(select(Character).where(Character.novel_id == project.id))).scalars().all()
        by_name: dict = {}
        for c in chars:
            variants = _name_variants(c.name)
            try:
                for a in json.loads(c.aliases or "[]"):
                    variants.extend(_name_variants(str(a)))
            except ValueError:
                pass
            for v in variants:
                by_name.setdefault(v, c)

        def _resolve(edge_name: str):
            for v in _name_variants(edge_name):
                if v in by_name:
                    return by_name[v]
            return None

        skipped = 0
        data_r = _data(task, "relations")
        for e in data_r.get("edges") or []:
            if not isinstance(e, dict):
                continue
            owner = _resolve(str(e.get("from", "")))
            other = _resolve(str(e.get("to", "")))
            if not owner or not other or owner.id == other.id:
                skipped += 1
                continue
            dup = await db.execute(
                select(CharacterRelation).where(
                    CharacterRelation.novel_id == project.id,
                    CharacterRelation.owner_id == owner.id,
                    CharacterRelation.other_id == other.id,
                    CharacterRelation.rel_type == str(e.get("rel_type", ""))[:20],
                )
            )
            if dup.scalars().first() is not None:
                continue
            db.add(CharacterRelation(
                novel_id=project.id, owner_id=owner.id, other_id=other.id,
                rel_type=str(e.get("rel_type", ""))[:20], stance=_clean_para(e.get("stance", ""), 100),
                note=_clean_para(e.get("note", ""), 300), ch_ref=str(e.get("evidence_ch", ""))[:40],
            ))
        await db.commit()
        if skipped:
            warnings.append(f"{skipped} 条人物关系因角色未入库（未勾角色设定或名单外）被跳过")

    if "techniques" in selected:
        # 写作技法 → 文风 rules 追加（「名：怎么用」；已存在的不重复）
        from settings.style_model import put_style

        data_t = _data(task, "techniques")
        raw = await storage.read_yaml(root, KEY_TO_PATH["style"]) or {}
        cur = [str(x) for x in (raw.get("rules") or [])] if isinstance(raw, dict) else []
        for t in data_t.get("techniques") or []:
            if not isinstance(t, dict):
                continue
            name = str(t.get("name", "")).strip()
            how = str(t.get("how", "")).strip()
            line = f"{name}：{how}" if name and how else (name or how)
            if line and line not in cur:
                cur.append(line[:200])
        await storage.write_yaml(root, KEY_TO_PATH["style"], put_style(raw, {"rules": cur}))

    return (
        {
            "book_id": project.id,
            "name": project.name,
            "skipped": [d for d in SETTING_DIMENSION_KEYS if d not in selected],
        },
        warnings,
    )


def _cards(task: DeconstructJob) -> list[dict]:
    cards: list[dict] = []
    for c in _data(task, "characters").get("characters") or []:
        if not isinstance(c, dict):
            continue
        # 别名：新契约＝aliases 数组；旧产物＝alias 字符串（顿号/斜杠分隔）双认
        raw_aliases = c.get("aliases")
        if isinstance(raw_aliases, list):
            aliases = [str(a).strip() for a in raw_aliases if str(a or "").strip()]
        else:
            aliases = [a.strip() for a in re.split(r"[、/／]", str(c.get("alias", "") or "")) if a.strip()]
        look = str(c.get("look", "")).strip()
        plot_txt = _clean_para(c.get("plot", ""), 10**9).strip()

        def _cell(v) -> str:
            v = _clean_para(v, 300)
            return "" if v == "原文未明确" else v

        persona = _cell(c.get("persona", ""))
        if not persona:
            # persona＝写章必带的全卡摘要（角色页一句话人设，唯一 AI 可覆盖格）：
            # 产物缺格/模型没产出时（真机 13路 258 章实测 10/10 张全空），从背景或
            # 关键行动合成一句话速写兜底——开书契约：角色页人设不留空
            basis = str(c.get("background", "")).strip()
            if not basis or basis == "原文未明确":
                basis = plot_txt
            if basis and basis != "原文未明确":
                persona = _clean_para(basis, 60).strip()

        cards.append(
            {
                "name": str(c.get("name", ""))[:30],
                "role": _role_normalize(str(c.get("role", "配角"))),
                "persona": persona,
                "plot": _cell(f"{plot_txt}（{c.get('evidence_ch', '原文未明确')}）") if plot_txt else "",
                "background": _cell(c.get("background", "")),
                "aliases": aliases[:20],
                # 产物有的格子全带（材料没写的字段产物侧已是「原文未明确」，这里置空不编造）
                "faction": _cell(c.get("faction", "")),
                "look": _cell(look),
                "speech": _cell(c.get("speech", "")),
                "gender": _cell(c.get("gender", "")),
                "age": _cell(c.get("age", "")),
                "race": _cell(c.get("race", "")),
                "confidence": str(c.get("confidence", "")),
            }
        )
    return _dedupe_cards([c for c in cards if str(c.get("role", "")) != "路人"])


def _dedupe_cards(cards: list[dict]) -> list[dict]:
    """同名卡归并：L1 分批各拆各的，核心角色跨批重复（13路实测 135→去重后 ~80）——
    按主名归组、可信度排序，字段非空者优先合并；路人已在调用侧过滤。"""
    conf_rank = {"high": 0, "mid": 1, "low": 2}
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for c in cards:
        name = c["name"]
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append(c)
    out: list[dict] = []
    for name in order:
        group = sorted(groups[name], key=lambda c: conf_rank.get(c.get("confidence", ""), 1))
        base: dict = {k: v for k, v in group[0].items() if str(v or "").strip()}
        for other in group[1:]:
            for k, v in other.items():
                if k != "confidence" and not str(base.get(k, "")).strip() and str(v or "").strip():
                    base[k] = v
        out.append(base)
    return out


def _hooks_items(task: DeconstructJob) -> list[dict]:
    """产物 hooks → 台账条目（对齐 NovelHook 字段）：type 九值闭集、priority
    high/mid/low→3/2/1、有回收（payoff_ch/status=paid）→ status=resolved 且
    回收章并入描述；新书无章，章号只能并进文本。"""
    items: list[dict] = []
    for h in _data(task, "foreshadow").get("hooks") or []:
        if not isinstance(h, dict):
            continue
        desc = str(h.get("desc", ""))[:300]
        plant = h.get("plant_ch")
        if plant not in (None, "原文未明确"):
            desc = f"{desc}（埋设于第{plant}章）"
        payoff = h.get("payoff_ch")
        resolved = str(h.get("status", "")) == "paid" or payoff not in (None, "原文未明确")
        if resolved and payoff not in (None, "原文未明确"):
            desc = f"{desc}（收于第{payoff}章）"
        hook_type = str(h.get("type", "")).strip()
        priority = {"high": 1, "mid": 2, "low": 3}.get(str(h.get("priority", "")).strip(), 2)
        items.append({
            "description": desc[:300],
            "planned_volume_no": None,
            "type": hook_type,
            "priority": priority,
            "status": "resolved" if resolved else "active",
        })
    return items


def _name_variants(name: str) -> list[str]:
    """角色名匹配变体：全名＋去括注＋斜杠拆分——产物关系边的端点写法很野
    （「李耀（小李/我）」「小李/我」「队长」都见过），精确名之外全都要能认。"""
    n = name.strip()
    out = [n]
    stripped = re.sub(r"（[^）]*）|\([^)]*\)", "", n).strip()
    if stripped and stripped not in out:
        out.append(stripped)
    for part in re.split(r"[/／]", n):
        p = part.strip()
        if p and p not in out:
            out.append(p)
    return out


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_manifest(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def export_products(
    task: DeconstructJob, dest_dir: str, selected_files: list[str], graph: dict | None = None
) -> dict:
    """导出到本地文件夹：勾中 md＋图谱三件套（固定附带）＋README＋`导出清单.json`。

    评审纪律：**内存装配先行**——全部内容在内存成形后才落笔（渲染异常零写入）；
    清单（sha256 账）最后写：磁盘文件与清单不符（手改/外来）者，本导出先转 `.bak-时间戳` 再写。
    """
    from datetime import UTC, datetime

    from deconstruct.render import render_html, render_svg

    products = _md_map(task)
    dest_dir = os.path.expanduser(dest_dir or "")
    if not dest_dir or not os.path.isabs(dest_dir):
        raise OSError("invalid_path", f"导出目录非法：{dest_dir!r}")

    payload: dict[str, str] = {}
    written: list[str] = []
    for fn in selected_files:
        text = products.get(fn)
        if text is None:
            continue
        safe = fn.replace("/", "_").replace("\\", "_")
        payload[safe] = text
        written.append(safe)
    graph_files: list[str] = []
    if graph is not None:
        trio = {
            "图谱.json": json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
            "图谱.html": render_html(graph),
            "图谱.svg": render_svg(graph),
        }
        payload.update(trio)
        graph_files = list(trio)

    readme = ["# 拆书产物目录", "", f"书名：{task.book_name}", "", "## Markdown 产物（可勾选）"]
    readme += [f"- {fn}" for fn in sorted(products)]
    if graph is not None:
        readme += ["", "## 知识图谱（固定附带，不参与勾选）"]
        readme += ["- 图谱.json（唯一机器正身）", "- 图谱.html（双击浏览器打开，离线可用）", "- 图谱.svg（静态图）"]
        meta = graph.get("meta") if isinstance(graph.get("meta"), dict) else {}
        comp = meta.get("completion") if isinstance(meta.get("completion"), dict) else {}
        warns = meta.get("warnings") if isinstance(meta.get("warnings"), list) else []
        n_warn = sum(int(w.get("count") or 1) for w in warns if isinstance(w, dict))
        readme += [
            "",
            (
                f"图谱完成度：在场 {comp.get('presence_placed', 0)}/{comp.get('presence_total', 0)}"
                f" · 警告 {n_warn} 处（详见 图谱.html 顶栏横幅）"
            ),
        ]
    readme += [
        "",
        (
            "> 本目录内文件均为导出副本：手改不会回流应用；需要更新请回任务重新导出"
            "（被改过的旧文件将转 .bak-时间戳 备份保留）。"
        ),
    ]
    payload["README.md"] = "\n".join(readme) + "\n"

    os.makedirs(dest_dir, exist_ok=True)
    manifest_path = os.path.join(dest_dir, "导出清单.json")
    recorded = _load_manifest(manifest_path).get("files")
    recorded = recorded if isinstance(recorded, dict) else {}
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backups: list[str] = []
    for name, content in payload.items():
        target = os.path.join(dest_dir, name)
        if os.path.exists(target):
            disk_text: str | None
            try:
                with open(target, encoding="utf-8") as f:
                    disk_text = f.read()
            except OSError:
                disk_text = None
            if disk_text is None or recorded.get(name) != _sha256(disk_text):
                bak = f"{name}.bak-{stamp}"
                n2 = 1
                while os.path.exists(os.path.join(dest_dir, bak)):  # 同秒重导防撞（评审 P3）
                    n2 += 1
                    bak = f"{name}.bak-{stamp}-{n2}"
                os.replace(target, os.path.join(dest_dir, bak))
                backups.append(bak)
        with open(target, "w", encoding="utf-8") as f:
            f.write(content)
    manifest = {
        "task": task.id,
        "book": task.book_name,
        "contract": "deconstruct-graph/6" if graph is not None else "document-only",
        "exported_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "files": {name: _sha256(text) for name, text in payload.items()},
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return {
        "written": written,
        "graph": graph_files,
        "readme": "README.md",
        "dest": dest_dir,
        "backups": backups,
    }
