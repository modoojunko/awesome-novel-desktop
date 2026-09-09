from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.middleware import get_current_user
from db import get_db
from novels.ai_backfill import step1_backfill, step2_backfill
from novels.events import log_event
from novels.service import get_novel
from workflow.gates import (
    PHASE_ORDER,
    gate_chapter_ready,
    gate_prompts_exist,
    gate_settings_complete,
    get_phase_status,
)
from workflow.tier import tier_bypass, tier_or_gate, tier_phase_transition

router = APIRouter(prefix="/api/novels/{project_id}/workflow", tags=["workflow"])


@router.post("/transition")
async def transition_workflow(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    target = body.get("target")
    if not target:
        raise HTTPException(400, "target is required")

    if target == "outline":
        # Soft gate: check settings but do not block (tier_or_gate: free 恒过)
        result = await tier_or_gate(
            db, project, gate_settings_complete, project.root_path, project.id
        )
        # hard_block is False for settings, so this always passes through
        if result.hard_block and not result.valid:
            raise HTTPException(
                400,
                {
                    "error": "Settings incomplete",
                    "warnings": result.warnings,
                },
            )

        tier_phase_transition(project, "outline")
        await db.commit()
        return {
            "ok": True,
            "phase": project.current_phase,
            "warnings": result.warnings,
        }

    if target == "prompt":
        # Hard gate: chapters must be ready before generating prompts（章族入库：DB 组装）
        from chapters.store import assemble_chapter
        from workflow.gates import _chapters_by_root

        failures = []
        for row in await _chapters_by_root(project.root_path):
            result = await tier_or_gate(
                db, project, gate_chapter_ready, assemble_chapter(row)
            )
            if result.hard_block and not result.valid:
                failures.append({"chapter_ref": row.ref, "missing": result.warnings})

        if failures:
            raise HTTPException(
                400,
                {
                    "error": "Some chapters are not ready",
                    "failures": failures,
                },
            )

        tier_phase_transition(project, "prompt")
        await db.commit()
        return {"ok": True, "phase": project.current_phase}

    if target == "write":
        # Hard gate: prompts must exist before writing（章族入库：DB 章 ref 列表）
        from workflow.gates import _chapters_by_root

        failures = []
        for row in await _chapters_by_root(project.root_path):
            result = await tier_or_gate(
                db, project, gate_prompts_exist, project.root_path, row.ref
            )
            if result.hard_block and not result.valid:
                failures.append({"chapter_ref": row.ref, "missing": result.warnings})

        if failures:
            raise HTTPException(
                400,
                {
                    "error": "Some chapters have no prompts",
                    "failures": failures,
                },
            )

        tier_phase_transition(project, "write")
        await db.commit()
        return {"ok": True, "phase": project.current_phase}

    raise HTTPException(400, f"Unsupported target: {target}")


@router.get("/phase-status")
async def phase_status_endpoint(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return six-phase completion status + warnings for the current project."""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    if tier_bypass():
        # 免费态：不展示阶段、不催促（N14），phases 全 complete + tier_bypass 标记
        return {
            "phases": {p: "complete" for p in PHASE_ORDER},
            "warnings": [],
            "tier_bypass": True,
        }
    status = await get_phase_status(
        project.root_path, project.current_phase, project
    )
    return status


# ── AI Backfill endpoints ───────────────────────────────────────────────────

backfill_router = APIRouter(prefix="/api/novels/{project_id}", tags=["backfill"])


@backfill_router.get("/ai-backfill/status")
async def ai_backfill_status(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    return {"backfill_status": project.backfill_status or "none"}


@backfill_router.post("/ai-backfill/step1")
async def ai_backfill_step1(
    project_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")

    project.backfill_status = "step1_running"
    await db.commit()

    root_path = project.root_path

    try:
        result = await step1_backfill(root_path, project_id)
        all_fields = any([
            result.get("synopsis"),
            result.get("world_setting"),
            result.get("characters"),
        ])
        project.backfill_status = "step1_done" if all_fields else "step1_partial"
        await db.commit()
        return result | {"backfill_status": project.backfill_status}
    except Exception as e:
        project.backfill_status = "step1_partial"
        await db.commit()
        raise HTTPException(500, str(e))


@backfill_router.post("/ai-backfill/step2")
async def ai_backfill_step2(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")

    project.backfill_status = "step2_running"
    await db.commit()

    root_path = project.root_path
    step1_result = body.get("step1_result", {})

    try:
        result = await step2_backfill(root_path, project_id, step1_result)
        project.backfill_status = "step2_done"
        await db.commit()
        return result | {"backfill_status": "step2_done"}
    except Exception as e:
        project.backfill_status = "step2_running"
        await db.commit()
        raise HTTPException(500, str(e))


@backfill_router.put("/ai-backfill/confirm")
async def confirm_backfill_step(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    log_event(db, user["id"], "ai_backfill_saved", {"novel_id": project_id})
    return {"ok": True, "backfill_status": project.backfill_status}
