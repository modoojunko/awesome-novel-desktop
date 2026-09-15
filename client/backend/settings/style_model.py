"""style KV v2 归一边界（style-settings-v2 tasks 1.1）。

文字文风收敛为三区（role/rules/craft）＋few_shot_examples；旧键在读写边界归一：

- ``narrator_role`` / ``tone.pov`` → 拼进 role 尾注（视角此前四处重复，归一为一句）
- ``tone.techniques`` ＋ ``depiction_techniques``（dict/list 双态）→ craft 去重合并
- ``core_principles``（dict/list 双态）＋``possible_mistakes``＋``pacing_rules`` → rules
  （宁多勿丢：通用/风格特有由作者在 UI 手搬，机器不做语义拆分）
- ``tone.default_tone`` / ``tone.atmosphere`` / ``chapter_types`` 丢弃
  （氛围归题材蓝图；ADR-007「题材不注入基调」口径不变）

首次归一的原文落 ``_legacy_style``（world ``_legacy`` 先例）——回滚基准，渲染侧永不读。
PUT 走白名单（role/rules/craft/few_shot_examples），撤并键零写回由白名单天然保证。
"""

from __future__ import annotations

from settings.render import depiction_techniques_str, flatten_principles

# 白名单写键（PUT 只受理这些；撤并键零写回）
STYLE_WRITE_KEYS = ("role", "rules", "craft", "few_shot_examples")

_MAX_RULES = 100  # 模板全量归一（core_principles+possible_mistakes+pacing_rules≈58 条）不截断
_MAX_CRAFT = 50
_MAX_FEWSHOT = 3
_VALUE_MAX = 500

_LEGACY_KEYS = (
    "narrator_role",
    "tone",
    "core_principles",
    "possible_mistakes",
    "depiction_techniques",
    "pacing_rules",
    "chapter_types",
)


def _as_str_list(v) -> list[str]:
    """str/任意列表 → 去空白字符串列表。"""
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    """保序去重（含全空剔除）。"""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        x = str(x).strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _has_legacy_keys(raw: dict) -> bool:
    return any(k in raw for k in _LEGACY_KEYS)


def normalize_style(raw: dict) -> dict:
    """旧形状 → 三区新形状（幂等；未知键如 fatigue_words 原样保留）。"""
    if not isinstance(raw, dict):
        raw = {}
    role = str(raw.get("role", "") or "").strip()
    rules = _as_str_list(raw.get("rules"))
    craft = _as_str_list(raw.get("craft"))
    few = _as_str_list(raw.get("few_shot_examples"))[:_MAX_FEWSHOT]

    if _has_legacy_keys(raw):
        # 视角归一：narrator_role / tone.pov 拼进 role 尾注（分号连接，保序去重）
        tone = raw.get("tone") if isinstance(raw.get("tone"), dict) else {}
        pov = _as_str_list(tone.get("pov"))
        role_parts = [p for p in (role, str(raw.get("narrator_role", "") or "").strip(), *pov) if p]
        role = "；".join(dict.fromkeys(role_parts))
        # 约束归一：原则 + 易犯错误 + 节奏规则 → rules（宁多勿丢，作者手搬拆分）
        rules = rules + flatten_principles(raw.get("core_principles"))
        rules += _as_str_list(raw.get("possible_mistakes"))
        rules += _as_str_list(raw.get("pacing_rules"))
        # 手法归一：depiction_techniques（dict/list 双态渲染成行）+ tone.techniques
        tech_text = depiction_techniques_str({"depiction_techniques": raw.get("depiction_techniques")})
        tech_lines = [ln.lstrip("- ").strip() for ln in tech_text.splitlines() if ln.strip()]
        craft = craft + tech_lines + _as_str_list(tone.get("techniques"))
        # 归一后的 role 可能超长（多段拼接），按上限裁断
        role = role[:_VALUE_MAX]

    return {
        "role": role,
        "rules": _dedupe(rules)[:_MAX_RULES],
        "craft": _dedupe(craft)[:_MAX_CRAFT],
        "few_shot_examples": [x for x in few if x],
        **{k: v for k, v in raw.items() if k not in ("role", "rules", "craft", "few_shot_examples", *_LEGACY_KEYS)},
    }


def read_style(raw: dict) -> dict:
    """GET 边界：归一后剥离 `_legacy_style`（回滚基准不出门）。"""
    data = normalize_style(raw)
    data.pop("_legacy_style", None)
    return data


def put_style(raw: dict, body: dict) -> dict:
    """PUT 边界：白名单写 + 归一落底。

    - 首次迁移（存量含旧键且无留底）：原文落 ``_legacy_style``，归一后撤并键清源
      ——「作者下次保存即完成迁移」，未保存前文件原样不动（正向不降级）
    - body 只受理白名单键；其余键一律忽略（撤并键零写回）
    """
    if not isinstance(body, dict):
        body = {}
    merged = normalize_style(raw)
    if _has_legacy_keys(raw) and "_legacy_style" not in raw:
        merged.setdefault("_legacy_style", raw)
    # 兼容旧客户端整文档 PUT：body 含旧键时先归一 body 再落（迁移那次保存生效，
    # 此后文件已是 v2 形状，旧键不再回流）；新前端 payload 无旧键 → 纯白名单语义
    payload = normalize_style(body) if _has_legacy_keys(body) else {
        k: body[k] for k in STYLE_WRITE_KEYS if k in body
    }
    role = str(payload.get("role", merged.get("role", "")) or "").strip()
    merged["role"] = role[:_VALUE_MAX]
    for key, cap in (("rules", _MAX_RULES), ("craft", _MAX_CRAFT), ("few_shot_examples", _MAX_FEWSHOT)):
        incoming = payload.get(key)
        items = _dedupe(_as_str_list(incoming)) if incoming is not None else merged.get(key, [])
        merged[key] = [x[:_VALUE_MAX] for x in items[:cap]]
    return merged


async def append_anti_ai_words(root_path: str, words) -> int:
    """禁用词服务端追加（归一去重，跨全部分类查重；新词落 `distilled` 分类）。

    供两处调用：/settings/anti-ai/words 端点与蒸馏 commit——机器段只走服务端
    写入，前端面板保持人类整表写，杜绝 read-modify-write 竞态（评审 P0）。
    返回实际新增词数。
    """
    if not isinstance(words, list) or not words:
        return 0
    clean: list[str] = []
    seen: set[str] = set()
    for w in words[:50]:
        w = str(w).strip()
        if not w:
            continue
        k = w.casefold()
        if k not in seen:
            seen.add(k)
            clean.append(w[:50])
    if not clean:
        return 0

    from filesystem.paths import KEY_TO_PATH
    from filesystem.storage import get_storage

    storage = get_storage()
    data = await storage.read_yaml(root_path, KEY_TO_PATH["anti-ai"]) or {}
    fatigue = data.get("fatigue_words_zh")
    if not isinstance(fatigue, dict):
        fatigue = {}
    existing = {
        str(w).strip().casefold()
        for cat in fatigue.values()
        if isinstance(cat, list)
        for w in cat
    }
    bucket = fatigue.get("distilled")
    if not isinstance(bucket, list):
        bucket = []
    added = 0
    for w in clean:
        if w.casefold() not in existing:
            bucket.append(w)
            existing.add(w.casefold())
            added += 1
    if added:
        fatigue["distilled"] = bucket
        data["fatigue_words_zh"] = fatigue
        await storage.write_yaml(root_path, KEY_TO_PATH["anti-ai"], data)
    return added
