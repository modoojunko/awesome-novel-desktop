"""AI-assisted settings generation endpoints.

分层（D11）：本模块属**业务层**——只组上下文、调客户端层、落结果、记计量；
不构造连接、不自判会员/模型（门控在 dependency）。

路由顺序：`/ai/intro/{action}` **必须**注册在 `/ai/{stype}/{field}` 之前，
否则 `intro` 会被通用路由当成 `stype` 吞掉（→400）。

页面级参数（D12）：JSON 判定类 temperature ≤0.3、max_tokens ≥2048；
长文生成类（润色简介）temperature 0.7。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from filesystem.storage import get_storage
from genres.novel_genre_service import get_novel_genre
from novels.service import get_novel
from prompts import load as load_prompt

router = APIRouter(prefix="/api/novels/{project_id}/settings", tags=["settings-ai"])

# 支持按字段生成的设定类型（anti-ai 除外）
FIELD_GENERATABLE = {"world", "style", "hooks", "characters", "genre"}

# 题材五行字段（01 口味胶囊不走 AI；promise_note 不单独成行，随 core_promise 出参）
GENRE_FIELDS = ("core_promise", "forbidden_list", "cost_ratio", "battlefield", "track")

INTRO_ACTIONS = ("introspect", "fill", "polish")

# 六段名 / 禁忌三元（体检归一化白名单；与前端 lib/introTemplate.ts 逐字一致）
INTRO_SEGMENT_NAMES = (
    "主角身份",
    "本来的生活",
    "突发状况",
    "必须面对的矛盾",
    "不做的后果",
    "做了的可能结局",
)
INTRO_TABOO_RULES = ("设定集腔", "作者自白", "剧透")

# 候选源（归一化：模型给出 label 时映射回 tagId）
_GENRE_VOCAB_IDS = {
    "promise": [
        "promise:comeback",
        "promise:mind-game",
        "promise:sweet",
        "promise:survival",
        "promise:scheme",
    ],
    "forbidden": [
        "forbidden:no-deus-ex-machina",
        "forbidden:no-free-powerup",
        "forbidden:no-villain-idiot",
        "forbidden:no-foresight",
        "forbidden:no-gratuitous-angst",
        "forbidden:no-third-wheel",
    ],
    "battlefield": [
        "battlefield:resources",
        "battlefield:status",
        "battlefield:truth",
        "battlefield:affection",
        "battlefield:infrastructure",
        "battlefield:external-enemy",
    ],
}


# ── 解析助手 ───────────────────────────────────────────────────────────────


def _strip_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0]
    return cleaned.strip()


def _parse_json(text: str, what: str):
    """模型输出 → JSON；非法 JSON 抛 502（可重试，不拦确认）。"""
    try:
        return json.loads(_strip_fences(text))
    except ValueError as e:
        raise HTTPException(502, f"{what}返回的不是合法 JSON，可重试：{e}") from e


def _clamp_str(v, limit: int) -> str:
    return str(v or "").strip()[:limit]


def _vocab_id(kind: str, raw: str) -> str | None:
    """把模型给的候选（id 或裸 slug）映射回 tagId。"""
    raw = (raw or "").strip()
    if not raw:
        return None
    for vid in _GENRE_VOCAB_IDS[kind]:
        slug = vid.split(":", 1)[1]
        if raw in (vid, slug):
            return vid
    return None


def _normalize_vocab_list(kind: str, data, label_limit: int) -> list[dict]:
    """[{tagId|text}] 归一化：命中候选 → tagId；否则落 custom text；丢弃空项。"""
    if not isinstance(data, list):
        return []
    out: list[dict] = []
    for item in data:
        if isinstance(item, str):
            vid = _vocab_id(kind, item)
            if vid:
                out.append({"tagId": vid})
            else:
                text = _clamp_str(item, label_limit)
                if text:
                    out.append({"text": text})
            continue
        if not isinstance(item, dict):
            continue
        raw = item.get("tagId") or item.get("id") or item.get("value") or item.get("text")
        vid = _vocab_id(kind, str(raw or ""))
        if vid:
            out.append({"tagId": vid})
            continue
        text = _clamp_str(item.get("text") or raw, label_limit)
        if text:
            out.append({"text": text})
    return out


def _normalize_genre_value(field: str, data):
    """题材字段强类型出参（D18 契约）。"""
    if field == "core_promise":
        if isinstance(data, dict):
            value = _clamp_str(data.get("value") or data.get("core_promise"), 60)
            note = _clamp_str(data.get("note") or data.get("promise_note"), 200)
        else:
            value, note = _clamp_str(data, 60), ""
        return {"value": value, "note": note}
    if field == "forbidden_list":
        return _normalize_vocab_list("forbidden", data, 100)
    if field == "battlefield":
        return _normalize_vocab_list("battlefield", data, 20)
    if field == "cost_ratio":
        raw = data.get("value") if isinstance(data, dict) else data
        try:
            n = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(502, "吃苦指数返回的不是数字，可重试") from None
        return max(1, min(10, n))
    if field == "track":
        raw = data.get("value") if isinstance(data, dict) else data
        return _clamp_str(raw, 300)
    raise HTTPException(400, f"未知题材字段：{field}")


def _normalize_introspect(data) -> dict:
    """体检响应归一化兜底（弱模型下 status/verdict/name/rule 全量 clamp）。"""
    if not isinstance(data, dict):
        raise HTTPException(502, "体检返回结构不对，可重试")

    seg_by_name = {}
    for item in data.get("six_segments") or []:
        if isinstance(item, dict) and item.get("name"):
            seg_by_name[str(item["name"]).strip()] = item
    segments = []
    for name in INTRO_SEGMENT_NAMES:
        item = seg_by_name.get(name, {})
        status = "ok" if str(item.get("status", "")).strip() == "ok" else "missing"
        segments.append(
            {
                "name": name,
                "status": status,
                "excerpt": _clamp_str(item.get("excerpt"), 120),
                "note": _clamp_str(item.get("note"), 120),
            }
        )

    hits = []
    taboo = data.get("taboo") or {}
    for hit in (taboo.get("hits") if isinstance(taboo, dict) else []) or []:
        if not isinstance(hit, dict):
            continue
        rule = str(hit.get("rule", "")).strip()
        if rule not in INTRO_TABOO_RULES:
            rule = next((r for r in INTRO_TABOO_RULES if r and r in rule), "未知")
        excerpts = [
            _clamp_str(x, 120) for x in (hit.get("excerpts") or []) if str(x).strip()
        ]
        hits.append({"rule": rule, "excerpts": excerpts[:3]})

    verdict = str(data.get("verdict", "")).strip()
    if verdict not in ("strong", "ok", "weak"):
        verdict = "ok" if not hits else "weak"
    return {"six_segments": segments, "taboo": {"hits": hits}, "verdict": verdict}


# ── 简介 AI（必须注册在通用字段路由之前）────────────────────────────────


@router.post("/ai/intro/{action}")
async def intro_ai(
    project_id: str,
    action: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """简介三能力：introspect（体检）/ fill（补缺失）/ polish（润色）。

    输入一律用 `body.content`（前端当前编辑草稿）+ `body.title`，**不读 story.yaml 旧文**。
    """
    if action not in INTRO_ACTIONS:
        raise HTTPException(400, f"不支持的简介 AI 动作：{action}")

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    title = _clamp_str(body.get("title"), 100)
    content = str(body.get("content") or "")
    if not content.strip():
        raise HTTPException(400, "简介为空，先写两句再让 AI 处理")

    template = load_prompt(f"settings_intro_{action}")
    if action == "fill":
        missing = [
            str(x).strip() for x in (body.get("missing_segments") or []) if str(x).strip()
        ]
        formatted = template.format(
            title=title,
            content=content,
            missing_segments="、".join(missing) or "（未指定，按六段自查）",
        )
    else:
        formatted = template.format(title=title, content=content)

    client = await get_ai_client_for_novel(project_id)
    # 页面级参数（D12）：体检/补缺失＝JSON 判定类；润色＝长文生成类
    temperature, max_tokens = (0.7, 2048) if action == "polish" else (0.3, 2048)

    usage: dict = {}
    try:
        text = await client.chat(
            model="haiku",
            system="你是小说简介编辑。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": formatted}],
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
            usage=usage,
        )
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    data = _parse_json(text, "简介 AI")

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        api_config_id=project.ai_config_id,
        operation=f"settings_intro_{action}",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )

    if action == "introspect":
        return _normalize_introspect(data)
    if action == "fill":
        missing_out = []
        for item in (data.get("missing") if isinstance(data, dict) else []) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            candidate = _clamp_str(item.get("candidate") or item.get("text"), 200)
            if name and candidate:
                missing_out.append({"name": name, "candidate": candidate})
        return {"missing": missing_out, "act": "insert"}

    if not isinstance(data, dict):
        raise HTTPException(502, "润色返回结构不对，可重试")
    polished = _clamp_str(data.get("polished"), 500)
    if not polished:
        raise HTTPException(502, "润色没给出结果，可重试")
    return {
        "original": _clamp_str(data.get("original"), 500) or content[:500],
        "polished": polished,
        "act": "replace",
    }


# ── 按字段生成（world/style/hooks/characters/genre）──────────────────────


@router.post("/ai/{stype}/{field}")
async def generate_field(
    project_id: str,
    stype: str,
    field: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """Generate a single settings field."""
    if stype not in FIELD_GENERATABLE:
        raise HTTPException(400, f"Field generation not supported for: {stype}")

    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    premise = story.get("synopsis", "")
    if not premise:
        raise HTTPException(400, "No story premise found.")

    # prompt 命名：仅 genre 特判 field 级，其余仍走 settings_{stype}
    if stype == "genre":
        if field not in GENRE_FIELDS:
            raise HTTPException(400, f"题材不支持该字段生成：{field}")
        prompt_name = f"settings_genre_{field}"
    else:
        prompt_name = f"settings_{stype}"

    context = body.get("context", {}) or {}
    if stype == "genre":
        g = await get_novel_genre(db, project.id)
        forbidden_labels = [
            item.get("tagId") or item.get("text") for item in g["forbidden_list"]
        ]
        formatted_prompt = load_prompt(prompt_name).format(
            title=_clamp_str(body.get("title"), 100),
            synopsis=premise,
            current=json.dumps(context.get("current", ""), ensure_ascii=False),
            core_promise=g["core_promise"] or context.get("core_promise", ""),
            forbidden_list=json.dumps(forbidden_labels, ensure_ascii=False),
            cost_ratio=g["cost_ratio"] if g["cost_ratio"] is not None else "",
            battlefield=json.dumps(g["battlefield"], ensure_ascii=False),
        )
    else:
        formatted_prompt = load_prompt(prompt_name).format(
            premise=premise, context=json.dumps(context, ensure_ascii=False)
        )

    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await client.chat(
            model="haiku",
            system="你是小说设定专家。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": formatted_prompt}],
            max_tokens=2048,
            temperature=0.3,
            json_mode=True,
            usage=usage,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    value = _parse_json(text, "设定 AI")
    if stype == "genre":
        value = _normalize_genre_value(field, value)

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        api_config_id=project.ai_config_id,
        operation=f"settings_{stype}_{field}",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    return {"value": value}
