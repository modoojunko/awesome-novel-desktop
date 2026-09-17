"""本章文风影子（chapter-style-shadow，拍板③记章节档案）：

全书文风基线（style-quant 六行）只读；本章只存覆盖行（chapters.style_shadow
JSON）。AI 建议端点读基线＋本章章纲，产出「每行 本章取值＋理由」的建议，
不落库——前端逐条采纳后经 PUT /chapters/{ref} 写入 style_shadow。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_configs.usage import record_usage
from auth_local.deps import get_current_user, require_ai_access, require_novel_model
from db import get_db
from filesystem.paths import STYLE_QUANT_PATH
from filesystem.storage import get_storage
from models.chapter import Chapter
from models.project import Novel
from settings.style_quant_model import BASELINE_ROWS, quant_doc

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/style-shadow",
    tags=["style-shadow"],
)


def _baseline_lines(doc: dict) -> list[dict]:
    """六行基线 → [{row, label, value, tolerance, locked}]（行序固定）。"""
    baseline = doc.get("baseline") if isinstance(doc.get("baseline"), dict) else {}
    out = []
    for row, label in BASELINE_ROWS:
        item = baseline.get(row) if isinstance(baseline.get(row), dict) else {}
        out.append({
            "row": row,
            "label": label,
            "value": str(item.get("value", "") or ""),
            "tolerance": item.get("tolerance"),
            "locked": bool(item.get("locked")),
        })
    return out


async def _load_project_chapter(db: AsyncSession, project_id: str, chapter_ref: str):
    project = await db.get(Novel, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    ch = (
        await db.scalars(
            select(Chapter).where(Chapter.project_id == project_id, Chapter.ref == chapter_ref)
        )
    ).first()
    if ch is None:
        raise HTTPException(404, "Chapter not found")
    return project, ch


def _read_shadow(ch: Chapter) -> dict:
    import json as _json

    try:
        shadow = _json.loads(ch.style_shadow or "{}")
    except Exception:  # noqa: BLE001 — 影子损坏按空处理
        shadow = {}
    return shadow if isinstance(shadow, dict) else {}


@router.get("/baseline")
async def get_style_baseline(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """全书基线（只读）＋ 本章影子（现状），供文风页签一次拉取。"""
    _project, ch = await _load_project_chapter(db, project_id, chapter_ref)
    doc = quant_doc(await get_storage().read_yaml(_project.root_path, STYLE_QUANT_PATH) or {})
    return {
        "baseline": _baseline_lines(doc),
        "confidence": doc.get("confidence", 0),
        "portrait": doc.get("portrait", ""),
        "shadow": _read_shadow(ch),
    }


@router.put("")
async def put_style_shadow(
    project_id: str,
    chapter_ref: str,
    body: dict,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写本章影子：body {rows: {dim: {value, reason}}}（专用小端点，避免
    PUT /chapters/{ref} 全对象替换的误覆盖）。"""
    _project, ch = await _load_project_chapter(db, project_id, chapter_ref)
    rows = body.get("rows") if isinstance(body.get("rows"), dict) else {}
    clean: dict[str, dict] = {}
    for dim, item in rows.items():
        if isinstance(item, dict) and (
            str(item.get("value", "")).strip() or str(item.get("reason", "")).strip()
        ):
            clean[str(dim)] = {
                "value": str(item.get("value", "")),
                "reason": str(item.get("reason", "")),
            }
    import json as _json

    ch.style_shadow = _json.dumps(clean, ensure_ascii=False)
    db.add(ch)
    await db.commit()
    return {"ok": True, "shadow": clean}


@router.post("/suggest")
async def suggest_style_shadow(
    project_id: str,
    chapter_ref: str,
    user: dict = Depends(get_current_user),
    _ai: None = Depends(require_ai_access),
    _m: None = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """AI 建议本章文风调整：读基线＋本章章纲 → 每行建议取值＋理由（不落库）。

    PRO 门控沿 require_ai_access（免费档 403/409 由门控层决定）；建议不落库，
    采纳经 PUT /chapters/{ref} 写 style_shadow。
    """
    project, _ch = await _load_project_chapter(db, project_id, chapter_ref)
    doc = quant_doc(await get_storage().read_yaml(project.root_path, STYLE_QUANT_PATH) or {})
    baseline = _baseline_lines(doc)
    if doc.get("confidence", 0) <= 0 or not any(b["value"] for b in baseline):
        raise HTTPException(409, "本书还没有蒸馏出文风基线——请先在设定 · 文风里完成蒸馏")

    from chapters.store import load_chapter

    chapter = await load_chapter(project.root_path, chapter_ref)
    if not chapter:
        raise HTTPException(404, "Chapter not found")
    outline = chapter.get("outline") or {}
    summary = str(outline.get("summary") or "")
    key_points = "；".join(str(k) for k in outline.get("key_points") or [])

    lines = [
        f"- {b['label']}（{b['row']}）：当前「{b['value']}」"
        + (f"（±{b['tolerance']}）" if b.get("tolerance") else "")
        for b in baseline
    ]
    prompt = (
        "你是文风教练。下面是这本书的文风基线（六行）和本章章纲。"
        "请判断本章是否值得在个别行上偏离基线（例如动作章把句子压得更短）。"
        "只对确实值得偏离的行给出建议，每行=「行名：本章取值｜理由一句话」。"
        "没有偏离必要的行不要输出。最多 3 行。\n\n"
        "文风基线：\n" + "\n".join(lines) + "\n\n"
        f"本章章纲：\n概要：{summary}\n关键事件：{key_points}\n\n"
        'JSON 数组输出，形如 {"suggestions": [{"row": "syntax", "value": "更短的句子", "reason": "打斗章节奏需要"}]}'
    )

    from ai_client import get_ai_client_for_novel

    try:
        client = await get_ai_client_for_novel(project_id)
    except Exception:  # noqa: BLE001 — 模型未就绪：调用未发生，不记账
        client = None
    if client is None:
        raise HTTPException(409, "本书 AI 模型未就绪——请先到设定 · 模型配置里选好本书模型")


    usage: dict = {}
    text = await client.chat(
        model="haiku", system="", messages=[{"role": "user", "content": prompt}],
        max_tokens=500, usage=usage,
    )
    await record_usage(
        db,
        user_id=project.user_id,
        project_id=project.id,
        chapter_id=chapter_ref,
        operation="style_shadow_suggest",
        model=usage.get("model", "haiku"),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )

    data = _parse_suggestions(text)
    return {"ok": True, "suggestions": data}


def _parse_suggestions(text: str) -> list[dict]:
    import json as _json

    if not text:
        return []
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = _json.loads(text[start : end + 1])
    except Exception:  # noqa: BLE001
        return []
    items = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    valid_rows = {row for row, _label in BASELINE_ROWS}
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = str(item.get("row", "")).strip()
        value = str(item.get("value", "")).strip()
        reason = str(item.get("reason", "")).strip()
        if row in valid_rows and value:
            out.append({"row": row, "value": value, "reason": reason[:200]})
    return out


