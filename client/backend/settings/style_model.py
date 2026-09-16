"""style KV v2 归一边界（style-settings-v2 tasks 1.1）＋禁用词收编（banned-words-into-style）。

文字文风收敛为三区（role/rules/craft）＋few_shot_examples；旧键在读写边界归一：

- ``narrator_role`` / ``tone.pov`` → 拼进 role 尾注（视角此前四处重复，归一为一句）
- ``tone.techniques`` ＋ ``depiction_techniques``（dict/list 双态）→ craft 去重合并
- ``core_principles``（dict/list 双态）＋``possible_mistakes``＋``pacing_rules`` → rules
  （宁多勿丢：通用/风格特有由作者在 UI 手搬，机器不做语义拆分）
- ``tone.default_tone`` / ``tone.atmosphere`` / ``chapter_types`` 丢弃
  （氛围归题材蓝图；ADR-007「题材不注入基调」口径不变）

禁用词收编（banned-words-into-style）：

- 白名单新增 ``banned_words``（词表，≤100）与 ``tic_patterns``（句式规则，≤20）
- 幽灵键 ``fatigue_words``（6.0e 迁移遗物）归一并入 banned_words 后剥离，GET 不再出门
- 存量 anti-ai KV 经 ``migrate_anti_ai_into_style`` 一次性迁入（完成标记位幂等；
  原键原样保留——回滚安全＋导出/导入兜底，清理属后续版本）
- 所有禁用词消费方（写章组装/程序化体检/辅助注入/AI 体检）一律走
  ``read_style_migrated`` 统一读路径，不绕过迁移

首次归一的原文落 ``_legacy_style``（world ``_legacy`` 先例）——回滚基准，渲染侧永不读。
PUT 走白名单（STYLE_WRITE_KEYS），撤并键零写回由白名单天然保证。
"""

from __future__ import annotations

import unicodedata

from settings.render import depiction_techniques_str, flatten_principles

# 白名单写键（PUT 只受理这些；撤并键零写回）
STYLE_WRITE_KEYS = (
    "role",
    "rules",
    "craft",
    "few_shot_examples",
    "banned_words",
    "tic_patterns",
)

_MAX_RULES = 100  # 模板全量归一（core_principles+possible_mistakes+pacing_rules≈58 条）不截断
_MAX_CRAFT = 50
_MAX_FEWSHOT = 3
_MAX_BANNED = 100  # 禁用词上限（模板 37 词＋蒸馏 ≤50＋手填余量）
_MAX_TICS = 20  # 句式规则上限（模板 8 条）
_VALUE_MAX = 500
_BANNED_WORD_MAX = 50
_TIC_PATTERN_MAX = 200
_TIC_TEXT_MAX = 200
_TIC_SEVERITIES = ("high", "medium", "low")

# 迁移完成标记：存于文风 KV 文档（非白名单键，随文档持久化），GET 边界剥离
BANNED_MIGRATED_KEY = "_banned_migrated"
# anti-ai 原键路径：键映射保留在 PATH_TO_KEY（迁移读＋导出/导入兜底）；读取仅限迁移函数
ANTI_AI_PATH = "settings/anti-ai.yaml"

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


def _word_key(w: str) -> str:
    """词归一键：NFKC（半/全角折叠）＋casefold——兑现 style-settings-v2 spec 的归一口径。"""
    return unicodedata.normalize("NFKC", str(w)).strip().casefold()


def _normalize_banned(v) -> list[str]:
    """任意形状 → 去空白字符串词表（单条截 50 字）。"""
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    out = []
    for w in v:
        w = str(w).strip()[:_BANNED_WORD_MAX]
        if w:
            out.append(w)
    return out


def _normalize_tics(v) -> list[dict]:
    """句式规则专用归一：dict 列表（pattern/name/threshold/severity/description）。

    pattern 去空白非空、按 pattern 保序去重；threshold 整数化（非法落默认 3）；
    severity 白名单（非法降 medium）。字符串条目兼容为仅 pattern。
    """
    if not isinstance(v, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for item in v:
        if isinstance(item, str):
            item = {"pattern": item}
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("pattern", "") or "").strip()[:_TIC_PATTERN_MAX]
        if not pattern or pattern in seen:
            continue
        seen.add(pattern)
        try:
            threshold = max(1, int(item.get("threshold", 3)))
        except (TypeError, ValueError):
            threshold = 3
        severity = str(item.get("severity", "") or "medium")
        if severity not in _TIC_SEVERITIES:
            severity = "medium"
        out.append(
            {
                "pattern": pattern,
                "name": str(item.get("name", "") or "").strip()[:_TIC_TEXT_MAX],
                "threshold": threshold,
                "severity": severity,
                "description": str(item.get("description", "") or "").strip()[:_TIC_TEXT_MAX],
            }
        )
    return out


def _has_legacy_keys(raw: dict) -> bool:
    return any(k in raw for k in _LEGACY_KEYS)


def normalize_style(raw: dict) -> dict:
    """旧形状 → 三区＋禁用词新形状（幂等）。

    幽灵键 fatigue_words 并入 banned_words 后剥离（不进 _LEGACY_KEYS——避免误触发
    _legacy_style 整文档留底）；未知键原样保留（含迁移完成标记，GET 边界剥离）。
    """
    if not isinstance(raw, dict):
        raw = {}
    role = str(raw.get("role", "") or "").strip()
    rules = _as_str_list(raw.get("rules"))
    craft = _as_str_list(raw.get("craft"))
    few = _as_str_list(raw.get("few_shot_examples"))[:_MAX_FEWSHOT]
    # 禁用词：显式键＋幽灵键同批归一去重
    banned = _normalize_banned(raw.get("banned_words")) + _normalize_banned(raw.get("fatigue_words"))
    banned_seen: set[str] = set()
    banned_out: list[str] = []
    for w in banned:
        k = _word_key(w)
        if k not in banned_seen:
            banned_seen.add(k)
            banned_out.append(w)
    tics = _normalize_tics(raw.get("tic_patterns"))

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
        "banned_words": banned_out[:_MAX_BANNED],
        "tic_patterns": tics[:_MAX_TICS],
        **{
            k: v
            for k, v in raw.items()
            if k
            not in (
                "role",
                "rules",
                "craft",
                "few_shot_examples",
                "banned_words",
                "tic_patterns",
                "fatigue_words",
                *_LEGACY_KEYS,
            )
        },
    }


