"""知识整理管线（c-kb-summarize）：素材 → 代码识别层次 → 知识树直接生效。

层次由**代码确定性识别**（boss 拍板：不由 LLM 识别层次）——两级分桶：
  L1 类别（kb_entries.concept）
  L2 槽位（payload 分组键值：角色=role[主角/配角/反派]、文风文笔=slot[叙事身份/规则/
      写法/忌用…]、世界设定=part[舞台/力量规则/代价/历史]；手法单桶「写法」）
每个槽位桶＝一个知识点（origin='summary'，schema_json＝桶内 payload 键并集），
桶内素材全部转该知识实例（fields＝素材属性格与 schema 对齐的键值）后归档。
知识点定义首版为模板文案；LLM 打磨（更贴切命名/定义）挂账增强。

运行独立落 kb_summarize_runs，同题材单飞（partial unique index 兜底）。
触发：素材积压 ≥阈值启动期自动 / 整理面板手动 / 定期（>7 天且有素材随启动钩）。
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kb.migrate_library import strip_anchors_deep
from models.kb import KbEntry, KbKnowledgeInstance

AUTO_MATERIAL_THRESHOLD = 5  # 素材积压自动触发阈值（题内）

_log = logging.getLogger("uvicorn.error")

async def ensure_kb_summarize(db: AsyncSession) -> dict[str, int]:
    """幂等 DDL：总结 runs 表＋kb_entries.parent_id 列（知识树，c-kb-summarize 批E）。"""
    added = 0
    cols = [r[1] for r in (await db.execute(_t("PRAGMA table_info(kb_entries)"))).fetchall()]
    if "parent_id" not in cols:
        await db.execute(_t(
            "ALTER TABLE kb_entries ADD COLUMN parent_id TEXT NOT NULL DEFAULT ''"
        ))
        added += 1
    # 知识字段元数据（c-kb-summarize schema 层）：知识点带字段定义，实例按 schema 存字段值
    if "schema_json" not in cols:
        await db.execute(_t(
            "ALTER TABLE kb_entries ADD COLUMN schema_json TEXT NOT NULL DEFAULT '[]'"
        ))
        added += 1
    inst_cols = [r[1] for r in (await db.execute(_t("PRAGMA table_info(kb_knowledge_instances)"))).fetchall()]
    if inst_cols and "fields_json" not in inst_cols:
        await db.execute(_t(
            "ALTER TABLE kb_knowledge_instances ADD COLUMN fields_json TEXT NOT NULL DEFAULT '{}'"
        ))
        added += 1
    await db.execute(_t("""CREATE TABLE IF NOT EXISTS kb_summarize_runs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        genre TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'running',
        trigger TEXT NOT NULL DEFAULT '',
        materials_scanned INTEGER NOT NULL DEFAULT 0,
        knowledge_created INTEGER NOT NULL DEFAULT 0,
        error TEXT NOT NULL DEFAULT '',
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )"""))
    # 单飞竞态兜底（评审 P2）：同题材同时只允许一行 running——
    # 建索引前只把超时孤儿清成 error（30 分钟前；活跃 running 不动）
    await db.execute(_t(
        "UPDATE kb_summarize_runs SET status='error', error='stale running reclaimed' "
        "WHERE status='running' AND created_at < datetime('now', '-30 minutes')"
    ))
    await db.execute(_t(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_summarize_runs_singleflight "
        "ON kb_summarize_runs (user_id, genre) WHERE status='running'"
    ))
    await db.commit()
    return {"ddl": added}


def _t(sql: str):
    from sqlalchemy import text

    return text(sql)


# ── 发版树字段模板落格（boss 2026-11-08：知识对象定义实例的格，实例按格填值）──
# 模板住 taxonomy.json 节点 fields（type/enum/from/join/transform）；这里只做
# 取值与转换：from 首取非空 → 逐值剥章锚 → 转换/拼接 → 不重复正文才落格。
def _conf_label(v) -> str:
    return {"high": "高", "mid": "中", "low": "低"}.get(str(v).strip().lower(), "")


def _sev_label(v) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(str(v).strip().lower(), "")


def _hard_label(v) -> str:
    s = "true" if v is True else ("false" if v is False else str(v).strip().lower())
    if s in ("true", "1"):
        return "铁律级"
    if s in ("false", "0", ""):
        return "普通"
    return ""


_TRANSFORMS = {"conf_label": _conf_label, "hard_label": _hard_label, "sev_label": _sev_label}


async def materialize_node_row(
    db: AsyncSession, *, user_id: str, genre: str,
    concept: str, title: str, definition: str, parent_id: str, schema_json: str = "[]",
) -> str:
    """懒物化一个知识点行：复用同题材×类别×标题行，缺则建（带发版定义/模板/父级）。

    总结桶归属与提炼任务（kb/refine）共用——树上的节点行只有这一个入口。
    """
    row = (await db.scalars(
        select(KbEntry).where(
            KbEntry.user_id == user_id,
            KbEntry.genre == genre,
            KbEntry.concept == concept,
            KbEntry.origin == "summary",
            KbEntry.title == title,
        ).limit(1)
    )).first()
    if row is None:
        row = KbEntry(
            id=uuid.uuid4().hex,
            user_id=user_id,
            genre=genre,
            concept=concept,
            concept_id=f"{genre}:{concept}",
            title=title,
            payload_json="{}",
            instruction="",
            definition=f"{genre}·{title}——{definition}",
            schema_json=schema_json,
            origin="summary",
            status="active",
            version=1,
            parent_id=parent_id,
        )
        db.add(row)
    else:
        row.definition = f"{genre}·{title}——{definition}"
        row.parent_id = parent_id
        row.schema_json = schema_json
    return row.id


async def materialize_tree_chain(db: AsyncSession, *, user_id: str, genre: str, node_key: str) -> str:
    """沿发版树父链物化到 node_key 自身，返回该节点行 id（提炼任务挂树用）。"""
    from kb.taxonomy import nodes as taxonomy_nodes
    from kb.taxonomy import parent_chain

    parent_id = ""
    for ck in parent_chain(node_key):  # 顶层在前
        pn = taxonomy_nodes()[ck]
        parent_id = await materialize_node_row(
            db, user_id=user_id, genre=genre, concept=pn["concept"],
            title=pn["title"], definition=pn["definition"], parent_id=parent_id,
        )
    n = taxonomy_nodes()[node_key]
    return await materialize_node_row(
        db, user_id=user_id, genre=genre, concept=n["concept"],
        title=n["title"], definition=n["definition"], parent_id=parent_id,
        schema_json=json.dumps(
            [{"name": f["name"], "desc": f.get("desc", "")} for f in (n.get("fields") or [])],
            ensure_ascii=False,
        ),
    )


def _fields_by_template(template: list[dict], payload: dict, inst_text: str) -> dict[str, str]:
    """按知识点模板落格：{格名: 值}；格值取不到不落（空格不渲染）。"""
    fields: dict[str, str] = {}
    for slot in template:
        raw_parts: list[str] = []
        for src in slot.get("from") or []:
            v = payload.get(src)
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            if isinstance(v, list):
                parts = [strip_anchors_deep(x) for x in v]
                raw_parts.append(slot.get("join", "；").join(str(p).strip() for p in parts if str(p).strip()))
            elif v is True or v is False:
                raw_parts.append("true" if v else "false")
            else:
                raw_parts.append(str(strip_anchors_deep(str(v))).strip())
        if not raw_parts:
            continue
        tr = _TRANSFORMS.get(slot.get("transform") or "")
        vals = [v for v in ((tr(p) if tr else p) for p in raw_parts) if v]
        if not vals:
            continue
        fv = slot.get("join", "；").join(vals)[:200]
        if fv and fv not in inst_text:
            fields[slot["name"]] = fv
    return fields


# ─── 素材统计 ────────────────────────────────────────────────────────────


async def material_stats(db: AsyncSession, *, user_id: str) -> dict[str, int]:
    """各题材素材积压数（origin=material 且 active）。"""
    rows = (
        await db.execute(
            select(KbEntry.genre, func.count(KbEntry.id))
            .where(
                KbEntry.user_id == user_id,
                KbEntry.status == "active",
                KbEntry.origin == "material",
                KbEntry.concept != "情节",  # 情节消费链未建，素材恒积压不触发
            )
            .group_by(KbEntry.genre)
        )
    ).all()
    return {g or "_general": int(n) for g, n in rows}


# ─── 核心跑一次总结 ──────────────────────────────────────────────────────


async def run_summarize(
    db: AsyncSession,
    *,
    user_id: str,
    genre: str,
    trigger: str,
) -> tuple[dict | None, str]:
    """总结一个题材：**代码识别层次**（类别 → 槽位 → 知识点），LLM 不参与分层。

    层次树由确定性分桶构建：
      L1 类别（kb_entries.concept）
      L2 槽位（payload 的 role/slot/part 键值——「主角」「配角」「叙事身份」「规则」…）
    每个槽位桶＝一个知识点（origin=summary），桶内素材全部转该知识的实例（fields
    取素材 payload 属性格与 schema 字段名对齐后的键值），素材行归档。
    返回 (摘要 dict, error)；单飞命中返回 (None, "running")。
    """
    await ensure_kb_summarize(db)

    # 单飞：同题材 30 分钟内的 running 即跳过；超时孤儿（进程中途死掉）置 error 回收
    stale = (
        await db.execute(_t(
            "SELECT id FROM kb_summarize_runs WHERE user_id=:u AND genre=:g "
            "AND status='running' AND created_at < datetime('now', '-30 minutes')"
        ), {"u": user_id, "g": genre})
    ).all()
    for (rid,) in stale:
        await db.execute(_t(
            "UPDATE kb_summarize_runs SET status='error', error='stale running reclaimed' WHERE id=:i"
        ), {"i": rid})
    live = (
        await db.execute(_t(
            "SELECT id FROM kb_summarize_runs WHERE user_id=:u AND genre=:g "
            "AND status='running' AND created_at >= datetime('now', '-30 minutes')"
        ), {"u": user_id, "g": genre})
    ).first()
    if live is not None:
        await db.commit()
        return None, "running"
    await db.commit()

    materials = (
        await db.execute(
            select(KbEntry).where(
                KbEntry.user_id == user_id,
                KbEntry.status == "active",
                KbEntry.origin == "material",
                KbEntry.genre == genre,
                KbEntry.concept != "情节",
            ).order_by(KbEntry.id)
        )
    ).scalars().all()
    if not materials:
        return {"collected": 0, "knowledge": 0}, ""

    run_id = uuid.uuid4().hex
    try:
        await db.execute(_t(
            "INSERT INTO kb_summarize_runs (id, user_id, genre, status, trigger, materials_scanned) "
            "VALUES (:i, :u, :g, 'running', :t, :n)"
        ), {"i": run_id, "u": user_id, "g": genre, "t": trigger, "n": len(materials)})
        await db.commit()
    except Exception as exc:  # noqa: BLE001 — 部分唯一索引兜底：并发双击/重放在此收敛为 running
        if "ux_kb_summarize_runs_singleflight" not in str(exc):
            _log.warning("kb summarize run claim failed: %s", exc)
        await db.rollback()
        return None, "running"

    created = 0
    try:
        # ── 代码识别层次：concept → 槽位键值 两级分桶 ──
        # 槽位键表（类别 → payload 分组键；None＝单桶）：
        #   角色设定 payload.role（主角/配角/反派）
        #   文风/文笔 payload.slot（叙事身份/规则/写法/忌用…）
        #   世界设定 payload.part（舞台/力量规则…）
        #   手法：无槽位，单桶
        SLOT_KEY = {"角色设定": "role", "文风": "slot", "文笔": "slot", "世界设定": "part",
                    "手法": "kind"}

        def _payload_of(m):
            try:
                p = json.loads(m.payload_json or "{}")
                return p if isinstance(p, dict) else {}
            except ValueError:
                return {}

        def _slot_label(concept, slot_value):
            """槽位值 → 知识点名（作家语言）。"""
            named = {"主角": "主角", "配角": "配角", "反派": "反派"}
            if concept == "角色设定" and slot_value in named:
                return named[slot_value]
            slot_cn = {
                # 文风 slot（payloads.StylePayload）
                "role": "叙事身份", "tone": "语调", "pov": "叙事视角",
                "register": "语域", "sample": "示范",
                # 文笔 slot（CraftPayload）
                "rule": "规则", "craft": "写法", "banned_word": "忌用词", "tic": "口癖",
                # 世界 part（WorldPayload）
                "stage": "舞台", "power": "力量与规则", "cost": "代价",
                "factions": "势力", "history": "历史沿革", "extra": "补充设定",
                "constraint": "约束",
            }
            plain = {
                ("手法", "写法"): "场面打法",
                ("文笔", "写法"): "笔法招式",
                ("文笔", "规则"): "句法规矩与忌用",
                ("文风", "规则"): "声音招式",
                ("世界设定", "补充设定"): "更多世界细节",
                ("世界设定", "力量与规则"): "力量体系与规矩",
            }
            if (concept, slot_value) in plain:
                return plain[(concept, slot_value)]
            return slot_cn.get(slot_value, slot_value or "写法")

        def _slot_desc(concept: str, slot_value: str) -> str:
            """知识点定义（作家语言一句话）——模板句无信息量（真机 2026-11-08「定义空」实锤）。"""
            if slot_value == "写法":
                if concept == "手法":
                    return "场面打法与读者体验设计——一条打法一条实例"
                if concept == "文笔":
                    return "句法层面的具体笔法——一条笔法一条实例"
            if slot_value == "场面打法":
                return "写每一章时的场面打法与读者体验设计——一条打法一条实例"
            if slot_value == "规则":
                if concept == "文风":
                    return "这本书的声音招式——一条场景规则一条实例（战斗短句、悲喜交替这类）"
                if concept == "文笔":
                    return "句子层面的写法规矩与忌用"
            if slot_value == "核心":
                return "故事核心位置的角色"
            return SLOT_DESC.get(slot_value, "同类写法实例的集合")

        # 知识点定义＝这个知识点是什么（作家语言一句话）——模板句「XX维度的写法案例集」
        # 无信息量（真机 2026-11-08 实锤「定义空」）；按槽位给真定义，未收录回落通用句
        SLOT_DESC = {
            # 角色
            "主角": "书里担主角位置的角色实例——一人一条，含人设/背景/剧情线",
            "配角": "书里担配角位置的角色实例",
            "反派": "书里担反派位置的角色实例",
            # 世界 part
            "舞台": "故事发生在哪、地理与时代底盘的设定实例",
            "力量与规则": "这个世界的能力体系与运行规矩——一条规矩一条实例",
            "代价": "使用力量要付出什么——一条代价一条实例",
            "历史沿革": "世界过去发生过的大事——一条事件一条实例",
            "势力": "世界里的组织与阵营——一势力一条实例",
            "约束": "这个世界铁律级的硬约束——一条一条实例",
            "补充设定": "舞台/力量/势力之外的零散世界细节",
            # 文风
            "叙事身份": "这本书用什么声音讲故事（人称/视角/语感）",
            "规则": "这本书的声音侧面与场景写法规则——一条规则一条实例",
            # 文笔/手法共用槽位值「写法」——按概念消歧见 _slot_desc（下方）
            "写法": "同类写法实例的集合——一条一条实际案例",
        }

        buckets: dict[tuple[str, str], list] = {}
        for m in materials:
            p = _payload_of(m)
            slot_key = SLOT_KEY.get(m.concept)
            slot_value = str(p.get(slot_key)).strip() if slot_key else ""
            if not slot_value:
                slot_value = "写法" if m.concept == "手法" else "通用"
            # 桶键＝槽位标签（slot_cn）：手法 fallback「写法」与文笔 craft 同标签归同桶
            buckets.setdefault((m.concept, _slot_label(m.concept, slot_value)), []).append(m)

        # schema 字段元数据＝桶内素材 payload 键的并集（代码可算，无需 LLM）；
        # 系统键与空值键排除。字段 desc 由前端字段字典（kbFieldLabels）补作家语言。
        # archetype（角色名）不再跳过——实例要有实例名（boss 2026-11-07：角色实例
        # 的名字就是角色名）；slot/part 仍跳（分桶键不进字段）
        # 分桶键不进实例字段；role 仅角色设定的分桶键跳（文风的「声音角色」字段要留）
        skip = {"id", "user_id", "slot", "part"}
        if m.concept == "角色设定":
            skip.add("role")
        SKIP_KEYS = skip

        for (concept, slot_value), bucket in sorted(buckets.items()):
            key_set: dict[str, None] = {}
            for m in bucket:
                for k in _payload_of(m):
                    if k not in SKIP_KEYS and k not in key_set:
                        key_set[k] = None
            # 发版知识树（boss 2026-11-08：层次与定义随 C 端发布，案例拆书输出，
            # 总结只做归属）——(类别, 槽位值) 查 kb.taxonomy；命中即用发版标题/定义/父级，
            # 未收录回落既有标签/描述拼装（用户新槽位不炸）
            from kb.taxonomy import node_for

            found = node_for(concept, slot_value)
            node_key, node = (found if found else (None, None))
            # 字段模板：命中发版树即用树上的格（知识对象定义实例的格）；
            # 未收录槽位回落键并集（schema_fields 旧路径，用户新槽位不炸）
            # _tpl_full＝完整模板（含 from/transform，落格用）；tpl_fields＝剥壳版（存 schema_json）
            _tpl_full = (node or {}).get("fields") or []
            tpl_fields = [
                {"name": f["name"], "desc": f.get("desc", "")}
                for f in _tpl_full
            ]
            if node:
                kp_title = node["title"]
                node_definition = node["definition"]
                label = kp_title
            else:
                label = _slot_label(concept, slot_value)
                # 拼装标签对齐发版树（世界 power/extra 案 2026-11-08）：单译标签可能与
                # 节点标题错位（力量与规则 →二次翻译→ 力量体系与规矩）——按拼装结果
                # 重查一次发版树，命中即并入树路径（定义/父级随发版树）
                found2 = node_for(concept, label) if label != slot_value else None
                if found2:
                    node_key, node = found2
                    kp_title = node["title"]
                    node_definition = node["definition"]
                    label = kp_title

            async def _materialize(genre: str, concept: str, title: str, definition: str, parent_id: str, schema_json: str = "[]") -> str:
                """懒物化发版节点：复用同题材×类别×标题行，缺则建（带发版定义与字段模板）。"""
                return await materialize_node_row(
                    db, user_id=user_id, genre=genre, concept=concept,
                    title=title, definition=definition, parent_id=parent_id,
                    schema_json=schema_json,
                )

            # 父链逐级向上物化（发版树数据链；根父为空＝挂题材根）
            from kb.taxonomy import nodes as taxonomy_nodes
            from kb.taxonomy import parent_chain

            parent_id = ""
            if node_key:
                for ck in parent_chain(node_key):  # 顶层在前
                    pn = taxonomy_nodes()[ck]
                    parent_id = await _materialize(genre, pn["concept"], pn["title"], pn["definition"], parent_id)
            else:
                # 其他路径也要根行（其他挂写作知识根下）
                parent_id = await _materialize(
                    genre, "", "写作知识", "这本书学到的写法与设定知识——全树根。", "")

            # 当前节点：命中发版树即物化/复用（带发版定义、字段模板与父级）；
            # 未命中＝落「其他」暂存节点（boss 2026-11-08：树上没有的不临时造，
            # 原始材料进其他，提炼任务从这里归类/长新节点）
            if node:
                kid = await _materialize(genre, concept, kp_title, node_definition, parent_id,
                                         json.dumps(tpl_fields, ensure_ascii=False))
            else:
                kid = await _materialize(
                    genre, "", "其他",
                    "拆书直接输出的原始材料暂存——提炼任务从这里把知识归类进树；树上没有的知识由提炼识别并长出新节点。",
                    parent_id, "",
                )
            for sort, m in enumerate(bucket):
                def _field_val(v):
                    # 章锚剥除接链（2026-11-07 鬼面王案）：拆书素材 payload 的字段值
                    # 可能带「（第N章…）」回查锚（含嵌套形）——实例是可见面，转生即剥；
                    # 剥空项不落（与 repair_chapter_anchors 的 strip_anchors_deep 同口径，
                    # 评审 P3：整项纯锚的别名不残 ""）；锚信息仍留素材卡 payload
                    if v is None:
                        return ""
                    v = strip_anchors_deep(v)
                    if isinstance(v, str):
                        return v[:200]
                    return json.dumps(v, ensure_ascii=False)[:200]
                # 字段不重复正文：载体槽位键（craft/rule/text）与 name/how 都已嵌在
                # 实例正文里（「名字：怎么写」）——再出字段行＝同一内容弹窗里填两遍
                # （真机 2026-11-08 实锤）；只留正文之外的结构化值（章证据/可信度等）
                _inst_text = (m.instruction or "").strip()
                # 正文统一「实例名：一句话」：素材 title＝实例名（角色名/锚名/打法名），
                # instruction 已带名头的不再补；title 与知识名同串的（叙事身份）也不补
                inst_title = (m.title or "").strip()
                inst_body = _inst_text
                if inst_title and inst_body and not inst_body.startswith(inst_title) and inst_title != label:
                    inst_text_out = f"{inst_title}：{inst_body}"
                else:
                    inst_text_out = inst_body or inst_title
                _inst_text = inst_text_out
                _tpl = _tpl_full or None
                if _tpl:
                    # 命中发版树：按知识对象的模板落格（格名/值域/来源全在树上）——
                    # 模板外的产物键不进实例（原型字段不再裸出）
                    fields = _fields_by_template(_tpl, _payload_of(m), _inst_text)
                else:
                    fields = {}
                    for k, v in _payload_of(m).items():
                        if k in SKIP_KEYS:
                            continue
                        fv = _field_val(v)
                        if not fv or (fv in _inst_text):
                            continue
                        fields[k] = fv
                db.add(KbKnowledgeInstance(
                    knowledge_id=kid,
                    text=inst_text_out,
                    source_kind="拆书" if m.src_kind == "deconstruct" else "手录",
                    source_novel=m.src_novel_name or "",
                    # 出处行：章证据列即章号；例证（原文例句）进摘句——「没有案例」补源
                    source_chapter=(m.evidence or "")[:40],
                    quote=(m.example or "")[:500],
                    fields_json=json.dumps(fields, ensure_ascii=False),
                    sort=sort,
                ))
                m.status = "archived"  # 素材行归档（审计可回溯）
            created += 1
    except Exception as exc:  # noqa: BLE001 — 中途异常回滚半截写入，run 置 error 不留 running 孤儿
        await db.rollback()
        await db.execute(
            _t("UPDATE kb_summarize_runs SET status='error', error=:e WHERE id=:i"),
            {"e": f"pipeline: {exc}", "i": run_id},
        )
        await db.commit()
        return {"collected": len(materials), "knowledge": 0}, f"pipeline: {exc}"

    status = "completed"
    await db.execute(
        _t("UPDATE kb_summarize_runs SET status=:s, knowledge_created=:n, error=:e WHERE id=:i"),
        {"s": status, "n": created, "e": "", "i": run_id},
    )
    await db.commit()
    return {"collected": len(materials), "knowledge": created}, ""


async def _last_run_older_than_days(
    db: AsyncSession, *, user_id: str, genre: str, days: int
) -> bool:
    """该题材距上次总结是否超过 days 天（无运行记录＝视为超期，定期兜底触发）。"""
    row = (
        await db.execute(
            _t(
                "SELECT created_at FROM kb_summarize_runs "
                "WHERE user_id=:u AND genre=:g AND status='completed' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"u": user_id, "g": genre},
        )
    ).first()
    if row is None:
        return True
    from datetime import UTC, datetime, timedelta

    try:
        last = datetime.fromisoformat(str(row[0]))
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        return datetime.now(UTC) - last > timedelta(days=days)
    except ValueError:
        return True


async def maybe_auto_summarize(*, user_id: str) -> list[str]:
    """启动钩入口（自开 session，同 organize startup 钩先例）。"""
    from db import async_session

    async with async_session() as db:
        return await _maybe_auto_summarize(db, user_id=user_id)


async def _maybe_auto_summarize(db: AsyncSession, *, user_id: str) -> list[str]:
    await ensure_kb_summarize(db)
    stats = await material_stats(db, user_id=user_id)
    triggered: list[str] = []
    for genre, n in sorted(stats.items()):
        # 触发口径：积压 ≥阈值 或 距上次总结超期。冷却只在「素材数无增量」时生效——
        # 新素材落库（count 超过上次 run 的 materials_scanned）立即再跑，不白等 7 天
        run_row = (
            await db.execute(
                _t(
                    "SELECT materials_scanned, created_at FROM kb_summarize_runs "
                    "WHERE user_id=:u AND genre=:g AND status='completed' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"u": user_id, "g": genre},
            )
        ).first()
        older = await _last_run_older_than_days(db, user_id=user_id, genre=genre, days=7)
        recent_completed = not older
        due = n >= AUTO_MATERIAL_THRESHOLD or older
        if due and recent_completed and run_row is not None and n <= (run_row[0] or 0):
            due = False  # 素材无增量，冷却生效
        if not due:
            continue
        try:
            _run, err = await run_summarize(db, user_id=user_id, genre=genre, trigger="auto")
            if err not in ("", "running"):
                continue
            triggered.append(genre)
        except Exception as exc:  # noqa: BLE001 — 自动钩失败静默（下次启动重试），留痕不抛
            import logging

            logging.getLogger("uvicorn.error").warning(
                "kb summarize auto trigger failed for %s: %s", genre, exc,
            )
            continue
    return triggered
