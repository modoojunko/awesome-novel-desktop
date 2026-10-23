"""图像 prompt 组装（c-cover-avatar）。

契约（模板 v2.1）：
- 封面只读书级信息：题材气质、核心承诺、世界舞台、用户封面描述；**不读**书名、
  简介原文、正文、章纲。书名只进 sources，绝不进 prompt。
- 头像只读角色卡白名单：性别/年龄/种族、外貌、势力/身份、一句话人设；**不读**
  角色名、正文、章纲、dossier.background、dossier.plot。
- 自由文本统一做“内容级脱敏”：书名、角色名/别名即使写在世界舞台、人设、势力、
  cover_prompt、avatar_prompt 里，也会替换成泛称，避免模型画招牌/题字/剧透。
- prompt_hash 对 canonical request（模板版本/画风/正向/负向/尺寸/seed/模型/provider/
  能力）做 SHA-256；每候选独立 seed，预览给 candidate_seeds[0]。
"""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from filesystem.storage import get_storage
from genres.novel_genre_service import get_novel_genre
from models.character import Character
from models.image_asset import BookImageSettings, CharacterImageSettings, ImageConfig
from models.project import Novel
from settings.world_model import normalize_world

PROMPT_TEMPLATE_VERSION = 3  # v2.1 模板：名称脱敏/正向无文字/候选 seed
MAX_SEED = 2**31 - 1

STYLE_CANONICAL = {
    "ink": "ink", "水墨": "ink",
    "cinematic": "cinematic", "电影写实": "cinematic",
    "guoman": "guoman", "国漫": "guoman",
    "print": "print", "版画": "print",
    "minimal": "minimal", "极简": "minimal",
}
STYLE_KEYS = frozenset(STYLE_CANONICAL)
STYLE_PREFIX = {
    "ink": "水墨画风格，宣纸质感，墨色浓淡相宜，少量暖色点染，留白",
    "cinematic": "电影剧照风格，浅景深，真实材质与皮肤质感，低饱和",
    "guoman": "国漫插画风格，干净线条，平涂加柔和渐变，人物造型鲜明",
    "print": "木刻版画风格，粗粝刀痕与高对比色块，边缘硬朗，颗粒感",
    "minimal": "极简插画风格，大面积留白，少量几何形状与单一强调色，克制",
}
STYLE_TAIL = {
    "ink": "构图留白，墨色层次清楚，边缘干净",
    "cinematic": "自然光，主体清晰，背景虚化克制",
    "guoman": "线条干净，色块利落，主体明确",
    "print": "刀痕粗粝，黑白对比明确，边缘硬朗",
    "minimal": "构图克制，留白充足，单一强调色",
}
DEFAULT_STYLE = "ink"

COVER_SIZE = (768, 1024)
AVATAR_SIZE = (512, 512)

_NEGATIVE_BASE = (
    "文字，汉字，英文，字母，数字，签名，印章，水印，logo，标志，边框，二维码，"
    "牌匾，招牌，书页，屏幕，书法，题字，落款，徽章，徽记，拼音，横幅，标题框，"
    "画面内文字排版，整体失焦，低清晰度，噪点，压缩伪影"
)
NEGATIVE_COVER = (
    f"{_NEGATIVE_BASE}，拼贴，多场景，分镜，人物畸形，多余肢体，错误手指，"
    "过曝，死黑，杂乱背景"
)
NEGATIVE_AVATAR = (
    f"{_NEGATIVE_BASE}，全身像，半身像，七分身，远景，背影，低头，多人，"
    "侧脸遮挡，脸部过小，夸张表情，塑料皮肤，多余肢体，错误手指，畸形五官，"
    "服装图案，胸标，臂章"
)
_NO_TEXT_COVER = (
    "画面中没有任何文字、标题、书法、题字、印章、签名、水印、logo、边框，"
    "不出现牌匾、招牌、书页、屏幕等可读文字载体"
)
_NO_TEXT_AVATAR = (
    "画面中没有任何文字、徽标、水印、边框，服装上不出现文字或图案，"
    "背景为纯净中性浅灰"
)


def _clamp(text, n: int) -> str:
    s = " ".join(str(text or "").split()).strip()
    return s[:n]


def _first_sentence(text, n: int) -> str:
    s = " ".join(str(text or "").split()).strip()
    for sep in ("。", "；", "\n"):
        if sep in s:
            s = s.split(sep, 1)[0]
    return s[:n]


