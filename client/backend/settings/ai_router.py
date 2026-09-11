"""AI-assisted settings generation endpoints.

分层（D11）：本模块属**业务层**——只组上下文、调客户端层、落结果、记计量；
不构造连接、不自判会员/模型（门控在 dependency）。

路由顺序：`/ai/intro/{action}` **必须**注册在 `/ai/{stype}/{field}` 之前，
否则 `intro` 会被通用路由当成 `stype` 吞掉（→400）。

页面级参数（D12）：JSON 判定类 temperature ≤0.3、max_tokens ≥2048；
长文生成类（润色简介）temperature 0.7。
"""

import json
import re

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
FIELD_GENERATABLE = {"style", "hooks", "characters", "genre"}

# 题材五行字段（01 口味胶囊不走 AI；promise_note 不单独成行，随 core_promise 出参）
GENRE_FIELDS = ("core_promise", "forbidden_list", "cost_ratio", "battlefield")

INTRO_ACTIONS = ("introspect", "fill", "polish")

# prompt 名＝字面映射（键为已校验的枚举值）——避免把请求参数拼进文件路径
_INTRO_PROMPTS = {
    "introspect": "settings_intro_introspect",
    "fill": "settings_intro_fill",
    "polish": "settings_intro_polish",
}
_GENRE_PROMPTS = {
    "core_promise": "settings_genre_core_promise",
    "forbidden_list": "settings_genre_forbidden_list",
    "cost_ratio": "settings_genre_cost_ratio",
    "battlefield": "settings_genre_battlefield",
}
_STYPE_PROMPTS = {
    "style": "settings_style",
    "hooks": "settings_hooks",
    "characters": "settings_characters",
}

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


# 判定类调用的预算：思考型模型会把预算花在推理上，2048 偶发「无文本输出」，
# 提到 4096 给输出留量（design D12：JSON 判定类 max_tokens 足量）。
_JUDGE_MAX_TOKENS = 4096


async def _judge_chat(client, **kwargs):
    """判定类调用：空文本输出自动重试一次，其余异常原样抛。

    供应商偶发「只回思考不回文本」时，重试一次基本能拿到结果——
    比直接把 502 甩给用户好。

    记账：**每次尝试的 token 都累加**——首次失败那次同样烧了钱，
    不能被重试覆盖（旧实现只记最后一次，用量偏低）。
    """
    caller_usage = kwargs.pop("usage", None)
    total_in = 0
    total_out = 0
    last_err: Exception | None = None
    for attempt in range(2):
        attempt_usage: dict = {}
        try:
            text = await client.chat(
                max_tokens=_JUDGE_MAX_TOKENS, usage=attempt_usage, **kwargs
            )
        except ValueError as e:
            total_in += attempt_usage.get("tokens_in", 0)
            total_out += attempt_usage.get("tokens_out", 0)
            if "模型未返回文本内容" not in str(e):
                _flush_usage(caller_usage, total_in, total_out)
                raise
            last_err = e
            if attempt == 0:
                continue
            break
        total_in += attempt_usage.get("tokens_in", 0)
        total_out += attempt_usage.get("tokens_out", 0)
        _flush_usage(caller_usage, total_in, total_out)
        return text
    _flush_usage(caller_usage, total_in, total_out)
    raise last_err  # type: ignore[misc]


def _flush_usage(usage: dict | None, tokens_in: int, tokens_out: int) -> None:
    """把累计用量写回调用方的 usage dict（None 则忽略）。"""
    if usage is not None:
        usage["tokens_in"] = tokens_in
        usage["tokens_out"] = tokens_out


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


def _slug_words(text: str) -> set[str]:
    """把 slug 切成词集（并做单复数归一：resource/resources 视为同词）。"""
    words = {w for w in re.split(r"[^a-z0-9]+", text) if w}
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words}


def _vocab_looks_like_slug(raw: str) -> bool:
    """像机器标识（`kind:slug` / 裸 slug）而不是给人看的文本。

    判据：不含中日韩字符且只由 `[a-z0-9_:-]` 组成。中文自定义禁项（「禁穿越」）不受影响。
    """
    s = (raw or "").strip()
    if not s or re.search(r"[\u3400-\u9fff]", s):
        return False
    return bool(re.fullmatch(r"[a-z0-9_:-]+", s.lower()))


