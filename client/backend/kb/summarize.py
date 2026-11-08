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
        SLOT_KEY = {"角色设定": "role", "文风": "slot", "文笔": "slot", "世界设定": "part"}

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
            schema_fields = [{"name": k, "desc": ""} for k in key_set]

            label = _slot_label(concept, slot_value)
            # 复用既有知识点（同题材×类别×标题）：多本书先后重建不再各长一套重名知识点
            # （真机实锤：斩神/749 顺序收敛后「都市·写法 ×2」「都市·配角 ×2」全部成对）
            existing_kp = (await db.scalars(
                select(KbEntry).where(
                    KbEntry.user_id == user_id,
                    KbEntry.genre == genre,
                    KbEntry.concept == concept,
                    KbEntry.origin == "summary",
                    KbEntry.title == label,
                ).limit(1)
            )).first()
            fresh_kp = existing_kp is None
            if fresh_kp:
                kid = uuid.uuid4().hex
            else:
                kid = existing_kp.id
            kp_definition = f"{genre}·{label}——{_slot_desc(concept, slot_value)}。已收 {len(bucket)} 条实例。"
            if fresh_kp:
                db.add(KbEntry(
                    id=kid,
                    user_id=user_id,
                    genre=genre,
                    concept=concept,
                    concept_id=f"{genre}:{concept}",
                    title=label,
                    payload_json="{}",
                    instruction="",
                    definition=kp_definition,
                    schema_json=json.dumps(schema_fields, ensure_ascii=False),
                    origin="summary",
                    status="active",
                    version=1,
                    parent_id="",
                ))
            else:
                # 复用也刷新定义：旧知识点可能带模板兜底句/陈旧计数（真机实锤「定义缺失」）
                existing_kp.definition = kp_definition
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
                fields = {k: _field_val(v) for k, v in _payload_of(m).items()
                          if k not in SKIP_KEYS and _field_val(v)}
                db.add(KbKnowledgeInstance(
                    knowledge_id=kid,
                    text=m.instruction or "",
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
