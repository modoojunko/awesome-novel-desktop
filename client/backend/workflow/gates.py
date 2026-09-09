from dataclasses import dataclass, field

from filesystem.storage import get_storage

PHASE_ORDER = ["init", "settings", "outline", "prompt", "write", "archive"]


@dataclass
class GateResult:
    """Standardized gate check result.

    valid:       True when all required conditions are met.
    warnings:    Human-readable list of what is missing or suboptimal.
                 Empty when valid=True. Non-empty when valid=False
                 (soft gate) or when passed but with suggestions.
    hard_block:  When True, the transition MUST be rejected (400).
                 When False, it is a soft gate — the caller may proceed
                 but should show warnings to the user.
    """

    valid: bool = True
    warnings: list[str] = field(default_factory=list)
    hard_block: bool = False


async def gate_settings_complete(root_path: str, novel_id: str | None = None) -> GateResult:
    """Check if settings are complete enough to start outlining.

    Product decision (2026-08-02): completion = the author clicked "完成设定"
    (ConfirmToggle) for the item AND its content passed the non-empty check
    (enforced in PUT /settings/status/{type}). This gate therefore reads the
    confirmation markers (settings-status.yaml); readiness content checks are
    used only as supplementary Chinese guidance.

    Soft gate — warns but does not block.
    """
    from workflow.readiness import READINESS_KEYS, compute_readiness

    status = await get_storage().read_yaml(root_path, "settings/settings-status.yaml") or {}
    unconfirmed = [k for k in READINESS_KEYS if not bool(status.get(k))]
    if not unconfirmed:
        return GateResult(valid=True, warnings=[])

    readiness = await compute_readiness(root_path, novel_id)
    labels = {m["key"]: m["label"] for m in readiness["missing"]}
    warnings = [f"尚未完成设定: {labels.get(k, k)}" for k in unconfirmed]
    if readiness["missing"]:
        warnings.append(readiness["warning"])
    return GateResult(
        valid=True,
        warnings=warnings,
        hard_block=False,
    )


def gate_chapter_ready(chapter_data: dict) -> GateResult:
    """Check if chapter outline is ready for prompt generation.

    Hard gate — missing fields block transition to prompt.
    """
    missing = []
    memo = chapter_data.get("memo", {})

    if not memo.get("current_task"):
        missing.append("核心任务")
    rexp = memo.get("reader_expectation", {})
    if not rexp.get("state"):
        missing.append("读者当前状态")
    if not rexp.get("strategy"):
        missing.append("预期策略")
    changes = memo.get("required_changes", [])
    if not changes:
        missing.append("必须完成的变化")
    ed = chapter_data.get("emotional_design", {})
    if not ed.get("primary_mood"):
        missing.append("主情绪")
    segments = chapter_data.get("segments", [])
    if not segments:
        missing.append("段落规划")

    return GateResult(
        valid=len(missing) == 0,
        warnings=missing,
        hard_block=True,
    )


async def gate_prompts_exist(root_path: str, chapter_ref: str) -> GateResult:
    """Check if prompt row exists for given chapter（chapter_prompts 表，PR④）.

    Hard gate — no prompt means cannot write.
    """
    from sqlalchemy import select

    from db import async_session
    from models.archive import ChapterPrompt
    from models.chapter import Chapter
    from models.project import Novel

    async with async_session() as session:
        prompt_id = await session.scalar(
            select(ChapterPrompt.id)
            .join(Chapter, Chapter.id == ChapterPrompt.chapter_id)
            .join(Novel, Novel.id == Chapter.project_id)
            .where(Novel.root_path == root_path, Chapter.ref == chapter_ref)
            .limit(1)
        )
    exists = prompt_id is not None
    return GateResult(
        valid=exists,
        warnings=[] if exists else [f"prompt for {chapter_ref} not generated yet"],
        hard_block=True,
    )


def gate_quality_passed(chapter_data: dict) -> GateResult:
    """Check if quality check has passed."""
    passed = chapter_data.get("quality_check", {}).get("passed", False)
    return GateResult(
        valid=passed,
        warnings=[] if passed else ["quality check not passed"],
        hard_block=True,
    )


async def _chapters_by_root(root_path: str) -> list:
    """root_path → 项目全部章行（selectin 已带子表/正文，供组装/派生）。"""
    from sqlalchemy import select

    from db import async_session
    from models.chapter import Chapter
    from models.project import Novel

    stmt = (
        select(Chapter)
        .join(Novel, Novel.id == Chapter.project_id)
        .where(Novel.root_path == root_path)
        .order_by(Chapter.ref)
    )
    async with async_session() as session:
        return list((await session.scalars(stmt)).all())


async def _volume_count_by_root(root_path: str) -> int:
    from sqlalchemy import func as sa_func
    from sqlalchemy import select as sa_select

    from db import async_session
    from models.project import Novel
    from models.volume import Volume

    stmt = (
        sa_select(sa_func.count(Volume.id))
        .join(Novel, Novel.id == Volume.project_id)
        .where(Novel.root_path == root_path)
    )
    async with async_session() as session:
        return await session.scalar(stmt) or 0


