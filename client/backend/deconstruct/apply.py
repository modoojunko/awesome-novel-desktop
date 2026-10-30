"""拆书出口编排（c-deconstruct-book 3.x）——建书灌设定与本地导出。

产物 JSON/md 是**分析稿**（证据章号、confidence、原文未明确保留）；建书是
**操作稿**：所有文本经 `deconstruct.settings_map` 投影，证据/分析尾巴不进设定。

建书幂等键 = task.book_id（项目创建成功即先落 book_id，后续任一写入失败重试
不再重复建书，评审 P1-7）；单条写入失败不拖垮整本（角色/关系逐条降级留痕）：

- 简介/题材 → create_project 参数＋novel_genre.promise_note（tags 只留任务资料）；
- 世界设定 → world_model.normalize_world/put_world_merged（extra 契约 {key,value}；
  超上限逐项进降级清单）；
- 角色 → character_service.create_character（每书只保留首位主角，其余降配角留痕）；
- 主线 → story_arc.fullstory/ending 三格（证据章标剥除，旧 ending 字符串兜底）；
- 文风 → style_model.put_style 三区＋style_samples 示范段＋taboo 并入硬约束；
- 伏笔 → hooks_service.batch_create_hooks（新书无章：埋设/回收章并入描述，note 并入）；
- 章卷结构 → volumes.service.create_volume（「原文未明确」标题交服务端兜底）；
- 人物关系 → 按解析后的 (owner, other) 归并（同对多关系取并集，DB 唯一键即这一对）。

产物消费 **模型 JSON**（products_json[dim].data）——md 只是渲染展示，不做反解
（评审 P0-1：渲染键来自模型契约，反解会静默丢维度）。
"""

from __future__ import annotations

import json
import os
import re

from sqlalchemy.ext.asyncio import AsyncSession

from deconstruct import settings_map as sm
from deconstruct.cards import (
    ROLE_MAP as _ROLE_MAP,
)
from deconstruct.cards import (
    card_to_book_payload,
    cards_from_products,
)
from deconstruct.cards import (
    clean_para as _clean_para,
)
from deconstruct.cards import (
    role_normalize as _role_normalize,
)
from deconstruct.mdrender import md_map_from_products
from filesystem.paths import KEY_TO_PATH
from models.deconstruct import SETTING_DIMENSION_KEYS, DeconstructJob

# 兼容面（scripts/tests 直接从 apply 取这些符号；__all__ 同时挡住 ruff F401 清理）
__all__ = [
    "_ROLE_MAP",
    "_clean_para",
    "_role_normalize",
    "card_to_book_payload",
    "cards_from_products",
]

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
    """{filename: md}——由 data 现渲染（c-deconstruct-evidence-report），与预览同口径。"""
    covered = f"第1-{task.chapter_count}章" if task.chapter_count else "全本"
    return md_map_from_products(_raw(task), task.book_name, covered)


def _selected(task: DeconstructJob) -> list[str]:
    try:
        picked = json.loads(task.selected_dims_json or "[]")
    except ValueError:
        picked = []
    return [k for k in SETTING_DIMENSION_KEYS if k in picked]


_SENT_END = "。！？；!?\n"



def _files(task: DeconstructJob) -> list[str]:
    return [obj.get("file", "") for obj in _raw(task).values() if isinstance(obj, dict)]


def _world_source_over(data: dict) -> bool:
    """拆书产物世界设定是否超字段契约（段落>300／条目 value>200／条数超限）——
    超了才值得花一次 AI 精炼；契约内直接机械灌入零调用。"""
    from settings.world_model import (
        CONSTRAINTS_MAX,
        EXTRA_MAX,
        FACTIONS_MAX,
        HISTORY_MAX,
    )

    for k in ("stage", "power", "cost"):
        if len(_clean_para(data.get(k), 10**9)) > 300:
            return True
    specs = {
        "history": HISTORY_MAX,
        "factions": FACTIONS_MAX,
        "constraints": CONSTRAINTS_MAX,
        "extra": EXTRA_MAX,
    }
    for key, cap in specs.items():
        entries = [i for i in (data.get(key) or []) if isinstance(i, dict)]
        if len(entries) > cap:
            return True
        for i in entries:
            if len(_clean_para(i.get("value", i.get("rule", i.get("note", ""))), 10**9)) > 200:
                return True
    return False