def _join_sentences(parts: list[str]) -> str:
    clean = []
    for part in parts:
        s = str(part or "").strip().rstrip("。！？；，、")
        if s:
            clean.append(s)
    return "。".join(clean) + "。"


def _canonical_style(value) -> str:
    return STYLE_CANONICAL.get(str(value or ""), DEFAULT_STYLE)


def _seed_for_candidate(base: int, index: int) -> int:
    return (int(base) + index) % MAX_SEED


def _redact(text, names: dict[str, str]) -> str:
    s = str(text or "")
    for name in sorted(names, key=len, reverse=True):
        if len(name) >= 2:
            s = s.replace(name, names[name])
    return s


def _capabilities(provider: str, declared: dict | None) -> dict:
    caps = {
        "negative_supported": True,
        "seed_supported": True,
        "watermark_supported": provider == "volcengine",
    }
    if provider == "openai":
        caps.update(negative_supported=False, seed_supported=False)
    elif provider == "minimax":
        caps.update(negative_supported=False)
    elif provider == "openai-compat" and isinstance(declared, dict):
        for key in caps:
            if key in declared:
                caps[key] = bool(declared[key])
    return caps


def _canonical_request(
    *, kind: str, style_key: str, prompt: str, negative_prompt: str,
    size: tuple[int, int], seed: int | None, model: str | None,
    provider: str, capabilities: dict,
) -> dict:
    return {
        "kind": kind,
        "template_version": PROMPT_TEMPLATE_VERSION,
        "style_key": style_key,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "size": f"{size[0]}x{size[1]}",
        "seed": seed,
        "model": model or "",
        "provider": provider or "",
        "watermark": False,
        "capabilities": capabilities,
    }


def _hash_request(canonical: dict) -> str:
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _effective_canonical(canonical: dict, capabilities: dict, prompt_override: str | None = None) -> dict:
    """按供应商能力裁剪 canonical：不支持的字段不参与 effective hash。"""
    out = json.loads(json.dumps(canonical, ensure_ascii=False))
    if not capabilities.get("seed_supported", True):
        out["seed"] = None
    if not capabilities.get("negative_supported", True):
        out["negative_prompt"] = ""
    if not capabilities.get("watermark_supported", False):
        out.pop("watermark", None)
    if prompt_override is not None:
        out["prompt"] = prompt_override
    return out


def effective_prompt_hash(
    preview: dict, index: int = 0, *,
    capabilities: dict | None = None, prompt_override: str | None = None,
) -> str:
    """候选级 effective hash：candidate 0 与预览 hash 对齐，后续候选独立。"""
    caps = capabilities or dict(preview.get("capabilities") or {})
    size = preview.get("size") or {}
    canonical = _canonical_request(
        kind=preview["kind"], style_key=preview["style_key"],
        prompt=preview["prompt"], negative_prompt=preview["negative_prompt"],
        size=(int(size.get("width", 0)), int(size.get("height", 0))),
        seed=preview.get("seed"), model=preview.get("model"),
        provider=preview.get("provider") or "", capabilities=caps,
    )
    seeds = preview.get("candidate_seeds") or []
    if caps.get("seed_supported", True) and 0 <= index < len(seeds):
        canonical["seed"] = seeds[index]
    return _hash_request(_effective_canonical(canonical, caps, prompt_override))


async def _name_map(db: AsyncSession, novel: Novel) -> dict[str, str]:
    """本书书名/角色名/别名 → 泛称；只替换长度 >=2 的名字，避免误伤常用字。"""
    mapping: dict[str, str] = {}
    if novel.name and len(novel.name.strip()) >= 2:
        mapping[novel.name.strip()] = "此地"
    rows = (await db.execute(
        select(Character.name, Character.aliases).where(Character.novel_id == novel.id)
    )).all()
    for name, aliases in rows:
        candidates = [name]
        try:
            candidates.extend(json.loads(aliases or "[]"))
        except (TypeError, ValueError):
            pass
        for candidate in candidates:
            s = str(candidate or "").strip()
            if len(s) >= 2 and s not in mapping:
                mapping[s] = "人物"
    return mapping


