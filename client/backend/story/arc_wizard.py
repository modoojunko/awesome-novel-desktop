"""AI 主线拆纲向导（story-arc-planning）。

四步端点：condense（浓缩一句话主线）/ ending（结局追问与矛盾指出）/
split（倒推分卷提案）/ audit（三问自查+结构归纳）。
每步只做「AI 干一活」返回结构化产出；落卡由前端 PUT /story/arc 完成，
续步推断由 GET /story/arc 的 next_step 提供（卡片数据为准，无独立会话）。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from novels.service import get_novel
from prompts import load as load_prompt

router = APIRouter(
    prefix="/api/novels/{project_id}/story/arc/wizard", tags=["story-arc"]
)

# step -> (提示词名, usage operation)
WIZARD_STEPS: dict[str, tuple[str, str]] = {
    "condense": ("arc_wizard_condense", "arc_wizard_condense"),
    "ending": ("arc_wizard_ending", "arc_wizard_ending"),
    "split": ("arc_wizard_split", "arc_wizard_split"),
    "audit": ("arc_wizard_audit", "arc_wizard_audit"),
}


@router.post("/{step}")
async def run_wizard_step(
    project_id: str,
    step: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """跑向导一步：入参 {input: 作者输入, arc: 卡片当前内容}，出参结构化 JSON。"""
    if step not in WIZARD_STEPS:
        raise HTTPException(400, f"Unknown wizard step: {step}")
    prompt_name, operation = WIZARD_STEPS[step]

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    author_input = str(body.get("input", "") or "").strip()
    if not author_input:
        raise HTTPException(400, "请先输入内容再让 AI 处理")

    prompt_template = load_prompt(prompt_name)
    formatted = prompt_template.format(
        input=author_input,
        arc=json.dumps(body.get("arc", {}), ensure_ascii=False),
    )
    client = await get_ai_client_for_novel(project.id)
    try:
        usage: dict = {}
        text = await client.chat(
            model=effective_model(project),
            system="你是长篇小说结构顾问。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": formatted}],
            max_tokens=1536,
            usage=usage,
        )
    except Exception as e:
        raise HTTPException(500, f"AI generation failed: {e!s}")

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        operation=operation,
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    try:
        value = json.loads(cleaned.strip())
    except ValueError as e:
        raise HTTPException(500, f"AI returned invalid JSON: {e}")
    return {"value": value}