class ImportCancelled(RuntimeError):
    """建书被取消（阶段边界检查命中，或在途调用被取消信号掐断）。

    调用方（deconstruct.imports）据此清理半成品并退出，**不写失败终态**——取消方已经把
    status 写回 completed，谁再写终态谁就把用户的操作吞了。
    """


async def _race_stop(coro, stop_event):
    """在途调用与取消信号竞速（照拆书管线 _Stopper 口径）：取消即放弃在途请求。

    两条取消来源都必须掐断在途请求：

    - `stop_event` 置位；
    - **外层任务被 `task.cancel()`** ——取消端点是「先置位、紧接着 cancel 执行体」，
      `ev.set()` 只把唤醒排进 call_soon，`task.cancel()` 会先取消这里的 `asyncio.wait`，
      所以这条才是常见路径。原先只处理了 stop_event 分支，外层取消时 `chat` 成了孤儿，
      那次 23 秒的调用会继续跑完并计费（评审实证）。
    """
    if stop_event is None:
        return await coro
    import asyncio
    import contextlib

    chat = asyncio.ensure_future(coro)
    stop = asyncio.ensure_future(stop_event.wait())
    try:
        done, _pending = await asyncio.wait({chat, stop}, return_when=asyncio.FIRST_COMPLETED)
    except asyncio.CancelledError:
        chat.cancel()  # 在途请求一起放弃：不留孤儿 future 继续烧 token
        stop.cancel()
        raise
    stop.cancel()
    if chat in done:
        return chat.result()
    chat.cancel()
    with contextlib.suppress(BaseException):
        await chat
    raise ImportCancelled("建书已取消")


async def _condense_world(
    task: DeconstructJob, source_body: dict, warnings: list[str], *, stop_event=None
) -> dict | None:
    """AI 精炼：产物分析稿 → 书内字段形态（一次轻量调用）。失败降级返回 None
    （调用方退机械句界截断）；`stop_event` 置位＝取消，放弃在途调用并抛 ImportCancelled。"""
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

        raw = await _race_stop(
            client.chat(
                model=model, system=sys_t,
                messages=[{"role": "user",
                           "content": usr_t.format(source_json=json.dumps(source_body, ensure_ascii=False))}],
                max_tokens=3000, json_mode=True, operation="deconstruct_condense",
            ),
            stop_event,
        )
        data = _parse_json_response(raw)
        # 完整句收口（模板铁律的代码兜底）：AI 半句停笔的字段截到最后一个句号
        for k in ("stage", "power", "cost"):
            if isinstance(data.get(k), str):
                data[k] = sm.clean_settings_text(data[k], PARAGRAPH_MAX)
        for set_key in ("history", "constraints", "extra"):
            entries = data.get(set_key)
            if isinstance(entries, list):
                for e in entries:
                    if isinstance(e, dict) and isinstance(e.get("value"), str):
                        e["value"] = sm.clean_settings_text(e["value"], 200)
        facs = data.get("factions")
        if isinstance(facs, list):
            for e in facs:
                if isinstance(e, dict) and isinstance(e.get("note"), str):
                    e["note"] = sm.clean_settings_text(e["note"], 200)
        out = normalize_world(data)
        if not any(str(out.get(k, "")).strip() for k in ("stage", "power", "cost")) and not any(
            out.get(s) for s in ("history", "factions", "constraints", "extra")
        ):
            raise ValueError("精炼结果为空")
        return out
    except ImportCancelled:
        raise  # 取消不是「精炼失败」：不得被降级吞掉（评审：取消要真中断）
    except Exception as e:  # noqa: BLE001 — 精炼失败：机械截断兜底
        warnings.append(f"AI 精炼失败（{str(e)[:60]}），世界设定按句界截断适配字段")
        return None