async def gate_outline_exists(root_path: str) -> GateResult:
    """Check if at least one volume exists（卷族入库：DB 计数）.

    Soft gate — reminds but allows proceeding.
    """
    if await _volume_count_by_root(root_path) == 0:
        return GateResult(
            valid=True,
            warnings=["no volumes created yet"],
            hard_block=False,
        )
    return GateResult(valid=True, warnings=[])


async def gate_prose_written(root_path: str) -> GateResult:
    """Check if at least one chapter has prose content written（章族入库：DB 判 has_prose）.

    Soft gate — reminds progress.
    """
    rows = await _chapters_by_root(root_path)
    if not rows:
        return GateResult(
            valid=True,
            warnings=["no chapters created yet"],
            hard_block=False,
        )
    written = sum(1 for r in rows if r.has_prose)
    if written < len(rows):
        return GateResult(
            valid=True,
            warnings=[f"prose written for {written}/{len(rows)} chapters"],
            hard_block=False,
        )
    return GateResult(valid=True, warnings=[])


async def gate_archived(root_path: str) -> GateResult:
    """Check if any chapters have been archived.

    Soft gate — reminds progress.
    """
    from sqlalchemy import select

    from db import async_session
    from models.archive import Archive
    from models.chapter import Chapter
    from models.project import Novel

    async with async_session() as session:
        arch_id = await session.scalar(
            select(Archive.id)
            .join(Chapter, Chapter.id == Archive.chapter_id)
            .join(Novel, Novel.id == Chapter.project_id)
            .where(Novel.root_path == root_path)
            .limit(1)
        )
    if arch_id is None:
        return GateResult(
            valid=True,
            warnings=["no chapters archived yet"],
            hard_block=False,
        )
    return GateResult(valid=True, warnings=[])


async def get_phase_status(
    root_path: str, current_phase: str, db_project=None
) -> dict:
    """Aggregate six phase completion statuses.

    Returns a dict with:
      - phases: {phase_name: "complete"|"in_progress"|"skipped"|"pending"}
      - warnings: [{"phase": str, "message": str}]

    "skipped" meaning: current_phase > phase and its gate_valid=false.
    卷/章/提示词/归档全量入库后，各门控直接查 DB；盘上无业务文件可读。
    """
    if current_phase not in PHASE_ORDER:
        current_phase = "init"

    phase_idx = PHASE_ORDER.index(current_phase)

    # --- Run all gates ---

    # novel_id 有值时题材判据查 novel_genre 表（D19）；无值时回退旧 KV。
    settings_result = await gate_settings_complete(
        root_path, db_project.id if db_project is not None else None
    )
    outline_result = await gate_outline_exists(root_path)

    # All chapters check（章族入库：DB 行 → 组装章 JSON 供门控）
    from chapters.store import assemble_chapter

    chapter_rows = await _chapters_by_root(root_path)
    chapter_refs = [r.ref for r in chapter_rows]

    all_chapters_ready = True
    chapter_warnings: list[str] = []
    for row in chapter_rows:
        r = gate_chapter_ready(assemble_chapter(row))
        if not r.valid:
            all_chapters_ready = False
            chapter_warnings.extend(r.warnings)

    # Prompt check: only if there are chapters
    prompt_result = GateResult(valid=True, warnings=[])
    if chapter_refs:
        for ref in chapter_refs:
            r = await gate_prompts_exist(root_path, ref)
            if not r.valid:
                prompt_result = r
                break

    prose_result = await gate_prose_written(root_path)
    archive_result = await gate_archived(root_path)

    # --- Phase-gate mapping ---
    phase_gates = {
        "settings": settings_result,
        "outline": outline_result,
        "prompt": prompt_result,
        "write": prose_result,
        "archive": archive_result,
    }

    phases: dict[str, str] = {}
    warnings_output: list[dict[str, str]] = []

    for i, phase in enumerate(PHASE_ORDER):
        if phase == "init":
            if phase_idx > i:
                phases[phase] = "complete"
            elif phase_idx == i:
                phases[phase] = "in_progress"
            else:
                phases[phase] = "pending"
            continue

        gate_result = phase_gates.get(phase)
        if gate_result is None:
            phases[phase] = "pending"
            continue

        # For "outline" phase, also check all_chapters_ready for completeness
        if phase == "outline":
            combined_valid = gate_result.valid and all_chapters_ready
        else:
            combined_valid = gate_result.valid

        if phase_idx > i:
            # Past this phase — was it completed or skipped?
            phases[phase] = "complete" if combined_valid else "skipped"
        elif phase_idx == i:
            phases[phase] = "in_progress"
        else:
            phases[phase] = "pending"

        # Collect warnings for the current and past phases
        if phase_idx >= i:
            for w in gate_result.warnings:
                warnings_output.append({"phase": phase, "message": w})

        # Chapter outline warnings for outline phase
        if phase == "outline" and phase_idx >= i and not all_chapters_ready:
            for w in chapter_warnings[:3]:  # limit to top 3
                warnings_output.append({"phase": phase, "message": w})

    return {
        "phases": phases,
        "warnings": warnings_output,
    }