def read_style(raw: dict) -> dict:
    """GET 边界：归一后剥离 `_legacy_style` 与迁移完成标记（内部簿记不出门）。"""
    data = normalize_style(raw)
    data.pop("_legacy_style", None)
    data.pop(BANNED_MIGRATED_KEY, None)
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
    for key, cap in (
        ("rules", _MAX_RULES),
        ("craft", _MAX_CRAFT),
        ("few_shot_examples", _MAX_FEWSHOT),
    ):
        incoming = payload.get(key)
        items = _dedupe(_as_str_list(incoming)) if incoming is not None else merged.get(key, [])
        merged[key] = [x[:_VALUE_MAX] for x in items[:cap]]
    # 禁用词：专用归一，不得走字符串助手（tic_patterns 是 dict 列表，评审 P1-6）
    incoming = payload.get("banned_words")
    if incoming is not None:
        seen: set[str] = set()
        out: list[str] = []
        for w in _normalize_banned(incoming):
            k = _word_key(w)
            if k not in seen:
                seen.add(k)
                out.append(w)
        merged["banned_words"] = out[:_MAX_BANNED]
    incoming = payload.get("tic_patterns")
    if incoming is not None:
        merged["tic_patterns"] = _normalize_tics(incoming)[:_MAX_TICS]
    return merged


async def migrate_anti_ai_into_style(root_path: str) -> None:
    """存量 anti-ai KV → 文风 KV 一次性迁移（banned-words-into-style design D3）。

    - 幂等：完成后在文风 KV 落 ``BANNED_MIGRATED_KEY`` 标记，标记在即跳过——
      作者此后对 banned_words 的删改不会被回灌
    - anti-ai 原键**原样保留不删不改**：回滚版本读原键恢复全部能力，
      导出/导入兜底不受影响；清理属后续版本独立清理项
    - 无 anti-ai 数据（新书）只落标记，零改写
    """
    from filesystem.storage import get_storage

    raw = await get_storage().read_yaml(root_path, "settings/writing-style.yaml") or {}
    if not isinstance(raw, dict):
        raw = {}
    if raw.get(BANNED_MIGRATED_KEY):
        return
    anti = await get_storage().read_yaml(root_path, ANTI_AI_PATH) or {}
    if not isinstance(anti, dict):
        anti = {}
    words: list[str] = []
    fw = anti.get("fatigue_words_zh")
    if isinstance(fw, dict):
        for cat in fw.values():
            if isinstance(cat, list):
                words.extend(str(w) for w in cat if str(w).strip())
    tics = anti.get("structural_tic_patterns")
    tics = tics if isinstance(tics, list) else []

    extra: dict = {}
    if words:
        extra["banned_words"] = words
    if tics:
        extra["tic_patterns"] = tics
    merged = normalize_style({**raw, **extra})
    merged[BANNED_MIGRATED_KEY] = True
    await get_storage().write_yaml(root_path, "settings/writing-style.yaml", merged)


async def read_style_migrated(root_path: str) -> dict:
    """统一迁移感知读路径：先确保迁移完成，再返回归一后的文风文档（GET 契约形状）。

    所有禁用词消费方（写章组装/程序化体检/辅助注入/AI 体检）与 GET 端点一律经此
    取文风——存量书不进设定页直接体检/写章也有迁移兜底（评审 P1：体检假通过窗口）。
    """
    await migrate_anti_ai_into_style(root_path)
    from filesystem.storage import get_storage

    raw = await get_storage().read_yaml(root_path, "settings/writing-style.yaml") or {}
    return read_style(raw)


async def append_banned_words(root_path: str, words) -> int:
    """禁用词服务端追加（原 append_anti_ai_words 改目标）：蒸馏学到的词写入文风 KV
    的 ``banned_words``，NFKC＋大小写归一后跨词表去重；满表静默丢弃返回实际新增数。

    机器段只走服务端写入，人类整表写走 PUT 白名单。注意共址后竞态语义（design D4）：
    人类保存＝以所见为准覆盖，commit 后由前端回读合并两键兜住旧快照覆盖丢词。
    """
    if not isinstance(words, list) or not words:
        return 0
    clean: list[str] = []
    seen: set[str] = set()
    for w in words[:50]:
        w = str(w).strip()[:_BANNED_WORD_MAX]
        if not w:
            continue
        k = _word_key(w)
        if k not in seen:
            seen.add(k)
            clean.append(w)
    if not clean:
        return 0

    from filesystem.storage import get_storage

    merged = normalize_style(
        await get_storage().read_yaml(root_path, "settings/writing-style.yaml") or {}
    )
    existing = {_word_key(w) for w in merged.get("banned_words", [])}
    added = 0
    for w in clean:
        if len(merged["banned_words"]) >= _MAX_BANNED:
            break
        k = _word_key(w)
        if k in existing:
            continue
        merged["banned_words"].append(w)
        existing.add(k)
        added += 1
    if added:
        await get_storage().write_yaml(root_path, "settings/writing-style.yaml", merged)
    return added