async def _effective_config(
    db: AsyncSession, novel: Novel, row: BookImageSettings | None,
) -> tuple[ImageConfig | None, str, dict]:
    config = None
    if row and row.image_config_id:
        config = (await db.execute(select(ImageConfig).where(
            ImageConfig.id == row.image_config_id,
            ImageConfig.user_id == novel.user_id,
            ImageConfig.status == "active",
        ))).scalar_one_or_none()
    if config is None:
        config = (await db.execute(select(ImageConfig).where(
            ImageConfig.user_id == novel.user_id,
            ImageConfig.status == "active",
        ).order_by(ImageConfig.is_default.desc(), ImageConfig.created_at.asc()))).scalars().first()
    model = (row.image_model if row else "") or (config.default_model if config else "")
    declared = {}
    if config:
        try:
            declared = json.loads(config.declared_capabilities or "{}")
        except (TypeError, ValueError):
            declared = {}
    return config, model, declared


async def _read_book_sources(db: AsyncSession, novel: Novel) -> dict:
    storage = get_storage()
    story = await storage.read_yaml(novel.root_path, "story.yaml") or {}
    world = await storage.read_yaml(novel.root_path, "settings/world-setting.yaml") or {}
    genre = await get_novel_genre(db, novel.id)
    row = (await db.execute(
        select(BookImageSettings).where(BookImageSettings.novel_id == novel.id)
    )).scalar_one_or_none()
    config, model, declared = await _effective_config(db, novel, row)
    names = await _name_map(db, novel)
    world_v2 = normalize_world(world)
    battlefield = genre.get("battlefield") or []
    if isinstance(battlefield, str):
        battlefield = [battlefield]
    battlefield_text = "、".join(str(x) for x in battlefield[:3])

    def redact(value, n: int) -> str:
        return _clamp(_redact(value, names), n)

    theme = _clamp(story.get("genre"), 40)
    sub_genre = _clamp(story.get("sub_genre"), 40)
    return {
        "name": novel.name,
        "theme": redact(theme, 40),
        "sub_genre": redact(sub_genre, 40),
        "synopsis": _clamp(story.get("synopsis"), 240),
        "core_promise": redact(genre.get("core_promise"), 60),
        "battlefield": _clamp(battlefield_text, 80),
        "world_stage": redact(_first_sentence(world_v2.get("stage"), 80), 60),
        "style_key": _canonical_style(row.style_key if row else DEFAULT_STYLE),
        "cover_prompt": redact(row.cover_prompt if row else "", 180),
        "cover_seed": row.cover_seed if row else None,
        "model": model,
        "provider": config.provider if config else "",
        "capabilities": _capabilities(config.provider if config else "", declared),
    }


async def build_cover_prompt(db: AsyncSession, novel: Novel) -> dict:
    src = await _read_book_sources(db, novel)
    style = src["style_key"]
    theme = " · ".join(x for x in (src["theme"], src["sub_genre"]) if x)
    scene = src["cover_prompt"]
    seed = src["cover_seed"] if src["cover_seed"] is not None else _derive_seed("cover", novel.id)
    seed_source = "settings" if src["cover_seed"] is not None else "derived"

    parts = [
        STYLE_PREFIX[style],
        "竖版封面构图，单一视觉焦点，主体位于画面中下部，顶部保留干净留白",
    ]
    if scene:
        parts.append(f"画面呈现{scene}")
    else:
        parts.append("单一象征性静物作为画面焦点，环境简洁，不出现具体人物")
    if theme:
        parts.append(f"整体气质接近{theme}题材，克制、不直白")
    if src["core_promise"]:
        parts.append(f"情绪落在{src['core_promise']}上")
    if src["world_stage"]:
        parts.append(src["world_stage"])
    parts.extend([STYLE_TAIL[style], _NO_TEXT_COVER])
    prompt = _join_sentences(parts)

    canonical = _canonical_request(
        kind="cover", style_key=style, prompt=prompt,
        negative_prompt=NEGATIVE_COVER, size=COVER_SIZE, seed=seed,
        model=src["model"], provider=src["provider"],
        capabilities=src["capabilities"],
    )
    return {
        "kind": "cover",
        "prompt": prompt,
        "negative_prompt": NEGATIVE_COVER,
        "prompt_hash": _hash_request(_effective_canonical(canonical, src["capabilities"])),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "style_key": style,
        "size": {"width": COVER_SIZE[0], "height": COVER_SIZE[1]},
        "seed": seed,
        "seed_source": seed_source,
        "candidate_seeds": [seed, _seed_for_candidate(seed, 1)],
        "model": src["model"] or None,
        "model_unbound": not bool(src["model"]),
        "provider": src["provider"] or None,
        "capabilities": src["capabilities"],
        "watermark": False,
        "needs_scene": not bool(scene),
        "uses_default_subject": not bool(scene),
        "sources": {
            "name": src["name"],
            "theme": theme,
            "core_promise": src["core_promise"],
            "synopsis": src["synopsis"],
            "world_stage": src["world_stage"],
            "battlefield": src["battlefield"],
            "override": bool(scene),
        },
    }


