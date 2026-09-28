"""章档提取流水线（c-chapter-dossier D1/D3/D4）——受理制归档的心脏。

- 受理（accept_extraction）：每章键控单飞——同章在跑返回 in_flight（幂等）；
  否则落 ChapterDossierJob(extracting) 行＋起后台线程。跨章并发信号量 2。
- 提取（_extract_and_finalize）：一次 AI 调用出四域 JSON（分层模板
  chapter_archive_extract.prompt，json_mode＋max_tokens=1600）；输入＝正文≤6000 字
  ＋世界摘要＋截至上一章累计章档＋cast＋专名名册。
- 后处理（_postprocess）：解析失败＝四域 failed；缺键＝空数组 extracted；
  证据句宽松校验（不匹配保留＋标 evidence_unverified，永不驱动重试）；
  名册外名字保留＋标 unregistered；每域 ≤6 条、单条 ≤60 字 clamp。
- 收口（finalize_archive）单源：四域行整体替换＋archives 行＋伏笔 mentioned＋
  status/archived_at/total_archives/tier phase＋job 行，一个事务；模型未就绪
  放行路径与逃生阀跳过路径复用（dossier_payload=None）。
- 启动 sweep：extracting 且无线程的 job 置 failed(interrupted)。

门禁豁免同 archive/service.py：本模块是 try/except 降级路径（模型未就绪→放行
归档），非 require_novel_model 门控对象（ai_client.py grep ④ 豁免名单）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
from datetime import UTC, datetime

from sqlalchemy import select

from db import async_session

# 每章键控单飞 + 跨章并发上限（AI 客户端是真实瓶颈）
_running: set[str] = set()
_running_lock = threading.Lock()
_extract_sem = threading.Semaphore(2)

# 提取域（job.domains 键）→ 章 JSON dossier 键
DOMAIN_JSON_KEYS = {"setting": "settings", "relation": "relations", "item": "items", "knowledge": "knowledge"}
_MAX_PER_DOMAIN = 6
_MAX_FIELD = 60
_PROSE_INPUT_MAX = 6000


def prose_sha256(prose: str) -> str:
    return hashlib.sha256((prose or "").encode("utf-8")).hexdigest()


def _now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ── job 行 ──────────────────────────────────────────────────────────────────


async def _get_job(session, chapter_id: str):
    from models.chapter import ChapterDossierJob

    return await session.scalar(
        select(ChapterDossierJob).where(ChapterDossierJob.chapter_id == chapter_id)
    )


async def get_job_state(chapter_id: str) -> dict | None:
    """单章提取任务状态（受理轮询/页签进度用）；无 job 行返回 None。"""
    async with async_session() as session:
        job = await _get_job(session, chapter_id)
        if job is None:
            return None
        try:
            domains = json.loads(job.domains or "{}")
        except ValueError:
            domains = {}
        return {
            "state": job.state,
            "domains": domains,
            "error": job.error,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }


async def sweep_stuck_jobs() -> int:
    """启动 sweep：extracting 且无线程的 job 置 failed(interrupted)——防章永久悬归档中。"""
    from models.chapter import ChapterDossierJob

    n = 0
    async with async_session() as session:
        jobs = (
            await session.scalars(
                select(ChapterDossierJob).where(ChapterDossierJob.state == "extracting")
            )
        ).all()
        for job in jobs:
            with _running_lock:
                if job.chapter_id in _running:
                    continue
            job.state = "failed"
            job.error = "interrupted: 应用重启，提取中断，可重试"
            n += 1
        if n:
            await session.commit()
    return n


# ── 受理 ────────────────────────────────────────────────────────────────────


async def accept_extraction(
    novel_id: str,
    root_path: str,
    chapter_ref: str,
    chapter_id: str,
    prose_hash: str,
    *,
    ai_summary: bool = True,
    rows_only: bool = False,
) -> dict:
    """受理提取：同章在跑→in_flight（幂等）；否则置 job(extracting)＋起后台线程。

    rows_only＝补提取模式（章已 archived：只重写章档行、不动归档收口）。
    """
    from models.chapter import ChapterDossierJob

    with _running_lock:
        if chapter_id in _running:
            return {"accepted": True, "state": "extracting", "dedup": "in_flight"}
        _running.add(chapter_id)

    async with async_session() as session:
        job = await _get_job(session, chapter_id)
        if job is None:
            job = ChapterDossierJob(
                chapter_id=chapter_id, novel_id=novel_id,
                state="extracting", prose_hash=prose_hash,
            )
            session.add(job)
        else:
            job.state = "extracting"
            job.prose_hash = prose_hash
            job.error = ""
            job.domains = "{}"
        await session.flush()
        job_id = job.id
        await session.commit()

    t = threading.Thread(
        target=_run_thread,
        args=(novel_id, root_path, chapter_ref, chapter_id, job_id, ai_summary, rows_only),
        daemon=True,
    )
    t.start()
    return {"accepted": True, "state": "extracting", "job_id": job_id}


def _run_thread(
    novel_id: str, root_path: str, chapter_ref: str, chapter_id: str,
    job_id: str, ai_summary: bool, rows_only: bool,
) -> None:
    try:
        asyncio.run(
            _extract_and_finalize(
                novel_id, root_path, chapter_ref, chapter_id, ai_summary, rows_only
            )
        )
    except Exception as e:  # noqa: BLE001 — 提取失败章不归档；落 job 行供重试
        print(f"[dossier] chapter {chapter_ref} 提取线程异常：{e}")
        try:
            asyncio.run(_fail_job(chapter_id, {}, f"internal: {e}"))
        except Exception:  # noqa: BLE001,S110
            pass
    finally:
        with _running_lock:
            _running.discard(chapter_id)


async def _fail_job(chapter_id: str, domains: dict, error: str) -> None:
    async with async_session() as session:
        job = await _get_job(session, chapter_id)
        if job is not None:
            job.state = "failed"
            job.domains = json.dumps(domains, ensure_ascii=False)
            job.error = str(error)[:500]
            await session.commit()


# ── 提取主体 ────────────────────────────────────────────────────────────────


async def _extract_and_finalize(
    novel_id: str, root_path: str, chapter_ref: str, chapter_id: str,
    ai_summary: bool, rows_only: bool,
) -> None:
    from ai_client import get_ai_client_for_novel
    from models.chapter import Chapter, ChapterContent
    from write.story_state import story_state_upto

    async with async_session() as session:
        chapter = await session.get(Chapter, chapter_id)
        if chapter is None:
            await _fail_job(chapter_id, {}, "chapter not found")
            return
        job = await _get_job(session, chapter_id)
        prose_hash = job.prose_hash if job is not None else ""
        # ChapterContent 主键是 id 不是 chapter_id——按外键查（UNIQUE 一章一行）
        content = (
            await session.scalars(
                select(ChapterContent).where(ChapterContent.chapter_id == chapter_id)
            )
        ).first()
        prose = content.prose if content is not None else ""
        title = chapter.title
        cast_names = [c.character_name for c in chapter.characters]
        # Chapter.project 是懒加载关系（异步上下文外触发 IO 被禁）——按 id 直查
        from models.project import Novel

        project = await session.get(Novel, chapter.project_id)
        root = project.root_path if project is not None else root_path

    # 受理后正文被改：以漂移正文收口会让证据句对不上——判失败提示重试
    if prose_sha256(prose) != prose_hash:
        await _fail_job(
            chapter_id, {},
            "prose_changed: 提取期间正文被修改，请重新归档以按最终稿提取",
        )
        return

    # ① 组装输入
    from filesystem.storage import get_storage
    from settings.world_model import world_summary_text

    world_raw = await get_storage().read_yaml(root, "settings/world-setting.yaml") or {}
    world_now = world_summary_text(world_raw, None).strip()[:1200]
    baseline_state = await story_state_upto(novel_id, chapter_ref, exclusive=True)
    baseline_text = _baseline_block(baseline_state)
    cast_s = "、".join(n for n in cast_names if n) or "（本章章纲未登记出场角色）"

    from settings.name_registry import known_names, roster_text

    async with async_session() as db:
        from models.project import Novel

        proj = await db.get(Novel, novel_id)
        names = await known_names(db, proj) if proj is not None else {}
    roster = roster_text(names)
    roster_chars = set(names.get("characters") or set())

    from prompts import load_layers

    sys_prompt, user_template = load_layers("chapter_archive_extract")
    user_prompt = user_template.format(
        world=world_now or "（未填世界设定）",
        baseline=baseline_text,
        cast=cast_s,
        roster=roster,
        chapter_ref=chapter_ref,
        prose=(prose or "")[:_PROSE_INPUT_MAX],
    )

    # ② 一次调用四域（json_mode＋1600 输出预算）
    usage: dict = {}
    try:
        client = await get_ai_client_for_novel(novel_id)
    except Exception:  # noqa: BLE001 — 受理时已就绪但中途失效：判失败可重试
        await _fail_job(chapter_id, {}, "model_unavailable: 本书模型不可用，可重试")
        return

    from archive.service import _record_ai_usage

    with _extract_sem:
        try:
            text = await client.chat(
                model="haiku",
                system=sys_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=1600,
                usage=usage,
                json_mode=True,
            )
            await _record_ai_usage(novel_id, "archive_extract", usage)
        except Exception as e:  # noqa: BLE001 — 调用失败＝四域 failed，可重试
            await _record_ai_usage(novel_id, "archive_extract_fail", usage, force=True)
            await _fail_job(chapter_id, {}, f"ai_call: {e}")
            return

    # ③ 解析＋后处理（确定性宽松：失败＝四域 failed；缺键＝空数组）
    data = _parse_json_lenient(text)
    if data is None:
        await _record_ai_usage(novel_id, "archive_extract_parse_fail", usage, force=True)
        await _fail_job(chapter_id, {}, "parse: 模型输出不是可解析的 JSON，可重试")
        return
    payload = _postprocess(data, prose or "", roster_chars)

    # ④ 收口（rows_only＝补提取：只重写章档行，不动归档收口）
    summary = None
    if not rows_only:
        from archive.service import make_archive_summary

        summary = await make_archive_summary(novel_id, prose or "", ai_summary)
    await finalize_archive(
        novel_id=novel_id,
        root_path=root,
        chapter_id=chapter_id,
        chapter_ref=chapter_ref,
        title=title,
        full_text=prose or "",
        summary=summary,
        dossier_payload=payload,
        job_state="ok",
        domains_json=json.dumps(
            {k: "extracted" for k in DOMAIN_JSON_KEYS}, ensure_ascii=False
        ),
        rows_only=rows_only,
    )
    if not rows_only:
        _maybe_start_reconcile(novel_id, root, chapter_ref, chapter_id)


def _maybe_start_reconcile(
    novel_id: str, root_path: str, chapter_ref: str, chapter_id: str
) -> None:
    """旧收尾提案（伏笔登记/世界 lore，PRO 门控）随归档成功触发——后台线程，
    失败/免费档不影响归档结果（archive-reconcile 既有语义）。"""
    try:
        from auth_local.deps import ai_access_granted

        if not ai_access_granted():
            return
        from archive.reconcile import start_reconcile_job

        start_reconcile_job(novel_id, root_path, chapter_ref, chapter_id)
    except Exception:  # noqa: BLE001,S110 — 收尾是附带动作，任何失败不冒泡
        pass


# ── 收口单源 ────────────────────────────────────────────────────────────────


async def finalize_archive(
    *,
    novel_id: str,
    root_path: str,
    chapter_id: str,
    chapter_ref: str,
    title: str,
    full_text: str,
    summary: str | None,
    dossier_payload: dict | None,
    job_state: str | None,
    domains_json: str = "{}",
    rows_only: bool = False,
) -> dict:
    """归档收口单源（一个事务）：四域行整体替换＋archives 行＋伏笔 mentioned＋
    status/archived_at/total_archives/tier phase＋job 行。

    - dossier_payload=None：模型未就绪放行 / 逃生阀跳过（无章档收口）。
    - rows_only=True：补提取模式——只替换章档行＋清 dossier_stale＋job 行，
      不动 status/archives/计数/threads。
    - summary=None 且非 rows_only：调用方应已给降级摘要（正文前 200 字）。
    """
    from archive.naming import archive_filename
    from chapters.store import _apply_dossier, _resolve_names
    from models.archive import Archive
    from models.chapter import Chapter
    from settings.hooks_service import mark_hooks_mentioned
    from workflow.tier import tier_phase_transition

    archive_path = f"archives/{archive_filename(chapter_ref, str(title)[:200])}"
    async with async_session() as session:
        chapter = await session.get(Chapter, chapter_id)
        if chapter is None:
            raise LookupError(f"chapter row not found for {chapter_ref}")
        was_archived = chapter.status == "archived"

        if dossier_payload is not None:
            names = [
                str(item.get(key, "")).strip()[:50]
                for item in (
                    list(dossier_payload.get("relations") or [])
                    + list(dossier_payload.get("knowledge") or [])
                )
                if isinstance(item, dict)
                for key in (("owner", "other") if "owner" in item else ("character",))
                if str(item.get(key, "")).strip()
            ]
            name_map = await _resolve_names(session, novel_id, names)
            for attr in ("dossier_settings", "dossier_relations", "dossier_items", "dossier_knowledge"):
                getattr(chapter, attr).clear()
            await session.flush()
            _apply_dossier(chapter, dossier_payload, name_map)
            chapter.dossier_stale = False

        if not rows_only:
            final_summary = str(summary if summary is not None else full_text[:200])[:300]
            arc = await session.scalar(
                select(Archive).where(Archive.chapter_id == chapter_id)
            )
            if arc is None:
                session.add(
                    Archive(
                        chapter_id=chapter_id,
                        title=str(title)[:200],
                        summary=final_summary,
                        content=full_text,
                    )
                )
            else:
                arc.title = str(title)[:200]
                arc.summary = final_summary
                arc.content = full_text
            await mark_hooks_mentioned(session, novel_id, chapter_id)
            chapter.status = "archived"
            chapter.archived_at = _now_naive()
            # dossier_stale 只在真重提（dossier_payload 分支）时清——跳过提取
            # （skip 路径 payload=None）不清：旧档基于旧设定的角标保留到补提取
            # Chapter.project 懒加载关系不可在异步属性访问上触发——按 id 直查
            from models.project import Novel

            project = await session.get(Novel, chapter.project_id)
            if project is not None:
                if not was_archived:
                    project.total_archives = (project.total_archives or 0) + 1
                tier_phase_transition(project, "archive", force=True)

        if job_state is not None:
            job = await _get_job(session, chapter_id)
            if job is not None:
                job.state = job_state
                job.domains = domains_json
                job.error = ""
        await session.commit()

    if not rows_only:
        # threads.yaml：commit 后尽力而为（写失败不回滚已生效的归档）
        from archive.service import update_thread_state

        try:
            volume_no = chapter.volume.volume_no
            await update_thread_state(
                root_path,
                {
                    "volume": volume_no,
                    "chapter": chapter.chapter_no,
                    "thread": "主线",
                },
                str(summary if summary is not None else full_text[:200])[:300],
            )
        except Exception as e:  # noqa: BLE001,S110
            print(f"[dossier] threads.yaml 更新失败（不影响归档）：{e}")
    return {"archive_path": archive_path, "summary": (summary or full_text[:200])[:300]}


async def skip_extraction_and_archive(
    novel_id: str,
    root_path: str,
    chapter_ref: str,
    chapter_id: str,
    full_text: str,
) -> dict:
    """逃生阀：跳过提取仍归档——与模型未就绪同一收口路径（archived、无章档）。"""
    return await finalize_archive(
        novel_id=novel_id,
        root_path=root_path,
        chapter_id=chapter_id,
        chapter_ref=chapter_ref,
        title=await _chapter_title(chapter_id),
        full_text=full_text,
        summary=None,
        dossier_payload=None,
        job_state="skipped",
    )


async def _chapter_title(chapter_id: str) -> str:
    from models.chapter import Chapter

    async with async_session() as session:
        ch = await session.get(Chapter, chapter_id)
        return ch.title if ch is not None else "untitled"


# ── 解析与后处理（确定性，永不驱动重试）────────────────────────────────────


def _parse_json_lenient(text: str) -> dict | None:
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


_MATCH_STRIP = set("，。！？；：、\u201c\u201d\u2018\u2019《》（）…—·,.!?;:'\"()<>[]{} \t\n\r")


def _match_norm(s: str) -> str:
    return "".join(ch for ch in str(s or "") if ch not in _MATCH_STRIP)


def evidence_verified(evidence: str, prose: str) -> bool:
    """宽松包含：归一后 ≥12 字连续子串命中，或 bigram 重叠 ≥80%。"""
    ev, pr = _match_norm(evidence), _match_norm(prose)
    if not ev:
        return False
    if ev in pr:
        return True
    if len(ev) < 2:
        return False
    grams = {ev[i : i + 2] for i in range(len(ev) - 1)}
    hit = sum(1 for g in grams if g in pr)
    return bool(grams) and hit / len(grams) >= 0.8


def _clip(s, n: int = _MAX_FIELD) -> str:
    return str(s or "").strip()[:n]


def _postprocess(data: dict, prose: str, roster_chars: set[str]) -> dict:
    """四域归一：缺键→空数组；每域 ≤6 条；字段 clamp；flags（不匹配保留标记）。"""

    def _rows(key: str) -> list[dict]:
        raw = data.get(key)
        return [r for r in (raw if isinstance(raw, list) else []) if isinstance(r, dict)][:_MAX_PER_DOMAIN]

    def _ev_flags(evidence: str, names: list[str]) -> str:
        flags = []
        if not evidence_verified(evidence, prose):
            flags.append("evidence_unverified")
        if roster_chars and any(n and n not in roster_chars for n in names):
            flags.append("unregistered")
        return ",".join(flags)

    settings = [
        {
            "area": _clip(s.get("area"), 50),
            "content": _clip(s.get("content")),
            "evidence": _clip(s.get("evidence")),
            "status": "pending",
            "flags": _ev_flags(s.get("evidence"), []),
        }
        for s in _rows("settings")
        if _clip(s.get("content"))
    ]
    relations = []
    for r in _rows("relations"):
        owner, other = _clip(r.get("owner"), 50), _clip(r.get("other"), 50)
        if not owner or not other:
            continue
        relations.append({
            "owner": owner, "other": other,
            "rel_type": _clip(r.get("rel_type"), 50),
            "change_note": _clip(r.get("change_note")),
            "evidence": _clip(r.get("evidence")),
            "status": "pending",
            "flags": _ev_flags(r.get("evidence"), [owner, other]),
        })
    items = [
        {
            "name": _clip(it.get("name"), 100),
            "change_type": _clip(it.get("change_type"), 50),
            "holder": _clip(it.get("holder"), 50),
            "detail": _clip(it.get("detail")),
            "evidence": _clip(it.get("evidence")),
            "status": "pending",
            "flags": _ev_flags(it.get("evidence"), []),
        }
        for it in _rows("items")
        if _clip(it.get("name"))
    ]
    knowledge = []
    for k in _rows("knowledge"):
        character = _clip(k.get("character"), 50)
        fact = _clip(k.get("fact"))
        if not character or not fact:
            continue
        knowledge.append({
            "character": character, "fact": fact,
            "learned": bool(k.get("learned", True)),
            "evidence": _clip(k.get("evidence")),
            "status": "pending",
            "flags": _ev_flags(k.get("evidence"), [character]),
        })
    return {"settings": settings, "relations": relations, "items": items, "knowledge": knowledge}


def _baseline_block(state: dict) -> str:
    """累计章档 → 提示词基线块（已采纳、截至上一章）。"""
    lines: list[str] = []
    for s in state.get("settings") or []:
        lines.append(f"- 设定·{s['area']}：{s['content']}")
    for r in state.get("relations") or []:
        note = f"（{r['change_note']}）" if r.get("change_note") else ""
        lines.append(f"- 关系·{r['owner']}→{r['other']}：{r['rel_type']}{note}")
    for it in state.get("items") or []:
        holder = f"（在 {it['holder']} 手中）" if it.get("holder") else ""
        lines.append(f"- 物品·{it['name']}{holder}")
    for k in state.get("knowledge") or []:
        verb = "已得知" if k.get("learned") else "仍不知道"
        lines.append(f"- 认知·{k['character']}{verb}「{k['fact']}」")
    return "\n".join(lines) if lines else "（上一章无已确认章档——本章全部按新增提取）"