async def import_book(
    db: AsyncSession,
    task: DeconstructJob,
    user_id: str,
    items: list[str] | None = None,
    *,
    book_id: str | None = None,
    on_step=None,
    is_cancelled=None,
    stop_event=None,
) -> tuple[dict, list[str]]:
    """建书：返回 ({book_id, name, skipped}, 降级提示清单)。

    c-deconstruct-import-async 起改为**后台整段执行**（deconstruct.imports.run_import 调用），
    三条纪律与旧同步实现不同：

    1. 幂等判定不在本函数：受理/重试的分支由 router + imports.claim 负责，这里一律按
       本次勾选完整建一遍；
    2. 慢调用前置：世界设定超字段契约时的 AI 精炼发生在**建书行创建之前**，写入阶段
       只有毫秒级，失败即由调用方软删半成品（不留可见的半本书）；
    3. 幂等键（task.book_id）由调用方在全部写入成功后落——本函数不写。

    items＝作家在弹窗勾选的灌入项（7 设定项＋章卷结构/人物关系/写作技法），由受理时
    持久化到任务 `import.items`（重试沿用同一份）；None 仅用于兼容旧口径。
    book_id＝受理时预分配的书 id（崩溃后可清理由此指向的半成品）。
    on_step＝进度回调（refine/writing）；is_cancelled＝阶段边界取消检查；
    stop_event＝取消信号（asyncio.Event，用于掐断在途模型调用）。
    """
    from models.project import Novel
    from novels.service import create_project

    if items is None:
        selected = _selected(task)
    else:
        picked = set(items)
        selected = [k for k in IMPORT_ITEM_KEYS if k in picked]

    warnings: list[str] = []
    # 简介/题材走同一投影：证据章号、分析尾巴不进设定；题材五字段一次落齐
    meta = sm.intro_genre_body(
        _data(task, "intro") if "intro" in selected else {},
        _data(task, "genre") if "genre" in selected else {},
        _data(task, "mainplot"),
        _data(task, "world"),
    )
    synopsis = meta["synopsis"]
    genre = meta["genre"]

    # ① 慢调用前置：精炼只依赖产物，不依赖书行——放在建书之前，写入阶段才毫秒级
    condensed_world = None
    if "world" in selected and _world_source_over(_data(task, "world")):
        if on_step is not None:
            await on_step("refine")
        if is_cancelled is not None and await is_cancelled():
            raise ImportCancelled("建书已取消")
        condensed_world = await _condense_world(
            task, sm.world_body(_data(task, "world"), unclamped=True), warnings,
            stop_event=stop_event,
        )
    if on_step is not None:
        await on_step("writing")
    if is_cancelled is not None and await is_cancelled():
        raise ImportCancelled("建书已取消")

    # ② 写入阶段：建书行 + 全部设定写入（<0.2s）
    project = await create_project(
        db,
        user_id,
        name=task.book_name,
        synopsis=synopsis,
        genre=genre,
        source="manual",
        book_id=book_id,
    )
    book_id = project.id

    if "genre" in selected:
        try:
            from genres.novel_genre_service import put_novel_genre

            forbidden_payload = []
            for label in meta["forbidden"]:
                vid = sm.genre_vocab_id(label, "forbidden")
                forbidden_payload.append({"tagId": vid} if vid else {"text": label})
            battlefield_payload = [
                sm.genre_vocab_id(label, "battlefield") or label
                for label in meta["battlefield"]
            ]
            await put_novel_genre(db, book_id, {
                "core_promise": meta["core_promise"],
                "promise_note": meta["promise_note"],
                "forbidden_list": forbidden_payload,
                "cost_ratio": meta["cost_ratio"],
                "battlefield": battlefield_payload,
            })
            if meta.get("inferred"):
                warnings.append(
                    "题材 "
                    + "、".join(meta["inferred"])
                    + " 拆书产物未覆盖，已按题材/主线/世界代价给起点（请在设定页确认）"
                )
        except Exception as e:  # noqa: BLE001 — 题材补充字段失败不拖垮建书
            warnings.append(f"题材字段未写入（{str(e)[:60]}），题材目录已写")

    root = project.root_path
    from filesystem.storage import get_storage

    storage = get_storage()

    if "world" in selected:
        data = _data(task, "world")
        raw = await storage.read_yaml(root, KEY_TO_PATH["world"]) or {}
        from settings.world_model import (
            CONSTRAINTS_MAX,
            EXTRA_MAX,
            FACTIONS_MAX,
            HISTORY_MAX,
            normalize_world,
            put_world_merged,
        )

        body = sm.world_body(data)
        # 超契约：精炼已在写入阶段之前完成（慢调用前置，c-deconstruct-import-async）；
        # 结果为空＝精炼失败/不可用，退回机械句界截断
        if _world_source_over(data) and condensed_world is not None:
            body = condensed_world
        # 机械兜底会按 world 契约截断条目；把截断说清楚，不静默丢
        for key, cap, label in (
            ("history", HISTORY_MAX, "大事记"),
            ("factions", FACTIONS_MAX, "势力"),
            ("constraints", CONSTRAINTS_MAX, "禁忌铁律"),
            ("extra", EXTRA_MAX, "其他设定"),
        ):
            n = len([x for x in (body.get(key) or []) if isinstance(x, dict)])
            if n > cap:
                warnings.append(f"世界设定{label} {n} 条超出上限 {cap}，已截断保留前 {cap} 条")
        merged = put_world_merged(raw, normalize_world(body))
        await storage.write_yaml(root, KEY_TO_PATH["world"], merged)

    if "characters" in selected:
        from sqlalchemy.exc import IntegrityError

        from settings.character_service import Conflict, create_character

        # 每书至多一位主角（DB 部分唯一索引）：第一个保留，其余降配角并留痕。
        cards = _cards(task)
        protagonist_seen = False
        downgraded = 0
        for i, card in enumerate(cards, start=1):
            payload = card_to_book_payload(card, i)
            name = payload["name"]
            role = payload["role"]
            if role == "主角":
                if protagonist_seen:
                    role = "配角"
                    downgraded += 1
                else:
                    protagonist_seen = True
            for attempt in range(1, 6):
                try:
                    await create_character(
                        db,
                        book_id,
                        name=name,
                        role=role,
                        persona=payload["persona"],
                        aliases=payload["aliases"],
                        dossier=payload["dossier"],
                    )
                    break
                except Conflict:
                    if attempt == 5:
                        warnings.append(f"角色「{name}」多次同名冲突，已跳过")
                        break
                    name = f"{name}（拆书{attempt}）"
                except IntegrityError as e:
                    # 单卡约束冲突不拖垮整本书：回滚本笔，后续维度继续
                    await db.rollback()
                    project = await db.get(Novel, book_id) or project
                    warnings.append(f"角色「{name}」未导入（数据库约束冲突：{str(e)[:60]}）")
                    break
        if downgraded:
            warnings.append(
                f"拆书产物有 {downgraded + 1} 个主角，按每书一位保留首位，其余 {downgraded} 位降为配角"
            )

    if "mainplot" in selected:
        data = _data(task, "mainplot")
        story = await storage.read_yaml(root, KEY_TO_PATH["story"]) or {}
        arc = story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {}
        mapped = sm.mainplot_body(data)
        arc["fullstory"] = mapped["fullstory"]
        arc["ending"] = mapped["ending"]
        story["story_arc"] = arc
        await storage.write_yaml(root, KEY_TO_PATH["story"], story)

    if "style" in selected:
        from settings.style_model import put_style

        data = _data(task, "style")
        raw = await storage.read_yaml(root, KEY_TO_PATH["style"]) or {}
        # 三区＋例句＋taboo 全部走同一投影：旧形状 narration/dialogue/rhythm/features
        # 降级双认；证据/confidence 不进设定。
        body = sm.style_body(data)
        if body:
            await storage.write_yaml(root, KEY_TO_PATH["style"], put_style(raw, body))
        else:
            warnings.append("写作文风产物为空，已保留新书原有文风设定")

    if "foreshadow" in selected:
        from settings.hooks_service import batch_create_hooks

        items = sm.hook_items(_data(task, "foreshadow"))
        result = await batch_create_hooks(db, book_id, items)
        if result.get("truncated"):
            warnings.append(
                f"伏笔产物超过单次上限，仅取前 {result['truncated']} 条（重复/空条目另计）"
            )

    if "structure" in selected:
        # 章卷结构 → 卷行（title 产物常写「原文未明确」→ 落「第N卷」由服务端兜底）
        from volumes.service import create_volume

        data_v = _data(task, "structure")
        for v in data_v.get("volumes") or []:
            if not isinstance(v, dict):
                continue
            mapped = sm.structure_volume(v)
            title, summary = mapped["title"], mapped["summary"]
            try:
                await create_volume(db, project, title=title, summary=summary)
            except Exception as e:  # noqa: BLE001 — 套餐卷数上限等：降级提示不中断（详情在任务资料）
                warnings.append(f"卷「{title or '未命名'}」未导入（{str(e)[:60]}），章卷结构详见任务资料")
                break

    if "relations" in selected:
        # 人物关系 → 关系行：先按解析后的 (owner, other) 归并——DB 唯一键是这一对，
        # 不是 (owner, other, rel_type)；同对多关系合并，绝不因第二种 rel_type 撞库中断。
        from sqlalchemy import select
        from sqlalchemy.exc import IntegrityError

        from models.character import Character, CharacterRelation

        chars = (await db.execute(select(Character).where(Character.novel_id == book_id))).scalars().all()
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

        def _join_unique(values: list[str], sep: str, limit: int) -> str:
            seen: list[str] = []
            for v in values:
                v = sm.clean_settings_text(v, limit)
                if v and v not in seen:
                    seen.append(v)
            return sep.join(seen)[:limit]

        def _join_refs(values: list[str]) -> str:
            """ch_ref 是关系行的证据字段（设定模型明确保留），只去重不洗章号。"""
            seen: list[str] = []
            for v in values:
                v = str(v or "").strip()
                if v and v != "原文未明确" and v not in seen:
                    seen.append(v)
            return "、".join(seen)[:40]

        buckets: dict[tuple[str, str], dict] = {}
        skipped = 0
        merged = 0
        for e in _data(task, "relations").get("edges") or []:
            if not isinstance(e, dict):
                continue
            owner = _resolve(str(e.get("from", "")))
            other = _resolve(str(e.get("to", "")))
            if not owner or not other or owner.id == other.id:
                skipped += 1
                continue
            key = (owner.id, other.id)
            row = buckets.get(key)
            if row is None:
                buckets[key] = {
                    "types": [str(e.get("rel_type", ""))],
                    "stances": [str(e.get("stance", ""))],
                    "notes": [str(e.get("note", ""))],
                    "refs": [str(e.get("evidence_ch", ""))],
                }
            else:
                merged += 1
                row["types"].append(str(e.get("rel_type", "")))
                row["stances"].append(str(e.get("stance", "")))
                row["notes"].append(str(e.get("note", "")))
                row["refs"].append(str(e.get("evidence_ch", "")))

        for (owner_id, other_id), row in buckets.items():
            dup = await db.execute(
                select(CharacterRelation).where(
                    CharacterRelation.novel_id == book_id,
                    CharacterRelation.owner_id == owner_id,
                    CharacterRelation.other_id == other_id,
                )
            )
            if dup.scalars().first() is not None:
                continue
            rel_type, merged_note = sm.merge_relation_labels(
                row["types"], _join_unique(row["notes"], "；", 300)
            )
            try:
                async with db.begin_nested():
                    db.add(CharacterRelation(
                        novel_id=book_id, owner_id=owner_id, other_id=other_id,
                        rel_type=rel_type,
                        stance=_join_unique(row["stances"], "；", 100),
                        note=merged_note,
                        ch_ref=_join_refs(row["refs"]),
                    ))
                    await db.flush()
            except IntegrityError as e:
                warnings.append(f"1 条人物关系未导入（数据库约束冲突：{str(e)[:60]}）")
        await db.commit()
        if skipped:
            warnings.append(f"{skipped} 条人物关系因角色未入库（未勾角色设定或名单外）被跳过")
        if merged:
            warnings.append(f"{merged + len(buckets)} 条关系边按角色对合并为 {len(buckets)} 条（同对多关系取并集）")

    if "techniques" in selected:
        # 写作技法 → 文风 rules/craft：新契约的 how 在 repro_steps/emotion_chain 里，
        # borrowable→craft、avoid→硬约束（避免…）；reader_needs 只留任务资料。
        from settings.style_model import put_style, read_style

        data_t = _data(task, "techniques")
        raw = await storage.read_yaml(root, KEY_TO_PATH["style"]) or {}
        cur = read_style(raw)
        add_rules, add_craft = sm.technique_lines(data_t)
        new_rules = [x for x in add_rules if x not in (cur.get("rules") or [])]
        new_craft = [x for x in add_craft if x not in (cur.get("craft") or [])]
        body: dict = {}
        if new_rules:
            body["rules"] = [*(cur.get("rules") or []), *new_rules]
        if new_craft:
            body["craft"] = [*(cur.get("craft") or []), *new_craft]
        if body:
            await storage.write_yaml(root, KEY_TO_PATH["style"], put_style(raw, body))

    return (
        {
            "book_id": project.id,
            "name": project.name,
            "skipped": [d for d in SETTING_DIMENSION_KEYS if d not in selected],
        },
        warnings,
    )


def _cards(task: DeconstructJob) -> list[dict]:
    """兼容薄封装：投影本体在 deconstruct.cards（建书与库收录共用单源）。"""
    return cards_from_products(_data(task, "characters"))


def _dedupe_cards(cards: list[dict]) -> list[dict]:
    """兼容薄封装（scripts/tests 沿用旧符号）。"""
    from deconstruct.cards import dedupe_cards

    return dedupe_cards(cards)


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