def _person_clause(gender: str, age: str, race: str) -> str:
    gender = "男性" if gender == "男" else "女性" if gender == "女" else gender
    age_text = age
    if age_text.isdigit():
        age_text = f"{age_text}岁"
    race_text = race
    if race_text and not race_text.endswith(("族", "人")):
        race_text = f"{race_text}族"
    first = f"{age_text}{gender}" if age_text and gender else (age_text or gender)
    return "，".join(x for x in (first, race_text) if x)


def _derive_seed(kind: str, key: str) -> int:
    digest = hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()
    return int(digest[:8], 16) % MAX_SEED


async def build_avatar_prompt(db: AsyncSession, novel: Novel, ch: Character) -> dict:
    story = await get_storage().read_yaml(novel.root_path, "story.yaml") or {}
    bsettings = (await db.execute(
        select(BookImageSettings).where(BookImageSettings.novel_id == novel.id)
    )).scalar_one_or_none()
    csettings = (await db.execute(
        select(CharacterImageSettings).where(CharacterImageSettings.character_id == ch.id)
    )).scalar_one_or_none()
    config, model, declared = await _effective_config(db, novel, bsettings)
    style = _canonical_style(bsettings.style_key if bsettings else DEFAULT_STYLE)
    names = await _name_map(db, novel)
    try:
        dossier = json.loads(ch.dossier or "{}")
        if not isinstance(dossier, dict):
            dossier = {}
    except (TypeError, ValueError):
        dossier = {}

    def redact(value, n: int) -> str:
        return _clamp(_redact(value, names), n)

    gender = redact(dossier.get("gender"), 20)
    age = redact(dossier.get("age"), 20)
    race = redact(dossier.get("race"), 20)
    look = redact(dossier.get("look"), 120)
    faction = redact(dossier.get("faction"), 60)
    persona = redact(ch.persona, 60)
    subject = redact(csettings.avatar_prompt if csettings else "", 140)
    seed = csettings.seed if csettings and csettings.seed is not None else _derive_seed("avatar", ch.id)
    seed_source = "settings" if csettings and csettings.seed is not None else "derived"
    provider = config.provider if config else ""
    capabilities = _capabilities(provider, declared)

    parts = [
        STYLE_PREFIX[style],
        (
            "近景头肩像，只到肩部，不露腰，人物居中，脸部约占画面高度一半，"
            "双眼位于画面上三分之一，正面或四分之三侧，中性浅灰背景"
        ),
        _person_clause(gender, age, race),
        look,
        f"身份背景是{faction}，只用服装轮廓与随身物件暗示" if faction else "",
        f"神情气质接近{persona}" if persona else "",
        f"外貌补充：{subject}；只补充外貌与服饰，不改变头肩构图，不增加场景或背景" if subject else "",
        STYLE_TAIL[style],
        _NO_TEXT_AVATAR,
    ]
    prompt = _join_sentences(parts)

    canonical = _canonical_request(
        kind="avatar", style_key=style, prompt=prompt,
        negative_prompt=NEGATIVE_AVATAR, size=AVATAR_SIZE, seed=seed,
        model=model, provider=provider, capabilities=capabilities,
    )
    return {
        "kind": "avatar",
        "prompt": prompt,
        "negative_prompt": NEGATIVE_AVATAR,
        "prompt_hash": _hash_request(_effective_canonical(canonical, capabilities)),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "style_key": style,
        "size": {"width": AVATAR_SIZE[0], "height": AVATAR_SIZE[1]},
        "seed": seed,
        "seed_source": seed_source,
        "candidate_seeds": [seed, _seed_for_candidate(seed, 1)],
        "model": model or None,
        "model_unbound": not bool(model),
        "provider": provider or None,
        "capabilities": capabilities,
        "watermark": False,
        "needs_scene": False,
        "uses_default_subject": not bool(subject),
        "sources": {
            "character_id": ch.id,
            "name": ch.name,
            "gender": gender, "age": age, "race": race,
            "look": look, "faction": faction, "persona": persona,
            "override": bool(subject),
            "book_theme": _clamp(story.get("genre"), 40),
        },
    }