def _vocab_id(kind: str, raw: str) -> str | None:
    """把模型给的候选（id / 裸 slug / 写岔的 id）映射回 tagId。

    精确命中优先；再做一次**近似匹配**——模型常把 id 写岔，
    例如把 `forbidden:no-deus-ex-machina` 写成 `forbidden:no-deus-machina`
    （实测发生过：那条被当"自定义文本"存了下来，界面就显示成英文 slug）。
    近似规则保守：去掉非字母数字后互相包含（且长度 ≥8），且**只认唯一命中**。
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    ids = _GENRE_VOCAB_IDS[kind]
    for vid in ids:
        slug = vid.split(":", 1)[1]
        if raw in (vid, slug):
            return vid
    # 近似＝按「词」比：模型少写/多写一个词（no-deus-machina vs no-deus-ex-machina）
    raw_words = _slug_words(raw.lower().removeprefix(f"{kind}:"))
    if not raw_words:
        return None
    hits = []
    for vid in ids:
        known = _slug_words(vid.split(":", 1)[1].lower())
        if len(raw_words) == 1 or len(known) == 1:
            # 单词情形只认「归一后完全相等」（resource ↔ resources），不放宽
            if known == raw_words:
                hits.append(vid)
            continue
        if raw_words <= known or known <= raw_words:
            hits.append(vid)
    return hits[0] if len(hits) == 1 else None


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
                if text and not _vocab_looks_like_slug(text):
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
        # 落自定义文本前挡一道：像机器标识（查不到的 id）不落库——
        # 存下来只会在界面上显示英文 slug，既不是有效候选也不是人类可读的规则。
        if text and not _vocab_looks_like_slug(text):
            out.append({"text": text})
    return out


def _theme_anchor(theme: str, sub: str) -> tuple[str, str]:
    """题材目录里的「解读」与「案例」——喂给 AI 当风格锚。

    目录（`genres/theme_catalog.py`）每条都带 desc/example，是最现成的 few-shot：
    同题材的读者习惯、案例参照直接进提示词，模型就不必靠书名猜题材。
    子类案例优先；只选大类时取前两个子类的案例拼一串。
    """
    from genres.theme_catalog import sub_type_entry, theme_entry

    entry = theme_entry(theme) if theme else None
    if entry is None:
        return "", ""
    sub_entry = sub_type_entry(theme, sub) if sub else None
    if sub_entry is not None:
        return sub_entry["desc"], sub_entry["example"]
    subs = entry["sub_types"][:2]
    return entry["desc"], "；".join(s["example"] for s in subs)


def _as_bool(value) -> bool:
    """宽松真值判定：true/1/"true"/"1"/"yes" → True（其余 False）。"""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "on"}


def _normalize_genre_value(field: str, data):
    """题材字段强类型出参（D18 契约）。"""
    if field == "core_promise":
        # 多看点模式（{multi_point}=true）：模型返回数组，最多保留 3 条独立看点。
        # 逐项做同样的长度校验（value ≤60 / note ≤200），**两项全空**的条目丢弃；
        # 全部无效则按 502 处理（与单条同口径，可重试）。
        if isinstance(data, list):
            points = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                value = _clamp_str(item.get("value") or item.get("core_promise"), 60)
                note = _clamp_str(item.get("note") or item.get("promise_note"), 200)
                if value or note:
                    points.append({"value": value, "note": note})
                if len(points) >= 3:
                    break
            if not points:
                raise HTTPException(502, "多看点没给出有效内容，可重试")
            return points
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

    out: dict = {"six_segments": segments, "taboo": {"hits": hits}, "verdict": verdict}

    # 标题对照（D21）：fit 三值白名单；**未给或非法 → 整行不下发**（不得补 ok 造假绿）
    tc = data.get("title_check")
    if isinstance(tc, dict):
        fit = str(tc.get("fit", "")).strip()
        if fit in ("ok", "mismatch", "generic"):
            suggestions = [
                _clamp_str(x, 16) for x in (tc.get("suggestions") or []) if str(x).strip()
            ][:3]
            out["title_check"] = {
                "fit": fit,
                "note": _clamp_str(tc.get("note"), 120),
                "suggestions": suggestions if fit != "ok" else [],
            }
    return out


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

    template = load_prompt(_INTRO_PROMPTS[action])
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
    temperature = 0.7 if action == "polish" else 0.3

    usage: dict = {}
    try:
        text = await _judge_chat(
            client,
            model="haiku",
            system="你是小说简介编辑。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": formatted}],
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


# ── 世界设定 v2：通用按主题起草 / 一致性体检 / lore-suggest ────────────────
# 注册在 /ai/{stype}/{field} 通配之前（intro 先例：通配会把 world 当 stype 吞掉）。
# 设计：不硬编码字段列表——AI 起草按主题名动态生成，任何世界要素都能补。

_CHECK_STATUS = ("ok", "warn", "miss")


def _world_theme(story: dict) -> tuple[str, str, str]:
    """题材锚（运行时读 story.yaml，不用前端快照）：标签/描述/示例。"""
    theme_name = (story.get("genre") or "").strip()
    theme_sub = (story.get("sub_genre") or "").strip()
    theme_label = f"{theme_name}（{theme_sub}）" if theme_sub else theme_name
    theme_desc, theme_example = _theme_anchor(theme_name, theme_sub)
    return theme_label, theme_desc, theme_example


def _world_context(project, story: dict) -> dict:
    """世界 AI 共享上下文：书名/简介/题材锚/已有世界设定摘要。"""
    from settings.world_model import world_summary_text

    world_raw = get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
    theme_label, theme_desc, _ = _world_theme(story)
    return {
        "title": _clamp_str(getattr(project, "name", ""), 100),
        "synopsis": _clamp_str(story.get("synopsis"), 600),
        "theme": theme_label,
        "theme_desc": theme_desc,
        "world": world_summary_text(world_raw, 1200) or "（世界设定还空着）",
    }


# 起草输出形状由调用方声明（前端知道要落哪个格）：text=一段话 / kv=名目条目 / faction=势力行
_DRAFT_SHAPES = ("text", "kv", "faction")
_DRAFT_SHAPE_LINE = {
    "text": "一段话即可，作家确认后会写入对应格",
    "kv": "分条给出（3-6 条），每条一句话、具体可判，不要空话",
    "faction": "列出主要势力（2-3 个），每个注明想要什么、与谁敌友",
}
_DRAFT_FORMAT_LINE = {
    "text": '{{"value": "一段话内容"}}',
    "kv": '{{"value": [{{"key": "名目（≤10字）", "value": "一句话（≤80字）"}}]}}',
    "faction": '{{"value": [{{"name": "势力名（≤10字）", "note": "想要什么、与谁敌友"}}]}}',
}


def _normalize_draft_value(shape: str, raw) -> object:
    """按形状归一 AI 返回的 value：text 出一段话，kv/faction 出条目数组（空项丢弃）。"""
    if shape == "text":
        return _clamp_str(raw, 500)
    rows = raw if isinstance(raw, list) else []
    out: list = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if shape == "kv":
            key = _clamp_str(row.get("key"), 20) or _clamp_str(row.get("value"), 10)
            val = _clamp_str(row.get("value"), 200)
            if key and val:
                out.append({"key": key, "value": val})
        else:
            name = _clamp_str(row.get("name"), 20)
            note = _clamp_str(row.get("note"), 200)
            if name:
                out.append({"name": name, "note": note})
    return out[: 10 if shape == "kv" else 6]


@router.post("/ai/world/draft")
async def draft_world_topic(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """通用按主题起草：topic 是任意世界要素名（力量体系/代价/历史/势力/铁律……）。

    后端不枚举合法主题——只要作家或体检觉得需要，就能 AI 起草。
    shape 声明落格形状：text（一段话）/ kv（名目条目）/ faction（势力行）。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    topic = _clamp_str(body.get("topic"), 60)
    if not topic:
        raise HTTPException(400, "缺少主题（topic）")
    shape = str(body.get("shape") or "text").strip()
    if shape not in _DRAFT_SHAPES:
        raise HTTPException(400, "shape 仅支持 text/kv/faction")

    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    ctx = _world_context(project, story)

    prompt = load_prompt("world_draft_topic").format(
        topic=topic,
        title=ctx["title"],
        synopsis=ctx["synopsis"],
        theme=ctx["theme"],
        theme_desc=ctx["theme_desc"],
        world=ctx["world"],
        shape_line=_DRAFT_SHAPE_LINE[shape],
        format_line=_DRAFT_FORMAT_LINE[shape],
    )

    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await _judge_chat(
            client,
            model="haiku",
            system="你是小说设定专家。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            json_mode=True,
            usage=usage,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    data = _parse_json(text, "世界起草")
    value = _normalize_draft_value(shape, data.get("value") if isinstance(data, dict) else None)
    if not value:
        raise HTTPException(502, "AI 没给出结果，可重试")

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        api_config_id=project.ai_config_id,
        operation=f"settings_world_draft_{topic[:20]}",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    return {"value": value, "topic": topic}


@router.post("/ai/world/check")
async def check_world_consistency(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """一致性体检：简介 × 题材 × 世界三方对照，逐项三态，只提醒不拦确认。

    降级（D7）：简介/题材缺失不 400——涉及行置 miss 并给补填出口（degraded 标记）。
    """
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    from settings.world_model import (
        CHECK_ITEMS_POWER,
        CHECK_ITEMS_REAL,
        normalize_world,
        world_summary_text,
    )

    world_raw = await get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
    world = normalize_world(world_raw)
    no_power = bool(world.get("no_power"))
    item_names = list(CHECK_ITEMS_REAL if no_power else CHECK_ITEMS_POWER)

    synopsis = str(story.get("synopsis", ""))
    theme_label, _, _ = _world_theme(story)
    synopsis_missing = not synopsis.strip()
    theme_missing = not theme_label

    prompt = load_prompt("world_check").format(
        synopsis=_clamp_str(synopsis, 600) or "（未填写）",
        theme=theme_label or "（未确认）",
        world=world_summary_text(world_raw, 1200) or "（未填写）",
        items=" / ".join(item_names),
    )

    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await _judge_chat(
            client,
            model="haiku",
            system="你是小说设定一致性审校。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            json_mode=True,
            usage=usage,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"体检失败，可重试：{e!s}") from e

    data = _parse_json(text, "一致性体检")
    ai_items: dict = {}
    raw_items = (data.get("items") if isinstance(data, dict) else []) or []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = _clamp_str(item.get("name"), 40)
        status = str(item.get("status", "")).strip()
        if name and name not in ai_items and status in _CHECK_STATUS:
            ai_items[name] = {"name": name, "status": status,
                              "note": _clamp_str(item.get("note"), 120)}

    items_out = []
    for name in item_names:
        items_out.append(ai_items.get(name) or
                         {"name": name, "status": "miss", "note": "AI 未给出该项，可重跑体检"})

    degraded = False
    if synopsis_missing:
        degraded = True
        for row in items_out:
            if "简介" in row["name"]:
                row.update(status="miss", note="简介还没写——先去补简介，再重新体检")
    if theme_missing:
        degraded = True
        for row in items_out:
            if "题材" in row["name"]:
                row.update(status="miss", note="题材还没确认——先去题材页确认，再重新体检")

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        api_config_id=project.ai_config_id,
        operation="settings_world_check",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    verdict = _clamp_str(data.get("verdict"), 120) if isinstance(data, dict) else ""
    return {"items": items_out, "degraded": degraded, "verdict": verdict}


@router.post("/ai/world/lore-suggest")
async def lore_suggest_world(
    project_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """归档章节的世界要素建议（stateless 不落库，采纳走 /settings/world/lore-apply）。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    chapter_ref = _clamp_str(body.get("chapter_ref"), 40)
    if not chapter_ref:
        raise HTTPException(400, "缺少章节引用（chapter_ref）")

    from settings.world_model import world_summary_text
    from workflow.engine import load_chapter

    chapter = await load_chapter(project.root_path, chapter_ref)
    chapter_text = _clamp_str(
        body.get("text") or (chapter.get("content") if isinstance(chapter, dict) else ""),
        3000,
    )
    if not chapter_text.strip():
        raise HTTPException(400, "章节正文为空，无法提取世界要素")

    world_raw = await get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
    prompt = load_prompt("world_lore_suggest").format(
        chapter=chapter_text,
        world=world_summary_text(world_raw, 1200) or "（世界设定还空着）",
    )

    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await _judge_chat(
            client,
            model="haiku",
            system="你是小说世界设定管理员。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            json_mode=True,
            usage=usage,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    data = _parse_json(text, "世界要素")
    _SET_WHITELIST = ("history", "extra", "factions", "constraints")
    suggestions = []
    for item in (data.get("suggestions") if isinstance(data, dict) else []) or []:
        if not isinstance(item, dict):
            continue
        set_name = str(item.get("set", "")).strip()
        key = _clamp_str(item.get("key"), 20)
        value = _clamp_str(item.get("value"), 200)
        if set_name in _SET_WHITELIST and key and value:
            suggestions.append({"key": key, "value": value, "set": set_name})
    suggestions = suggestions[:8]

    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        api_config_id=project.ai_config_id,
        operation="settings_world_lore_suggest",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    return {"suggestions": suggestions, "chapter_ref": chapter_ref}


# ── 按字段生成（world/style/hooks/characters/genre）──────────────────────# ── 按字段生成（world/style/hooks/characters/genre）──────────────────────


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
        prompt_name = _GENRE_PROMPTS[field]
    else:
        prompt_name = _STYPE_PROMPTS[stype]

    context = body.get("context", {}) or {}
    if stype == "genre":
        g = await get_novel_genre(db, project.id)
        forbidden_labels = [
            item.get("tagId") or item.get("text") for item in g["forbidden_list"]
        ]
        # ① 题材目录进提示词（用户 2026-09-10）：题材是「定了就不跑偏」的类型锁，
        #    AI 助手此前完全不知道本书是什么题材，产出只能靠书名硬猜。
        #    落 story.yaml 的 genre/sub_genre（与简介同族）→ 目录取解读与案例当风格锚。
        theme_name = (story.get("genre") or "").strip()
        theme_sub = (story.get("sub_genre") or "").strip()
        theme_label = f"{theme_name}（{theme_sub}）" if theme_sub else theme_name
        theme_desc, theme_example = _theme_anchor(theme_name, theme_sub)
        # ② 候选池动态渲染（不再在模板里手抄一遍——四处各存一份必然漂移）
        from genres.vocab_presets import VOCAB_PRESETS

        def _pool(kind: str) -> tuple[str, str]:
            """某类候选的「标签清单 / id 清单」——两处都动态渲染，模板不手抄。"""
            entries = [e for e in VOCAB_PRESETS if e["kind"] == kind]
            return (
                " / ".join(e["label"] for e in entries),
                " / ".join(e["id"] for e in entries),
            )

        candidate_list, _promise_ids = _pool("promise")
        forbidden_candidates, forbidden_ids = _pool("forbidden")
        battlefield_candidates, battlefield_ids = _pool("battlefield")
        # ③ 多看点开关走 user 占位符（后端控制；旧调用不传＝false，完全兼容）
        multi_point = "true" if _as_bool(body.get("multi_point")) else "false"
        formatted_prompt = load_prompt(prompt_name).format(
            title=_clamp_str(body.get("title"), 100),
            synopsis=premise,
            current=json.dumps(context.get("current", ""), ensure_ascii=False),
            # 02：作者刚写的那句话优先（promise_note），短标签另给（current_value）
            current_note=_clamp_str(
                g["promise_note"] or context.get("promise_note"), 200
            ),
            current_value=_clamp_str(
                g["core_promise"] or context.get("current"), 60
            ),
            core_promise=g["core_promise"] or context.get("core_promise", ""),
            forbidden_list=json.dumps(forbidden_labels, ensure_ascii=False),
            cost_ratio=g["cost_ratio"] if g["cost_ratio"] is not None else "",
            battlefield=json.dumps(g["battlefield"], ensure_ascii=False),
            theme=theme_label,
            theme_desc=theme_desc,
            theme_example=theme_example,
            candidate_list=candidate_list,
            forbidden_candidates=forbidden_candidates,
            forbidden_ids=forbidden_ids,
            battlefield_candidates=battlefield_candidates,
            battlefield_ids=battlefield_ids,
            multi_point=multi_point,
        )
    else:
        formatted_prompt = load_prompt(prompt_name).format(
            premise=premise, context=json.dumps(context, ensure_ascii=False)
        )

    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await _judge_chat(
            client,
            model="haiku",
            system="你是小说设定专家。只输出 JSON，不要任何其他文字。",
            messages=[{"role": "user", "content": formatted_prompt}],
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
