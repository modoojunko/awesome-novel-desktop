"""Story deduction API routes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import ensure_novel_model_ready, require_ai_access
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from story.engine import DeductionEngine

router = APIRouter(prefix="/api/story", tags=["story"])

# In-memory store for active deduction sessions
_active: dict[str, DeductionEngine] = {}


def _get_engine(deduction_id: str) -> DeductionEngine:
    engine = _active.get(deduction_id)
    if not engine:
        raise HTTPException(404, "Deduction session not found")
    return engine


@router.post("/init")
async def init_deduction(
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    db: AsyncSession = Depends(get_db),
):
    """Initialize a deduction session from project data."""
    project_id = body.get("project_id")
    chapter_ref = body.get("chapter_ref")
    if not project_id:
        raise HTTPException(400, "project_id is required")

    # key-crypto-selfcontained：模型链路未就绪（含 Key 死文）在装载前早拦，
    # 不让会话建到一半才在首轮 503/静默空回合
    await ensure_novel_model_ready(db, user["id"], project_id)

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    engine = DeductionEngine(project_id, project.root_path)
    await engine.load_from_project(chapter_ref)

    # Check completeness
    missing = []
    if not engine.characters:
        missing.append("没有加载到角色，请先创建角色设定")
    if not engine.stage.terrain:
        missing.append("舞台场景未指定，请在章纲或世界设定中补充场景描述")

    _active[engine.deduction_id] = engine

    return {
        "deduction_id": engine.deduction_id,
        "stage": {
            "terrain": engine.stage.terrain,
            "time": engine.stage.time,
            "weather": engine.stage.weather,
        },
        "characters": list(engine.characters.keys()),
        "missing": missing,
    }


@router.post("/{deduction_id}/seed")
async def set_seed(
    deduction_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
):
    """Set the trigger seed for the deduction."""
    engine = _get_engine(deduction_id)
    seed_text = body.get("seed", "")
    if not seed_text:
        raise HTTPException(400, "seed is required")
    engine.set_seed(seed_text)
    return {"ok": True, "seed": seed_text}


@router.post("/{deduction_id}/round")
async def run_round(
    deduction_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _: bool = Depends(require_ai_access),
):
    """Execute one deduction round."""
    engine = _get_engine(deduction_id)
    # key-crypto-selfcontained：路径无 project_id（在会话引擎内）——取值后复用
    # 判定核心，模型链路未就绪（含 Key 死文）503 拦截，不再静默空回合
    await ensure_novel_model_ready(db, user["id"], engine.project_id)
    result = await engine.run_round()
    return _round_to_dict(result)


@router.post("/{deduction_id}/rewind/{round_num}")
async def rewind(
    deduction_id: str,
    round_num: int,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
):
    """Rewind to a previous round checkpoint."""
    engine = _get_engine(deduction_id)
    try:
        engine.rewind_to(round_num)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "current_round": engine.round}


@router.post("/{deduction_id}/adjust")
async def adjust(
    deduction_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
):
    """Author adjusts character or stage state."""
    engine = _get_engine(deduction_id)
    adjustments = body.get("adjustments", [])
    for adj in adjustments:
        target = adj.get("target", "")
        field = adj.get("field", "")
        value = adj.get("value", "")
        if target in engine.characters and hasattr(engine.characters[target], field):
            setattr(engine.characters[target], field, value)
    return {"ok": True}


@router.post("/{deduction_id}/stop")
async def stop_deduction(
    deduction_id: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
):
    """Stop deduction and return summary."""
    engine = _get_engine(deduction_id)
    summary = {
        "deduction_id": deduction_id,
        "total_rounds": engine.round,
        "seed": engine.seed,
        "events": engine.stage.events,
        "character_count": len(engine.characters),
        "history": [_round_to_dict(r) for r in engine.history],
    }
    _active.pop(deduction_id, None)
    return summary


@router.get("/{deduction_id}")
async def get_deduction(
    deduction_id: str,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
):
    """Get current deduction state."""
    engine = _get_engine(deduction_id)
    return engine.to_dict()


def _round_to_dict(r) -> dict:
    return {
        "round": r.round_number,
        "stage": {
            "terrain": r.stage.terrain,
            "time": r.stage.time,
            "weather": r.stage.weather,
            "events": r.events,
        },
        "decisions": [
            {
                "character_id": d.character_id,
                "log": {
                    "see": d.log.see,
                    "hear": d.log.hear,
                    "sense": d.log.sense,
                    "understanding": d.log.understanding,
                    "values_checked": d.log.values_checked,
                    "ability_assessment": d.log.ability_assessment,
                    "emotion": d.log.emotion,
                    "urgency": d.log.urgency,
                    "decision_process": d.log.decision_process,
                    "action_type": d.log.action_type,
                    "action_description": d.log.action_description,
                    "inner_monologue": d.log.inner_monologue,
                    "action_impact": d.log.action_impact,
                },
            }
            for d in r.decisions
        ],
        "characters": {
            cid: {
                "position": c.position,
                "stamina": c.stamina,
                "emotion": c.emotion,
                "urgency": c.urgency,
                "knowledge": c.knowledge,
            }
            for cid, c in r.characters.items()
        },
    }
