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
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_client import AITimeoutError, get_ai_client_for_novel
from ai_state import effective_model
from auth_local.deps import require_ai_access, require_novel_model
from auth_local.middleware import get_current_user
from db import get_db
from filesystem.storage import get_storage
from genres.novel_genre_service import get_novel_genre
from novels.service import get_novel
from prompts import load as load_prompt
from settings.hooks_model import (
    DESCRIPTION_MAX,
    HOOK_TYPE_KEYS,
    HOOK_TYPES,
    PAYOFF_NOTE_MAX,
    PRIORITY_LABELS,
    normalize_priority,
    priority_label,
    type_label,
)

router = APIRouter(prefix="/api/novels/{project_id}/settings", tags=["settings-ai"])

# 支持按字段生成的设定类型（anti-ai 除外；hooks 已随伏笔 AI 四能力退役——foreshadow-settings-v2 9.1）
FIELD_GENERATABLE = {"genre"}  # style 已升级三区 AI（/ai/style/{polish,check,fewshot-mine}）＋蒸馏

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
    不能被重试覆盖（旧实现只记最后一次，用量偏低）。回填走 finally：
    任何退出路径（成功 / 空文本重试耗尽 / 超时或其他异常）都把累计
    用量写回调用方，失败记账据此落库。
    """
    caller_usage = kwargs.pop("usage", None)
    total_in = 0
    total_out = 0
    last_err: Exception | None = None
    try:
        for attempt in range(2):
            attempt_usage: dict = {}
            try:
                text = await client.chat(
                    max_tokens=_JUDGE_MAX_TOKENS, usage=attempt_usage, **kwargs
                )
            except ValueError as e:
                if "模型未返回文本内容" not in str(e):
                    raise
                last_err = e
                if attempt == 0:
                    continue
                break
            else:
                return text
            finally:
                # 每次尝试退出时（成功/失败/超时/取消）都把该次已烧 token 落袋
                total_in += attempt_usage.get("tokens_in", 0)
                total_out += attempt_usage.get("tokens_out", 0)
        raise last_err  # type: ignore[misc]
    finally:
        _flush_usage(caller_usage, total_in, total_out)


def _flush_usage(usage: dict | None, tokens_in: int, tokens_out: int) -> None:
    """把累计用量写回调用方的 usage dict（None 则忽略）。"""
    if usage is not None:
        usage["tokens_in"] = tokens_in
        usage["tokens_out"] = tokens_out


async def _record_failure(
    db: AsyncSession,
    *,
    user_id: str,
    project_id: str | None,
    api_config_id: str | None,
    operation: str,
    model: str,
    usage: dict | None,
) -> None:
    """失败记账：operation 加 `_fail` 后缀、force 落库（零 token 的真实调用也留痕）。"""
    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user_id,
        project_id=project_id,
        api_config_id=api_config_id,
        operation=f"{operation}_fail"[:50],
        model=model,
        tokens_in=(usage or {}).get("tokens_in", 0),
        tokens_out=(usage or {}).get("tokens_out", 0),
        force=True,
    )


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
    except AITimeoutError:
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_intro_{action}", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_intro_{action}", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    # 记账先于解析：调用已完成（钱已花），JSON 不合法也要留痕
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

    data = _parse_json(text, "简介 AI")

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

def _world_theme(story: dict) -> tuple[str, str, str]:
    """题材锚（运行时读 story.yaml，不用前端快照）：标签/描述/示例。"""
    theme_name = (story.get("genre") or "").strip()
    theme_sub = (story.get("sub_genre") or "").strip()
    theme_label = f"{theme_name}（{theme_sub}）" if theme_sub else theme_name
    theme_desc, theme_example = _theme_anchor(theme_name, theme_sub)
    return theme_label, theme_desc, theme_example


async def _world_context(project, story: dict) -> dict:
    """世界 AI 共享上下文：书名/简介/题材锚/已有世界设定摘要。"""
    from settings.world_model import world_summary_text

    world_raw = await get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
    theme_label, theme_desc, _ = _world_theme(story)
    return {
        "title": _clamp_str(getattr(project, "name", ""), 100),
        "synopsis": _clamp_str(story.get("synopsis"), 600),
        "theme": theme_label,
        "theme_desc": theme_desc,
        "world": world_summary_text(world_raw, 1200) or "（世界设定还空着）",
    }


# 起草输出形状由调用方声明（前端知道要落哪个格）：text=一段话 / kv=名目条目 / faction=势力行
# 注意：format_line 是 .format() 的**参数**，花括号写单层（双层会原样进 prompt）
_DRAFT_SHAPES = ("text", "kv", "faction")
_DRAFT_SHAPE_LINE = {
    "text": "60-140 字一段话即可，作家确认后会写入对应格",
    "kv": "分条给出（3-6 条），每条一句话、具体可判，不要空话",
    "faction": "列出主要势力（2-3 个），每个注明想要什么、与谁敌友",
}
_DRAFT_FORMAT_LINE = {
    "text": '{"value": "一段话内容"}',
    "kv": '{"value": [{"key": "名目（≤10字）", "value": "一句话（≤80字）"}]}',
    "faction": '{"value": [{"name": "势力名（≤10字）", "note": "想要什么、与谁敌友"}]}',
}
# 已知要素的起草口径（吸收原字段级模板的精华；未知 topic 用通用口径）
_DRAFT_TOPIC_LINE = {
    "世界舞台": "写名称、时代、形态、主要地点；「暂不出场」的区域要写明",
    "力量体系": "力量叫什么、分几级、怎么获得；上限必须写死（最强者能做什么、不能做什么）",
    "力量的代价": "写消耗、副作用、冷却、禁忌与失控——代价是冲突的引信，无消耗的力量写不了冲突",
    "势力": "2-3 个：各自想要什么、与谁是敌是友；反派是立场不同，不是单纯坏",
    "世界铁律": "3-6 条不许破的硬边界：能力上限、不可推翻的事、世人不知道的事；要具体可判（如「死者不可复生」）",
    "历史与旧账": "只写剧情会用到的世界级大事：时间+经过+留下的后果；万年流水账不写",
}


def _sanitize_topic(raw) -> str:
    """topic 消毒：去控制字符与花括号/尖括号（防 prompt 结构被换行/占位符破坏）。"""
    topic = re.sub(r"[{}\[\]<>`]", "", str(raw or ""))
    return re.sub(r"[\x00-\x1f\x7f\r]", "", topic).strip()[:60]


def _normalize_draft_value(shape: str, raw) -> object:
    """按形状归一 AI 返回的 value：text 出一段话，kv/faction 出条目数组（空项丢弃）。"""
    if shape == "text":
        return _clamp_str(raw, 300)
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

    topic = _sanitize_topic(body.get("topic"))
    if not topic:
        raise HTTPException(400, "缺少主题（topic）")
    shape = str(body.get("shape") or "text").strip()
    if shape not in _DRAFT_SHAPES:
        raise HTTPException(400, "shape 仅支持 text/kv/faction")

    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    from settings.world_model import normalize_world

    world_raw = await get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
    # 现实向兜底：力量两格已收起时拒绝起草力量内容（与面板收起口径一致）
    if bool(normalize_world(world_raw).get("no_power")) and topic in ("力量体系", "力量的代价"):
        raise HTTPException(400, "本书开了现实向（无超自然力量），不起草力量内容；可起草「更多世界细节」")
    ctx = await _world_context(project, story)

    prompt = load_prompt("world_draft_topic").format(
        topic=topic,
        title=ctx["title"],
        synopsis=ctx["synopsis"],
        theme=ctx["theme"],
        theme_desc=ctx["theme_desc"],
        world=ctx["world"],
        shape_line=_DRAFT_SHAPE_LINE[shape],
        format_line=_DRAFT_FORMAT_LINE[shape],
        topic_line=_DRAFT_TOPIC_LINE.get(topic, ""),
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
    except AITimeoutError:
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_world_draft_{topic[:20]}",
            model=effective_model(project), usage=usage,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_world_draft_{topic[:20]}",
            model=effective_model(project), usage=usage,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    # 记账先于解析：调用已完成（钱已花），JSON 不合法也要留痕
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

    data = _parse_json(text, "世界起草")
    value = _normalize_draft_value(shape, data.get("value") if isinstance(data, dict) else None)
    if not value:
        raise HTTPException(502, "AI 没给出结果，可重试")
    if shape == "text":
        from settings.world_model import PARAGRAPH_MAX

        value = str(value)[:PARAGRAPH_MAX]

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
        _CHECK_STATUS,
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
    theme_label, theme_desc, _ = _world_theme(story)
    synopsis_missing = not synopsis.strip()
    theme_missing = not theme_label

    # D7 降级【拍板】：缺输入的检查项直接置 miss，不烧 AI 调用；
    # 三方缺二（简介+题材全空）→ 整次体检免调用，全部项置 miss。
    degraded_reasons: list[str] = []
    if synopsis_missing:
        degraded_reasons.append("简介未填")
    if theme_missing:
        degraded_reasons.append("题材未确认")

    def _miss_row(name: str, note: str) -> dict:
        return {"name": name, "status": "miss", "note": note}

    def _needs_synopsis(name: str) -> bool:
        return "简介" in name

    def _needs_theme(name: str) -> bool:
        return "题材" in name

    if synopsis_missing and theme_missing:
        items_out = [
            _miss_row(
                name,
                "输入缺失：简介未填、题材未确认——补完再体检更准"
                if (_needs_synopsis(name) and _needs_theme(name))
                else ("输入缺失：简介未填——先去补简介" if _needs_synopsis(name) else "输入缺失：题材未确认——先去题材页确认"),
            )
            for name in item_names
        ]
        return {"items": items_out, "degraded": True,
                "degraded_reasons": degraded_reasons, "verdict": "简介与题材都还没写，体检结果不完整"}

    prompt = load_prompt("world_check").format(
        synopsis=_clamp_str(synopsis, 600) or "（未填写）",
        theme=theme_label or "（未确认）",
        theme_desc=theme_desc or "（无）",
        world=world_summary_text(world_raw, 1200) or "（未填写）",
        items=" / ".join(item_names),
        mode_line="本书为现实向：没有超自然力量，用物理与法律规则判断" if no_power else "",
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
    except AITimeoutError:
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation="settings_world_check", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation="settings_world_check", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, f"体检失败，可重试：{e!s}") from e

    # 记账先于解析：调用已完成（钱已花），JSON 不合法也要留痕
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

    data = _parse_json(text, "一致性体检")
    # 名称归一匹配：模型把「简介 × 世界」写岔（空格/×半角）不算失格
    def _name_key(n: str) -> str:
        return re.sub(r"[\s×xX*·・]", "", n)

    ai_items: dict = {}
    raw_items = (data.get("items") if isinstance(data, dict) else []) or []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        name = _clamp_str(item.get("name"), 40)
        status = str(item.get("status", "")).strip()
        nk = _name_key(name)
        if nk and nk not in ai_items and status in _CHECK_STATUS:
            official = next((n for n in item_names if _name_key(n) == nk), None)
            if official:
                ai_items[nk] = {"name": official, "status": status,
                                "note": _clamp_str(item.get("note"), 120)}

    items_out = []
    for name in item_names:
        items_out.append(ai_items.get(_name_key(name)) or
                         {"name": name, "status": "miss", "note": "AI 未给出该项，可重跑体检"})

    degraded = bool(degraded_reasons)
    if synopsis_missing:
        for row in items_out:
            if _needs_synopsis(row["name"]):
                row.update(status="miss", note="输入缺失：简介未填——先去补简介，再重新体检")
    if theme_missing:
        for row in items_out:
            if _needs_theme(row["name"]):
                row.update(status="miss", note="输入缺失：题材未确认——先去题材页确认，再重新体检")

    verdict = _clamp_str(data.get("verdict"), 120) if isinstance(data, dict) else ""
    if degraded and not verdict:
        verdict = "体检输入不完整（" + "、".join(degraded_reasons) + "），结果仅供参考"
    return {"items": items_out, "degraded": degraded,
            "degraded_reasons": degraded_reasons, "verdict": verdict}


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
    except AITimeoutError:
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation="settings_world_lore_suggest", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation="settings_world_lore_suggest", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    # 记账先于解析：调用已完成（钱已花），JSON 不合法也要留痕
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

    data = _parse_json(text, "世界要素")
    # 与 archive 产出同形：每条带 canonical 章节引用 origin（幂等键）
    from settings.world_model import canonical_chapter_ref, parse_lore_suggestions

    suggestions = [
        {**item, "origin": canonical_chapter_ref(chapter_ref)}
        for item in parse_lore_suggestions(data)
    ]

    return {"suggestions": suggestions, "chapter_ref": chapter_ref}


# ── 按字段生成（world/style/hooks/genre）──────────────────────


# ═══ 主线 AI 四能力（storyline-settings-v2）══════════════════════════════
# draft（起草主线）/ calibrate（结局校准）/ check（主线体检）/ tone（行内基调）
# 全部聚焦本设定：他项设定只作输入，结论只落主线面板字段。
_ARC_ACTIONS: dict[str, str] = {
    "draft": "arc_draft",
    "calibrate": "arc_calibrate",
    "check": "arc_check",
    "tone": "arc_tone",
}


async def _arc_context(project) -> tuple[dict, dict]:
    """主线上下文：arc 归一形状 + 轻量他项输入（题材/简介；世界/角色由 prompt 引导 AI 概括，避免超长）。"""
    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    from novels.router import _arc_normalize

    arc = _arc_normalize(story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {})
    theme_label, theme_desc, _theme_fields = _world_theme(story)
    ctx = {
        "title": project.name if hasattr(project, "name") else "",
        "synopsis": str(story.get("synopsis", "") or ""),
        "theme": theme_label or "",
        "theme_desc": theme_desc or "",
    }
    return arc, ctx


@router.post("/ai/arc/{action}")
async def run_arc_ai(
    project_id: str,
    action: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """主线 AI 四能力：起草主线 / 结局校准 / 主线体检 / 行内基调建议。

    输入：body.input（散想法，可选）+ 面板当前内容从 KV 读取（不信任客户端整卡回传）。
    输出：{value} 信封；check 出 {checks:[{name,status,note}]} 四线。
    """
    if action not in _ARC_ACTIONS:
        raise HTTPException(400, f"不支持的主线 AI 动作：{action}")
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    arc, ctx = await _arc_context(project)
    author_input = str(body.get("input", "") or "").strip()
    # 素材门槛按行语义（2026-09-13 实测修正：draft 的主输入是「简介」——
    # 行描述即「把你的简介扩写成完整故事」，此前只认 fullstory 会把有简介的书拦成 400）
    has_synopsis = bool(ctx["synopsis"].strip())
    has_arc = bool(arc["fullstory"]) or any(arc["ending"].values())
    if action == "draft" and not (author_input or has_synopsis or has_arc):
        raise HTTPException(400, "先写两句简介，AI 才能帮你扩写成完整故事")
    if action == "calibrate" and not (author_input or has_arc):
        raise HTTPException(400, "先把主线或结局三问写两句，AI 才有校准的依据")

    # 提示词名走字面量白名单字典取值（勿用 f-string 拼 action：CodeQL 会把 URL 参数
    # 直接拼进文件路径判为高危 path injection——PR #355 CI 实测，此形态永不告警）
    template = load_prompt(_ARC_ACTIONS[action])
    formatted = template.format(
        input=author_input or "（无——按已填内容处理）",
        fullstory=arc["fullstory"] or "（未填）",
        scene=arc["ending"]["scene"] or "（未填）",
        hero=arc["ending"]["hero"] or "（未填）",
        tone=arc["ending"]["tone"] or "（未填）",
        **ctx,
    )

    _SYSTEMS = {
        "draft": "你是长篇小说结构顾问。只输出 JSON，不要任何其他文字。",
        "calibrate": "你是资深小说主编。只输出 JSON，不要任何其他文字。",
        "check": "你是小说主线编辑。只输出 JSON，不要任何其他文字。",
        "tone": "你是小说编辑。只输出 JSON，不要任何其他文字。",
    }
    # model 必须用客户端别名（haiku/sonnet/review → 配置模型）；字面模型名会
    # 透传供应商被拒 → 502（2026-09-13 实测："main" 非法）。
    # 起草/校准＝生成类（temp 0.6），体检/基调＝判定类（temp 0.3）。
    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await _judge_chat(
            client,
            model="haiku",
            system=_SYSTEMS[action],
            messages=[{"role": "user", "content": formatted}],
            temperature=0.6 if action in ("draft", "calibrate") else 0.3,
            json_mode=True,
            usage=usage,
        )
    except AITimeoutError:
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"arc_{action}", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"arc_{action}", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    # 记账先于解析：调用已完成（钱已花），JSON 不合法也要留痕
    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        api_config_id=project.ai_config_id,
        operation=f"arc_{action}",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )

    value = _parse_json(text, "主线 AI")

    # 素材门槛只拦 draft/calibrate（见上方 400）：check/tone 在内容全空时也照常发起
    # 一次调用——降级发生在 prompt 侧（模型把各线标 miss、提示先补再查），
    # 与 world_check 的「缺输入免调用」策略不同，此处不做免调用（P3，2026-09-13 检视）
    return {"value": value}


# ═══ 伏笔 AI 四能力（foreshadow-settings-v2 批2/批3）══════════════════════
# draft（起草候选）/ payoff（拟收束方案）/ audit（埋坑体检）/ check（查一致性）。
# 本节必须注册在下方 /ai/{stype}/{field} 通配之前（intro/world/arc 同款约束）。
# 注意：/ai/hooks/{action} 路由同时遮蔽了旧通配路径 /ai/hooks/description——
# 该 action 不在白名单时按 9.1 给专门退役文案（见下方分支）。
_HOOK_ACTIONS: dict[str, str] = {
    "draft": "hooks_draft",
    "payoff": "hooks_payoff",
    "audit": "hooks_audit",
    "check": "hooks_check",
}

# audit 判定常量（design D5：判定服务端出——类别/状态/跳转目标不采信模型自由文本，
# 模型只产每条的 note；id/code/goto_field 由本模块按真表与常量组装）。
AUDIT_OUTLINE_MAX_LINES = 60  # 章纲上下文封顶最近 60 章（全量拼 prompt 的护栏）
AUDIT_NO_PLAN_LINE = 40       # 「40 章未定期」提醒线：已写 ≥40 章仍无计划 → 默认 note 升格催办
_AUDIT_GOTO_FIELDS = ("planned", "payoff")  # 行跳转目标白名单（None＝在期，无需跳）

# check 三上下文行（world_check 同款：简介/题材/世界）；status 白名单同 audit。
_HOOK_CHECK_ITEMS = ("简介", "题材", "世界")
_HOOK_CHECK_STATUS = ("ok", "warn", "miss")


def _check_item_key(name) -> str:
    """模型回名归一：「简介 × 伏笔」「简介×伏笔」「简介」都映射回 简介。"""
    return re.sub(r"[\s×xX*·・]|伏笔", "", str(name or ""))


def _check_miss_row(item: str) -> dict:
    """缺输入行的 miss 出参（D7：补填出口写进 note，不报错不阻断）。"""
    notes = {
        "简介": "输入缺失：简介未填——先去补简介，再重新体检",
        "题材": "输入缺失：题材未确认——先去题材页确认，再重新体检",
        "世界": "输入缺失：世界设定还空着——先去世界面板补几条，再重新体检",
    }
    return {"name": f"{item} × 伏笔", "status": "miss", "note": notes[item]}


async def _hooks_draft_context(project) -> dict:
    """起草上下文全部后端自读（不信任前端快照）：简介＋题材锚＋世界＋主线。"""
    from novels.router import _arc_normalize
    from settings.world_model import world_summary_text

    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    world_raw = await get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
    theme_label, theme_desc, _ = _world_theme(story)
    arc_raw = story.get("story_arc") if isinstance(story.get("story_arc"), dict) else {}
    arc = _arc_normalize(arc_raw)
    return {
        "title": _clamp_str(getattr(project, "name", ""), 100),
        "synopsis": _clamp_str(story.get("synopsis"), 600),
        "theme": theme_label or "（未确认）",
        "theme_desc": theme_desc or "",
        "world": world_summary_text(world_raw, 1200) or "（世界设定还空着）",
        "fullstory": _clamp_str(arc["fullstory"], 600) or "（未填）",
    }


def _normalize_hook_candidates(data) -> list[dict]:
    """draft 出参归一（词表归一走 hooks_model，端点/模板不手抄枚举）：
    description 空丢弃；type 非法降默认「悬念」；priority 非法降默认「中」；最多 3 条。"""
    if not isinstance(data, dict):
        raise HTTPException(502, "伏笔起草返回结构不对，可重试")
    raw = data.get("candidates")
    out: list[dict] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        desc = _clamp_str(item.get("description") or item.get("desc"), DESCRIPTION_MAX)
        if not desc:
            continue
        htype = str(item.get("type") or "").strip()
        if htype not in HOOK_TYPE_KEYS:
            htype = HOOK_TYPE_KEYS[0]
        try:
            priority = normalize_priority(item.get("priority"))
        except ValueError:
            priority = 2
        out.append({"description": desc, "type": htype, "priority": priority})
        if len(out) >= 3:
            break
    if not out:
        raise HTTPException(502, "AI 没给出可用候选，可重试")
    return out


async def _load_written_outline(
    db: AsyncSession, novel_id: str
) -> tuple[list[tuple[int, str, str]], dict[str, int], dict[str, str]]:
    """已写章纲构建（批2 audit；payoff 同源复用）：返回 (written, pos_by_id, ref_by_id)。

    - written：[(书序 pos, 章 ref, prompt 行)]——outline_status != unfilled 或 summary
      非空才算「已写」，行渲染 `vol-N-ch-M 标题：summary`，摘要截 300
    - pos_by_id / ref_by_id：章 id → 书序位置 / 章 ref（超期判定与 id→ref 换算用）
    """
    from models.chapter import Chapter
    from models.volume import Volume

    ch_rows = (
        await db.execute(
            select(Chapter, Volume.volume_no)
            .join(Volume, Chapter.volume_id == Volume.id)
            .where(Chapter.project_id == novel_id)
            .order_by(Volume.volume_no, Chapter.chapter_no)
        )
    ).all()
    pos_by_id: dict[str, int] = {}
    ref_by_id: dict[str, str] = {}
    written: list[tuple[int, str, str]] = []  # (pos, ref, prompt 行)
    for pos, (ch, _vol_no) in enumerate(ch_rows, start=1):
        pos_by_id[ch.id] = pos
        ref_by_id[ch.id] = ch.ref
        summary = (ch.summary or "").strip()
        if (ch.outline_status or "unfilled") != "unfilled" or summary:
            head = f"{ch.ref} {ch.title}" if (ch.title or "").strip() else ch.ref
            written.append((pos, ch.ref, f"{head}：{summary[:300]}"))
    return written, pos_by_id, ref_by_id


async def _hooks_audit_scan(db: AsyncSession, novel_id: str) -> tuple[list[dict], list[str], int]:
    """埋坑体检的确定性扫描：类别/状态/跳转目标全由服务端判定（模型只补 note）。

    返回 (rows, outline_lines, written_count)：
    - rows：按 seq 序的体检行骨架。kind 四类——
        overdue 超期（计划收束章已过还没收 → miss）/ on_track 在期（ok）/
        no_plan 未定期（warn）/ no_receipt 无留痕（已收束没留「怎么收的」→ warn）
    - outline_lines：已写章纲 prompt 行（书序；构建见 _load_written_outline）
    - written_count：已写章纲章数（40 章未定期提醒线的判据）
    """
    from models.hook import NovelHook

    written, pos_by_id, ref_by_id = await _load_written_outline(db, novel_id)
    last_written = written[-1][0] if written else 0
    written_count = len(written)

    hooks = (
        await db.scalars(
            select(NovelHook)
            .where(
                NovelHook.novel_id == novel_id,
                NovelHook.status.in_(("active", "resolved")),
            )
            .order_by(NovelHook.seq)
        )
    ).all()

    rows: list[dict] = []
    for h in hooks:
        base = {
            "hook_id": h.id,
            "code": f"#H-{h.seq:04d}",
            "description": h.description,
        }
        if h.status == "resolved":
            # 无留痕：已收束但「怎么收的」/收束章节没留（软引导——体检持续点名）
            if not (h.payoff_note or "").strip() or not h.resolved_chapter_id:
                rows.append({
                    **base, "kind": "no_receipt", "status": "warn",
                    "goto_field": "payoff", "tag": "缺留痕",
                    "default_note": "已收束但没留「怎么收的」——补一句，下次体检不再点名",
                })
            continue
        planned_id = h.planned_chapter_id or ""
        planned_pos = pos_by_id.get(planned_id)
        if planned_id and planned_pos is not None and last_written and planned_pos <= last_written:
            rows.append({
                **base, "kind": "overdue", "status": "miss",
                "goto_field": "planned", "tag": f"超期·计划 {ref_by_id[planned_id]} 已过",
                "default_note": f"计划收束章 {ref_by_id[planned_id]} 已过还没收——去收束，或改期",
            })
        elif planned_id and planned_pos is not None:
            ref = ref_by_id[planned_id]
            rows.append({
                **base, "kind": "on_track", "status": "ok",
                "goto_field": None, "tag": f"在期·计划 {ref}",
                "default_note": f"计划 {ref}，还在期内",
            })
        else:
            escalated = written_count >= AUDIT_NO_PLAN_LINE
            rows.append({
                **base, "kind": "no_plan", "status": "warn",
                "goto_field": "planned", "tag": "未定期",
                "default_note": (
                    f"已写 {written_count} 章还没定期——读者快忘了这个坑，尽快定章"
                    if escalated
                    else "还没定计划收束章——章未建可先留空，这里会一直提醒"
                ),
            })
    return rows, [line for _, _, line in written], written_count


@router.post("/ai/hooks/{action}")
async def run_hooks_ai(
    project_id: str,
    action: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """伏笔 AI 四能力：draft（起草候选）/ payoff（拟收束方案）/ audit（埋坑体检）/ check（查一致性）。

    输入后端自读（story.yaml＋世界＋主线＋真表 chapters），不采信前端快照；
    例外是**选中伏笔的当前编辑值**——payoff/check 按 body 传值作用域（intro 先例：
    面板编辑未落库时也按所见出建议，不读库旧文）。
    audit 降级（world_check D7 先例）：无活跃伏笔 / 无已写章纲 → 免调用，
    纯台账自检只点名 未定期/无留痕，不报错不阻断。
    """
    if action not in _HOOK_ACTIONS:
        if action == "description":
            # 旧单字段生成路径退役（9.1）：/ai/hooks/{action} 白名单路由遮蔽了通配
            # 400 口径，这里给专门退役文案（沿角色 FIELD_GENERATABLE 摘除先例的 400 语义）。
            raise HTTPException(
                400,
                "伏笔单字段生成已退役：伏笔 AI 升级为四能力，"
                "请改用 /ai/hooks/draft（起草）、/payoff（拟收束）、/audit（埋坑体检）、/check（查一致性）",
            )
        raise HTTPException(400, f"不支持的伏笔 AI 动作：{action}")
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")

    # ── 选中作用域公共校验（payoff/check）：hook id ＋ 当前编辑描述 ──────────
    if action in ("payoff", "check"):
        hook_id = str(body.get("hook_id") or "").strip()
        if not hook_id:
            what = "拟收束方案" if action == "payoff" else "查一致性"
            raise HTTPException(400, f"先选一条伏笔——{what}对选中的伏笔生效")
        description = _clamp_str(body.get("description"), DESCRIPTION_MAX)
        if not description:
            raise HTTPException(400, "这条伏笔还没有描述，先写一句再让 AI 处理")

    # 选中伏笔展示上下文（type/priority 非法降默认，与 draft 出参同口径）
    def _hook_display() -> dict:
        htype = str(body.get("type") or "").strip()
        if htype not in HOOK_TYPE_KEYS:
            htype = HOOK_TYPE_KEYS[0]
        try:
            pri = normalize_priority(body.get("priority"))
        except ValueError:
            pri = 2
        return {
            "code": _clamp_str(body.get("code"), 12) or "（未编号）",
            "type_label": type_label(htype),
            "priority_label": priority_label(pri),
        }

    if action == "draft":
        ctx = await _hooks_draft_context(project)
        if not ctx["synopsis"].strip():
            raise HTTPException(400, "先写两句简介，AI 才有依据帮你埋伏笔")
        # 提示词名走字面量白名单字典取值（勿用 f-string 拼 action：见 arc 同款注释——
        # CodeQL 把 URL 参数拼进文件路径判为高危 path injection，此形态永不告警）
        formatted = load_prompt(_HOOK_ACTIONS[action]).format(
            title=ctx["title"],
            synopsis=ctx["synopsis"],
            theme=ctx["theme"],
            theme_desc=ctx["theme_desc"],
            world=ctx["world"],
            fullstory=ctx["fullstory"],
            # 词表由 hooks_model 渲染（模板不手抄枚举）
            type_list=" / ".join(f"{t['k']}（{t['label']}）" for t in HOOK_TYPES),
            priority_list=" / ".join(PRIORITY_LABELS[k] for k in sorted(PRIORITY_LABELS)),
        )
        system = "你是小说伏笔编辑。只输出 JSON，不要任何其他文字。"
    elif action == "payoff":
        # 主线是收束方案的依据（缺主线 400，中文原因）——fullstory 空时 _hooks_draft_context
        # 填的是「（未填）」占位，据此判缺
        ctx = await _hooks_draft_context(project)
        if not ctx["fullstory"].strip() or ctx["fullstory"] == "（未填）":
            raise HTTPException(400, "主线还没写——收束方案要按全书走向定收束点，先去主线面板写两句")
        written, _pos_by_id, ref_by_id = await _load_written_outline(db, project.id)
        planned_ref = ref_by_id.get(str(body.get("planned_chapter_id") or ""), "")
        disp = _hook_display()
        formatted = load_prompt(_HOOK_ACTIONS[action]).format(
            title=ctx["title"],
            code=disp["code"],
            description=description,
            type_label=disp["type_label"],
            priority_label=disp["priority_label"],
            planned=planned_ref or "（未定期——由你按主线节奏建议）",
            fullstory=ctx["fullstory"],
            outline_block=(
                "\n".join(line for _, _, line in written[-AUDIT_OUTLINE_MAX_LINES:])
                or "（还没有已写章纲——按主线节奏建议之后的章）"
            ),
        )
        system = "你是小说伏笔编辑。只输出 JSON，不要任何其他文字。"
    elif action == "check":
        # world_check 同款三上下文（简介/题材/世界）；选中伏笔值走 body（intro 先例）
        story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
        from settings.world_model import world_summary_text

        world_raw = await get_storage().read_yaml(project.root_path, "settings/world-setting.yaml") or {}
        theme_label, theme_desc, _ = _world_theme(story)
        synopsis = _clamp_str(story.get("synopsis"), 600)
        world_text = world_summary_text(world_raw, 1200)
        synopsis_missing = not synopsis.strip()
        theme_missing = not theme_label
        world_missing = not world_text.strip()
        degraded_reasons: list[str] = []
        if synopsis_missing:
            degraded_reasons.append("简介未填")
        if theme_missing:
            degraded_reasons.append("题材未确认")
        if world_missing:
            degraded_reasons.append("世界设定还空着")
        if len(degraded_reasons) == 3:
            # D7 降级【拍板】：三方全缺 → 整次体检免调用，全部行置 miss＋补填出口
            return {
                "checks": [_check_miss_row(x) for x in _HOOK_CHECK_ITEMS],
                "degraded": True,
                "degraded_reasons": degraded_reasons,
                "verdict": "简介、题材、世界都还没写——先补几笔，再查才有依据",
            }
        disp = _hook_display()
        formatted = load_prompt(_HOOK_ACTIONS[action]).format(
            code=disp["code"],
            description=description,
            type_label=disp["type_label"],
            priority_label=disp["priority_label"],
            synopsis=synopsis or "（未填写）",
            theme=theme_label or "（未确认）",
            theme_desc=theme_desc or "",
            world=world_text or "（未填写）",
        )
        system = "你是小说设定一致性审校。只输出 JSON，不要任何其他文字。"
    else:
        ctx = await _hooks_draft_context(project)
        rows, outline_lines, _written_count = await _hooks_audit_scan(db, project.id)
        # 降级免调用（D7）：无活跃伏笔 / 无已写章纲 → 纯台账自检（点名 未定期/无留痕）
        degraded_reasons = []
        if not rows:
            degraded_reasons.append("还没有活跃伏笔")
        elif not outline_lines:
            degraded_reasons.append("章纲还没写")
        if degraded_reasons:
            checks = [
                {
                    "hook_id": r["hook_id"],
                    "code": r["code"],
                    "status": r["status"],
                    "note": r["default_note"],
                    "goto_field": r["goto_field"],
                }
                for r in rows
                if r["kind"] in ("no_plan", "no_receipt")
            ]
            verdict = (
                "先埋一条伏笔（写一句描述就行），再来体检"
                if not rows
                else "章纲还没写，先按台账点名未定期/无留痕；章纲写好后体检更准"
            )
            return {
                "checks": checks,
                "degraded": True,
                "degraded_reasons": degraded_reasons,
                "verdict": verdict,
            }
        hooks_block = "\n".join(
            f"{no}. {r['code']}（{r['tag']}）{r['description']}"
            for no, r in enumerate(rows, start=1)
        )
        formatted = load_prompt(_HOOK_ACTIONS[action]).format(
            title=ctx["title"],
            synopsis=ctx["synopsis"] or "（未填写）",
            theme=ctx["theme"],
            fullstory=ctx["fullstory"],
            hooks_block=hooks_block,
            outline_block="\n".join(outline_lines[-AUDIT_OUTLINE_MAX_LINES:]) or "（无）",
        )
        system = "你是小说伏笔管理员。只输出 JSON，不要任何其他文字。"

    # model 必须用客户端别名（haiku/sonnet/review → 配置模型）；字面模型名会
    # 透传供应商被拒 → 502（见 arc 同款注释）。
    # 起草/拟收束＝生成类（temp 0.6）；体检/查一致性＝判定类（temp 0.3）。
    client = await get_ai_client_for_novel(project_id)
    usage: dict = {}
    try:
        text = await _judge_chat(
            client,
            model="haiku",
            system=system,
            messages=[{"role": "user", "content": formatted}],
            temperature=0.6 if action in ("draft", "payoff") else 0.3,
            json_mode=True,
            usage=usage,
        )
    except AITimeoutError:
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_hooks_{action}", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_hooks_{action}", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    # 记账先于解析：调用已完成（钱已花），JSON 不合法也要留痕
    from api_configs.usage import record_usage

    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        api_config_id=project.ai_config_id,
        operation=f"settings_hooks_{action}",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )

    data = _parse_json(text, "伏笔 AI")

    if action == "draft":
        return {"candidates": _normalize_hook_candidates(data)}

    if action == "payoff":
        # ref 走 canonical 惯例归一（world_model 单源，勿复制）：模型写模板短格式
        # 「1-3」也归一成 vol-1-ch-3；归一后仍不合规范形 → 502 可重试
        from settings.world_model import canonical_chapter_ref

        if not isinstance(data, dict):
            raise HTTPException(502, "拟收束方案返回结构不对，可重试")
        ref = canonical_chapter_ref(
            str(data.get("resolved_chapter_ref") or data.get("chapter_ref") or "")
        )
        if not re.fullmatch(r"vol-\d+-ch-\d+", ref):
            raise HTTPException(
                502, "收束章引用要写成 vol-N-ch-M（如 vol-1-ch-12），可重试"
            )
        note = _clamp_str(data.get("payoff_note") or data.get("note"), PAYOFF_NOTE_MAX)
        if not note:
            raise HTTPException(502, "AI 没给出「怎么收」的建议，可重试")
        return {"resolved_chapter_ref": ref, "payoff_note": note}

    if action == "check":
        # 出参白名单同 audit：status ∈ ok/warn/miss，模型写岔的行丢弃→回退「AI 未给出」；
        # 缺输入涉及行强制置 miss＋补填出口（world_check D7 同款，不采信模型对空输入的判定）
        raw_checks = (data.get("checks") if isinstance(data, dict) else []) or []
        ai_by_key: dict[str, dict] = {}
        for item in raw_checks if isinstance(raw_checks, list) else []:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", "")).strip()
            key = _check_item_key(item.get("name"))
            if not key or key in ai_by_key or status not in _HOOK_CHECK_STATUS:
                continue
            official = next(
                (x for x in _HOOK_CHECK_ITEMS if _check_item_key(x) == key), None
            )
            if official:
                ai_by_key[key] = {
                    "name": f"{official} × 伏笔",
                    "status": status,
                    "note": _clamp_str(item.get("note"), 120),
                }
        checks_out = [
            ai_by_key.get(x)
            or {"name": f"{x} × 伏笔", "status": "miss", "note": "AI 未给出该项，可重试"}
            for x in _HOOK_CHECK_ITEMS
        ]
        if synopsis_missing:
            checks_out[0] = _check_miss_row("简介")
        if theme_missing:
            checks_out[1] = _check_miss_row("题材")
        if world_missing:
            checks_out[2] = _check_miss_row("世界")
        degraded = bool(degraded_reasons)
        verdict = _clamp_str(data.get("verdict"), 120) if isinstance(data, dict) else ""
        if degraded and not verdict:
            verdict = "查一致性输入不完整（" + "、".join(degraded_reasons) + "），结果仅供参考"
        return {
            "checks": checks_out,
            "degraded": degraded,
            "degraded_reasons": degraded_reasons,
            "verdict": verdict,
        }

    # audit：模型只产 note（reason），id/status/goto_field 以服务端骨架为准组装——
    # 模型没给/写岔编号的行回退服务端默认 note，绝不因模型缺行丢点名。
    reasons: dict[int, str] = {}
    raw_reasons = (data.get("reasons") if isinstance(data, dict) else []) or []
    for item in raw_reasons if isinstance(raw_reasons, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            no = int(item.get("no"))
        except (TypeError, ValueError):
            continue
        note = _clamp_str(item.get("reason"), 120)
        if no >= 1 and note:
            reasons[no] = note
    checks = [
        {
            "hook_id": r["hook_id"],
            "code": r["code"],
            "status": r["status"],
            "note": reasons.get(no) or r["default_note"],
            "goto_field": r["goto_field"],
        }
        for no, r in enumerate(rows, start=1)
    ]
    return {"checks": checks, "degraded": False, "degraded_reasons": [], "verdict": ""}


# ── 文风蒸馏与三区 AI（style-settings-v2）──────────────────────────
# 注意：本路由族必须注册在 /ai/{stype}/{field} 之前，否则被通配遮蔽（hooks 同款注释）。

_STYLE_DISTILL_ACTIONS = {"step1", "step2", "step3", "commit"}


async def _load_quant_doc(root_path: str) -> dict:
    from settings.style_quant_model import quant_doc
    from filesystem.paths import STYLE_QUANT_PATH
    from filesystem.storage import get_storage

    return quant_doc(await get_storage().read_yaml(root_path, STYLE_QUANT_PATH) or {})


async def _save_quant_doc(root_path: str, doc: dict) -> None:
    from filesystem.paths import STYLE_QUANT_PATH
    from filesystem.storage import get_storage

    await get_storage().write_yaml(root_path, STYLE_QUANT_PATH, doc)


async def _assemble_distill_samples(project, body: dict, db) -> tuple[str, int, list[str]]:
    """样本两路装配：novel-samples/ 文件＋勾选已归档章节；区间校验（3,000–10,000）。"""
    import os

    from models.archive import Archive
    from models.chapter import Chapter
    from settings.style_quant_model import SAMPLE_MAX, SAMPLE_MIN

    files = [str(x) for x in (body.get("files") or []) if str(x).strip()]
    chapter_ids = [str(x) for x in (body.get("chapter_ids") or []) if str(x).strip()]
    samples_dir = os.path.join(project.root_path, "novel-samples")
    texts: list[str] = []
    used: list[str] = []
    matched_chapters = 0
    for name in files[:20]:
        safe = os.path.realpath(os.path.join(samples_dir, name))
        if os.path.dirname(safe) != os.path.realpath(samples_dir) or not os.path.isfile(safe):
            raise HTTPException(400, f"样本文件不可用：{name}")
        with open(safe, encoding="utf-8", errors="ignore") as f:
            texts.append(f.read())
        used.append(name)
    if chapter_ids:
        rows = await db.execute(
            select(Archive)
            .join(Chapter, Chapter.id == Archive.chapter_id)
            .where(Chapter.project_id == project.id, Archive.chapter_id.in_(chapter_ids))
        )
        for a in rows.scalars():
            matched_chapters += 1
            texts.append(a.content or "")
            used.append(a.title or "已归档章节")
    text = "\n\n".join(texts)
    chars = len("".join(text.split()))
    if chars < SAMPLE_MIN:
        raise HTTPException(400, f"样本合计 {chars} 字，少于 {SAMPLE_MIN} 字统计噪声大——再补一些你认可的文章")
    if chars > SAMPLE_MAX:
        raise HTTPException(400, f"样本合计 {chars} 字，超过 {SAMPLE_MAX} 字——挑最有代表性的几章")
    return text, chars, used, matched_chapters


async def _distill_llm(project, user, db, *, system: str, prompt: str):
    """蒸馏单步 LLM 调用：沿 hooks 管线（judge 重试＋记账＋JSON 解析）。"""
    from api_configs.usage import record_usage

    client = await get_ai_client_for_novel(project.id)
    usage: dict = {}
    try:
        text = await _judge_chat(
            client,
            model="haiku",
            system=system,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            json_mode=True,
            usage=usage,
        )
    except AITimeoutError:
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation="settings_style_distill", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation="settings_style_distill", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, f"AI 学习失败，可重试：{e!s}") from e
    await record_usage(
        db,
        user_id=user["id"],
        project_id=project.id,
        api_config_id=project.ai_config_id,
        operation="settings_style_distill",
        model=effective_model(project),
        tokens_in=usage.get("tokens_in", 0),
        tokens_out=usage.get("tokens_out", 0),
    )
    return _parse_json(text, "文风蒸馏")


@router.post("/ai/style-distill/{action}")
async def style_distill_ai(
    project_id: str,
    action: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """蒸馏三步＋落卡（A3 组装审阅形）：每步产物落 style-quant.draft，中断续跑；
    「不像，再学一次」＝ step3 带 force 重跑；commit 落正式区＋history＋禁用词并入。"""
    if action not in _STYLE_DISTILL_ACTIONS:
        raise HTTPException(400, f"不支持的蒸馏动作：{action}")
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    body = body or {}
    doc = await _load_quant_doc(project.root_path)
    draft = doc.get("draft") or {}

    if action == "commit":
        from settings.style_model import append_anti_ai_words
        from settings.style_quant_model import commit_draft

        doc = commit_draft(doc, sample_chars=int(draft.get("sample_chars") or 0), chapter_count=int(draft.get("chapter_count") or 0), at=datetime.now(UTC).isoformat(timespec="seconds"))
        await _save_quant_doc(project.root_path, doc)
        banned = (draft.get("step3") or {}).get("banned") or []
        added = await append_anti_ai_words(project.root_path, banned) if banned else 0
        return {"ok": True, "quant": await _load_quant_doc(project.root_path), "banned_added": added}

    if not isinstance(body, dict):
        body = {}

    if action == "step1":
        if draft.get("step1"):
            return {"ok": True, "resumed": True, "step": draft.get("step", 0)}
        text, chars, used, matched_chapters = await _assemble_distill_samples(project, body, db)
        prompt = load_prompt("style_distill_step1").format(sample=text)
        data = await _distill_llm(project, user, db, system="你是文风分析师。只输出 JSON，不要任何其他文字。", prompt=prompt)
        sections = data.get("sections") if isinstance(data, dict) else None
        if not isinstance(sections, list) or not sections:
            raise HTTPException(502, "样本标注返回结构不对，可重试")
        draft.update({
            "step": 1,
            "sample_chars": chars,
            "chapter_count": matched_chapters,
            "samples_used": used,
            "step1": {"sections": sections[:40]},
        })
        doc["draft"] = draft
        await _save_quant_doc(project.root_path, doc)
        return {"ok": True, "step": 1, "sections": len(sections[:40])}

    if action == "step2":
        if draft.get("step2"):
            return {"ok": True, "resumed": True, "step": draft.get("step", 0)}
        if not draft.get("step1"):
            raise HTTPException(400, "先完成第一步（样本标注）")
        step1_lines = "\n".join(
            f"- {s.get('label')}（{s.get('layer')}）" for s in draft["step1"].get("sections", []) if isinstance(s, dict)
        )
        prompt = load_prompt("style_distill_step2").format(
            sample_chars=draft.get("sample_chars", 0), step1_summary=step1_lines or "（无）"
        )
        data = await _distill_llm(project, user, db, system="你是文风量化分析师。只输出 JSON，不要任何其他文字。", prompt=prompt)
        metrics = data.get("metrics") if isinstance(data, dict) else None
        if not isinstance(metrics, dict):
            raise HTTPException(502, "量化统计返回结构不对，可重试")
        draft["step"] = 2
        draft["step2"] = {"metrics": metrics}
        doc["draft"] = draft
        await _save_quant_doc(project.root_path, doc)
        return {"ok": True, "step": 2}

    # step3：归纳九维＋画像＋禁用词候选；force=「不像，再学一次」（只重跑本步）
    if action == "step3" and not body.get("force") and draft.get("step3"):
        return {"ok": True, "resumed": True, "step": draft.get("step", 0)}
    if not draft.get("step2"):
        raise HTTPException(400, "先完成第二步（量化统计）")
    metrics = (draft.get("step2") or {}).get("metrics") or {}
    metrics_lines = "\n".join(f"- {k}：{v}" for k, v in metrics.items())
    prompt = load_prompt("style_distill_step3").format(metrics=metrics_lines)
    data = await _distill_llm(project, user, db, system="你是文风蒸馏师。只输出 JSON，不要任何其他文字。", prompt=prompt)
    if not isinstance(data, dict) or not isinstance(data.get("baseline"), dict):
        raise HTTPException(502, "文风归纳返回结构不对，可重试")
    banned = data.get("banned")
    draft["step"] = 3
    draft["step3"] = {
        "baseline": data.get("baseline"),
        "details": data.get("details") or {},
        "portrait": _clamp_str(data.get("portrait"), 1200),
        "banned": [str(x).strip()[:50] for x in banned if str(x).strip()][:50] if isinstance(banned, list) else [],
    }
    doc["draft"] = draft
    await _save_quant_doc(project.root_path, doc)
    return {"ok": True, "step": 3, "portrait": draft["step3"]["portrait"]}


@router.post("/ai/style/{action}")
async def run_style_ai(
    project_id: str,
    action: str,
    body: dict,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """文风三区 AI：polish（润色/起草三区）/check（锚定体检）/fewshot-mine（例句提炼）。

    旧 /ai/style/{field} 单字段生成随三区改版退役——落到本路由未知 action 分支，
    给专门退役文案（hooks 9.1 先例）。
    """
    if action not in ("polish", "check", "fewshot-mine"):
        raise HTTPException(
            400,
            "文风单字段生成已退役：文风 AI 升级为三区，"
            "请改用 /ai/style/polish（润色文字文风）、/check（锚定体检）、/fewshot-mine（例句提炼）",
        )
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Project not found")
    body = body or {}
    story = await get_storage().read_yaml(project.root_path, "story.yaml") or {}
    premise = _clamp_str(story.get("synopsis"), 600)
    usage_note = "输入：题材＋简介"

    if action == "polish":
        if not premise:
            raise HTTPException(400, "先写两句简介，AI 才有依据帮你起草文风")
        ctx = body.get("context", {}) or {}
        ctx_text = "\n".join(f"- {k}：{v}" for k, v in ctx.items() if v) or "（空——按蓝图起草）"
        prompt = load_prompt("settings_style").format(premise=premise, context=ctx_text)
        system = "你是小说文风设定专家。只输出 JSON，不要任何其他文字。"
        data = await _distill_llm(project, user, db, system=system, prompt=prompt)
        if not isinstance(data, dict):
            raise HTTPException(502, "文风起草返回结构不对，可重试")
        role = _clamp_str(data.get("role"), 500)
        rules = [str(x).strip()[:500] for x in data.get("rules", []) if str(x).strip()][:8]
        craft = [str(x).strip()[:500] for x in data.get("craft", []) if str(x).strip()][:8]
        if not role or not rules:
            raise HTTPException(502, "文风起草缺少身份或红线，可重试")
        return {"role": role, "rules": rules, "craft": craft}

    if action == "check":
        role = _clamp_str(body.get("role"), 500)
        rules = [str(x).strip()[:500] for x in body.get("rules", []) if str(x).strip()]
        craft = [str(x).strip()[:500] for x in body.get("craft", []) if str(x).strip()]
        if not role:
            raise HTTPException(400, "先写叙事身份——锚定体检对当前三区生效")
        anti = await get_storage().read_yaml(project.root_path, "settings/anti-ai.yaml") or {}
        fatigue = [
            w
            for cat in (anti.get("fatigue_words_zh") or {}).values()
            if isinstance(cat, list)
            for w in cat
        ][:40]
        rules_text = "\n".join(f"- {r}" for r in rules) or "（未填）"
        craft_text = "\n".join(f"- {c}" for c in craft) or "（未填）"
        prompt = load_prompt("style_check").format(
            role=role, rules=rules_text, craft=craft_text,
            fatigue="、".join(str(w) for w in fatigue) or "（空）",
        )
        system = "你是小说设定一致性审校。只输出 JSON，不要任何其他文字。"
        data = await _distill_llm(project, user, db, system=system, prompt=prompt)
        checks = data.get("checks") if isinstance(data, dict) else None
        if not isinstance(checks, list):
            raise HTTPException(502, "锚定体检返回结构不对，可重试")
        return {
            "checks": checks[:8],
            "verdict": _clamp_str(data.get("verdict"), 200) if isinstance(data, dict) else "",
        }

    # fewshot-mine：从已归档正文提炼 1-3 条标志句
    rows = await db.execute(
        select(Archive)
        .join(Chapter, Chapter.id == Archive.chapter_id)
        .where(Chapter.project_id == project.id)
        .order_by(Archive.archived_at.desc())
        .limit(6)
    )
    texts = [(a.title or "章节", (a.content or "")[:1200]) for a in rows.scalars()]
    if not texts:
        raise HTTPException(400, "还没有已归档章节——写完一章并归档后，AI 才能替你挑例句")
    corpus = "\n\n".join(f"【{t}】\n{c}" for t, c in texts)
    prompt = load_prompt("style_fewshot_mine").format(corpus=corpus)
    system = "你是文风编辑。只输出 JSON，不要任何其他文字。"
    data = await _distill_llm(project, user, db, system=system, prompt=prompt)
    lines = [str(x).strip()[:300] for x in (data.get("lines") or []) if str(x).strip()][:3] if isinstance(data, dict) else []
    if not lines:
        raise HTTPException(502, "例句提炼返回结构不对，可重试")
    return {"lines": lines}


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
    except AITimeoutError:
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_{stype}_{field}", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, "AI 服务响应超时，请稍后重试")
    except Exception as e:  # noqa: BLE001
        await _record_failure(
            db, user_id=user["id"], project_id=project.id,
            api_config_id=project.ai_config_id,
            operation=f"settings_{stype}_{field}", model=effective_model(project),
            usage=usage,
        )
        raise HTTPException(502, f"AI 生成失败，可重试：{e!s}") from e

    # 记账先于解析：调用已完成（钱已花），JSON 不合法也要留痕
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

    value = _parse_json(text, "设定 AI")
    if stype == "genre":
        value = _normalize_genre_value(field, value)

    return {"value": value}
