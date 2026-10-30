"""卷节奏（c-volume-pacing）——章层小循环的单源。

三层模型：题材映射给起点（预填默认的来源）→ 书级默认（设定页可改，存
book-prefs）→ 卷配置（卷页签精调，最终以卷为准）。段边界**不落库**：拍位由
「章号 ÷ 每段几章」公式实时推导（末段吸收余数），加删章自动一致——
逐段落库与漂移重排是 v2 的事。

- 六套预设为本模块常量（共享，SHALL NOT 复制进题材数据；题材只持「子类/大类
  → 套路键」映射）。文案＝作家语言（套路/段/步），过实现词汇黑名单。
- 归一与 clamp 单源：步数 2–6、每段 1–30、步名 ≤12／步任务 ≤80；前端镜像
  ``src/lib/volumePacing.ts``（公式与展示文案，parity 对拍）。
- **注入按配置存在推导**：``effective_of`` 只读「卷上已保存且可解析的配置 →
  书级默认」，**不看 planned**（未排段也注入）；题材映射只驱动页签展示预填
  （display_prefill），不触发任何拍位注入（未配置的书行为与升级前逐字一致）。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select

# ── 六套预设（共享常量；文案与 docs/design-c/drafts 原型逐字同源） ──────────

STEPS_MIN = 2
STEPS_MAX = 6
STEP_NAME_MAX = 12
STEP_TASK_MAX = 80
LEN_MIN = 1
LEN_MAX = 30

PACING_PRESETS: dict[str, dict[str, Any]] = {
    "upgrade": {
        "key": "upgrade",
        "label": "升级套路",
        "sub": "遇麻烦 → 解决 → 变强",
        "steps_len": 3,
        "warn_len": 6,
        "hint": "3–5 章最稳；拖过 5 章，读者会等疲。",
        "steps": [
            {"n": "遇麻烦", "t": "一个主角眼下对付不了的麻烦当场砸下来；第一段剧情里，金手指露头。"},
            {"n": "用金手指解决", "t": "真刀真枪把麻烦解掉——怎么出手、付出什么、局面怎么松，都写实。"},
            {"n": "变强收尾", "t": "变强落到实处（境界、家底、名分），交代下一步；结尾埋下一段的新麻烦。"},
        ],
        "ch1_extra": "开场即危机，金手指当场觉醒，世界观跟着剧情带出来——前三章内给到第一个爽点。",
    },
    "case": {
        "key": "case",
        "label": "破案套路",
        "sub": "案发 → 查案 → 反转",
        "steps_len": 12,
        "warn_len": 16,
        "hint": "一案一段剧情；收案别拖过 15 章。",
        "steps": [
            {"n": "案发", "t": "案子当场发生，利害落到主角头上；不写背景铺陈。"},
            {"n": "查案", "t": "现场和证物过一遍手，抓住第一条线头。"},
            {"n": "锁定嫌疑人", "t": "圈出两三个可疑的人，个个有动机。"},
            {"n": "层层排查", "t": "线索排掉又翻起来；中途至少认错一次方向。"},
            {"n": "真相反转", "t": "真凶落定，和开头想的不一样；余波一句话收。"},
        ],
        "ch1_extra": "案子必须当场发生。",
    },
    "episodic": {
        "key": "episodic",
        "label": "日常小故事",
        "sub": "日常 → 小事 → 暖收尾",
        "steps_len": 4,
        "warn_len": 7,
        "hint": "3–6 章一个小故事，收尾要暖。",
        "steps": [
            {"n": "日常开场", "t": "从几件相处小事切入，一眼看出这群人怎么相处。"},
            {"n": "事情上门", "t": "一件不大、但躲不掉的事找上门。"},
            {"n": "把事办了", "t": "各展所长把事办成；过程比结果要紧。"},
            {"n": "暖收尾", "t": "落回日常，关系比开场更近一步。"},
        ],
        "ch1_extra": "把主要角色的日常关系立起来。",
    },
    "romance": {
        "key": "romance",
        "label": "感情拉扯",
        "sub": "靠近 → 考验 → 更近一步",
        "steps_len": 5,
        "warn_len": 9,
        "hint": "4–8 章一轮；别反复用同一种误会。",
        "steps": [
            {"n": "靠近", "t": "一次具体的相处，两人比上一段更近。"},
            {"n": "考验", "t": "误会、外来的压力或旧伤发作，把刚近的一步推开。"},
            {"n": "表态", "t": "有人先低头、先说实话；最重的话最短。"},
            {"n": "更近一步", "t": "关系落在一个看得见的新状态：一个称呼、一件信物、一次同路。"},
        ],
        "ch1_extra": "两人以错位的方式相遇。",
    },
    "level": {
        "key": "level",
        "label": "闯关套路",
        "sub": "进关 → 受挫 → 通关",
        "steps_len": 6,
        "warn_len": 11,
        "hint": "4–10 章一关；关里必须真栽一次。",
        "steps": [
            {"n": "进关", "t": "目标、规矩、时限当场亮清楚。"},
            {"n": "栽跟头", "t": "按老打法真失败一次，代价看得见。"},
            {"n": "找到打法", "t": "从失败里翻出正解，备好最后一搏。"},
            {"n": "通关结算", "t": "过关，奖励和下一个入口一起给。"},
        ],
        "ch1_extra": "灾变或入局的第一击当场落下。",
    },
    "event": {
        "key": "event",
        "label": "大势争斗",
        "sub": "布局 → 相撞 → 新格局",
        "steps_len": 8,
        "warn_len": 13,
        "hint": "6–12 章一轮；每轮收在格局变化上。",
        "steps": [
            {"n": "布局落子", "t": "各方把子放到桌上；主角这一手要让读者看见。"},
            {"n": "摩擦升级", "t": "试探变成正面冲突，回不了头。"},
            {"n": "正面相撞", "t": "主力对决，胜负落在先前埋下的一手上。"},
            {"n": "胜后新格局", "t": "输家退场、规矩改写；赢家也付出代价。"},
        ],
        "ch1_extra": "主角以当下身份卷进第一场博弈。",
    },
}

DEFAULT_PRESET_KEY = "upgrade"

# 题材（theme_catalog 大类名）→ 套路键。子类精确命中优先（GENRE_SUB_PRESET_MAP）。
GENRE_PRESET_MAP: dict[str, str] = {
    "都市": "upgrade",
    "年代文": "episodic",
    "乡土/乡村": "episodic",
    "悬疑": "case",
    "刑侦/现实犯罪": "case",
    "校园长篇": "episodic",
    "谍战": "event",
    "军事": "event",
    "体育": "level",
    "美食": "episodic",
    "正史历史小说": "event",
    "架空古王朝": "event",
    "穿越历史": "event",
    "仙侠/修真": "upgrade",
    "玄幻": "upgrade",
    "志怪/民俗灵异": "case",
    "西式奇幻": "upgrade",
    "科幻": "event",
    "末世/废土": "level",
    "无限流": "level",
    "游戏文": "level",
}

# 子类精确映射（覆盖大类默认；键＝(大类名, 子类名)）
GENRE_SUB_PRESET_MAP: dict[tuple[str, str], str] = {
    ("都市", "都市情感"): "romance",
    ("都市", "家庭伦理"): "romance",
    ("都市", "商战"): "event",
    ("都市", "市井烟火"): "episodic",
    ("都市", "都市生活"): "episodic",
}


def preset_for_genre(theme: str | None, sub_genre: str | None = None) -> str:
    """题材 → 套路键：子类精确命中 → 大类 → 兜底升级套路。未知名照兜底。"""
    if sub_genre:
        key = GENRE_SUB_PRESET_MAP.get((theme or "", sub_genre))
        if key:
            return key
    return GENRE_PRESET_MAP.get(theme or "", DEFAULT_PRESET_KEY)


def preset_or_default(key: Any) -> dict[str, Any]:
    """套路键 → 预设；非法/未知键兜底升级套路（不抛错，配置面已 clamp）。"""
    return PACING_PRESETS.get(str(key or ""), PACING_PRESETS[DEFAULT_PRESET_KEY])


# ── 归一（clamp 单源；配置面与 API 兜底共用） ─────────────────────────────


def _clamp_len(value: Any, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(LEN_MIN, min(LEN_MAX, n))


def normalize_steps(raw: Any, preset_key: str) -> list[dict[str, str]]:
    """步表归一：2–6 步、步名 ≤12、任务 ≤80；不足/非法回落该预设默认步表。"""
    preset = preset_or_default(preset_key)
    if not isinstance(raw, list):
        return [dict(s) for s in preset["steps"]]
    steps: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        n = str(item.get("n") or "").strip()[:STEP_NAME_MAX]
        t = str(item.get("t") or "").strip()[:STEP_TASK_MAX]
        if n:
            steps.append({"n": n, "t": t})
    if len(steps) < STEPS_MIN:
        return [dict(s) for s in preset["steps"]]
    return steps[:STEPS_MAX]


def normalize_pacing_config(raw: Any) -> dict[str, Any] | None:
    """卷列原文 → 归一配置；空/形状非法 → None（＝未配置，注入全关）。"""
    if not isinstance(raw, dict) or not raw:
        return None
    preset_key = str(raw.get("preset") or "")
    if preset_key not in PACING_PRESETS:
        return None
    preset = PACING_PRESETS[preset_key]
    steps = normalize_steps(raw.get("steps"), preset_key)
    try:
        ch1_on = bool(raw.get("ch1_extra_on"))
    except Exception:  # noqa: BLE001 — 脏值按关处理
        ch1_on = False
    ch1_extra = str(raw.get("ch1_extra") or "").strip()[:STEP_TASK_MAX]
    return {
        "preset": preset_key,
        "steps_len": _clamp_len(raw.get("steps_len"), int(preset["steps_len"])),
        "steps": steps,
        "ch1_extra_on": ch1_on,
        "ch1_extra": ch1_extra,
        "planned": bool(raw.get("planned")),
    }


def build_config(
    preset_key: str, steps_len: int, *, ch1_extra_on: bool = False,
    ch1_extra: str = "", planned: bool = False, steps: list | None = None,
) -> dict[str, Any]:
    """按预设构造配置（预设带默认步表与开篇句；调用方可覆盖）。"""
    preset = preset_or_default(preset_key)
    return normalize_pacing_config(
        {
            "preset": preset["key"],
            "steps_len": steps_len,
            "steps": steps if steps is not None else preset["steps"],
            "ch1_extra_on": ch1_extra_on or bool(ch1_extra),
            "ch1_extra": ch1_extra or (preset["ch1_extra"] if ch1_extra_on else ""),
            "planned": planned,
        }
    )


# ── 段表与拍位（公式推导；段边界不落库） ──────────────────────────────────


def segment_plan(target: int, steps_len: int) -> dict[str, int]:
    """段表口径：段数＝max(1, ⌊目标÷每段⌋)，末段吸收余数。

    章数目标未知（0/None）时按 1 段处理——拍位仍可查（整卷一段），展示层
    自行决定是否隐藏段数口径。
    """
    target = max(0, int(target or 0))
    steps_len = max(1, int(steps_len or 1))
    if target == 0:
        return {"n": 1, "rem": 0, "last_from": 1, "last_to": 0}
    n = max(1, target // steps_len)
    rem = target % steps_len
    return {"n": n, "rem": rem, "last_from": (n - 1) * steps_len + 1, "last_to": target}


def beat_of(chapter_no: int, config: dict[str, Any] | None, chapter_target: int | None) -> dict[str, Any] | None:
    """章号 → 拍位；未配置/越界 → None（下游按无拍位口径照常工作）。"""
    config = normalize_pacing_config(config)
    if not config or chapter_no is None or int(chapter_no) < 1:
        return None
    target = int(chapter_target or 0)
    if target <= 0:
        return None
    n = max(1, target // config["steps_len"])
    if chapter_no > target:
        return None
    seg = min(n, (chapter_no - 1) // config["steps_len"] + 1)
    step_idx = (chapter_no - 1) % config["steps_len"]
    steps = config["steps"]
    step = steps[min(step_idx, len(steps) - 1)]
    return {
        "seg": seg,
        "step_idx": step_idx + 1,
        "step_name": step["n"],
        "step_task": step["t"],
    }


# ── 预填链（展示用）与生效解析（注入用；卷列 → 书默认，不看 planned） ──────


def book_pacing_default(doc: Any) -> dict[str, Any] | None:
    """book-prefs KV 原文 → 书级默认（套路键＋每段几章）；未设 → None。"""
    if not isinstance(doc, dict):
        return None
    key = str(doc.get("pacing_preset") or "")
    if key not in PACING_PRESETS:
        return None
    return {"preset": key, "steps_len": _clamp_len(doc.get("pacing_steps_len"), int(PACING_PRESETS[key]["steps_len"]))}


def prefill_chain(
    prev_pacing: Any,
    book_default: dict[str, Any] | None,
    theme: str | None,
    sub_genre: str | None,
) -> dict[str, Any] | None:
    """展示预填链：上一卷配置 → 书级默认 → 题材映射 → 兜底升级套路。

    仅驱动页签展示（「已按题材预填/继承上一卷」）；注入走 effective_of
    （卷列 → 书默认，不看 planned），题材映射不参与注入。
    """
    prev = normalize_pacing_config(prev_pacing)
    if prev:
        # 展示预填不继承「已排」：planned 只属于卷列已保存的配置
        return {**prev, "planned": False}
    if book_default:
        preset = preset_or_default(book_default["preset"])
        return build_config(book_default["preset"], book_default["steps_len"], ch1_extra_on=True)
    key = preset_for_genre(theme, sub_genre)
    preset = preset_or_default(key)
    return build_config(key, int(preset["steps_len"]), ch1_extra_on=True)


# ── 注入助手（各生成点共用；注入按「配置存在」推导，不看 planned） ─────────


def effective_of(
    config: Any,
    book_default: dict[str, Any] | None,
    volume_no: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """生效配置解析（注入与页签同源）：卷列 → 书级默认 → 空。

    返回 ``(config, source)``，source ∈ ``volume | book | None``。书默认分支必须
    用 build_config 补齐步表与「第 1 章额外交代」开关（第 1 卷开、其余卷关），
    SHALL NOT 把只有 {preset, steps_len} 的书默认裸对象当完整配置返回。
    题材映射只驱动展示预填，不进本解析。
    """
    normalized = normalize_pacing_config(config)
    if normalized:
        return normalized, "volume"
    if book_default:
        built = build_config(
            book_default["preset"],
            book_default["steps_len"],
            ch1_extra_on=(int(volume_no) == 1),
        )
        if built:
            return built, "book"
    return None, None


async def resolve_config(db: Any, project, volume_no: int) -> dict[str, Any] | None:
    """注入用配置解析：卷列节奏 → 书级默认（book-prefs）→ None。

    题材映射只驱动页签展示预填，SHALL NOT 进注入链；旧书（书默认未设且卷列空）
    返回 None＝行为同升级前（零变化承诺）。与 effective_of 同源，不看 planned。"""
    from models.volume import Volume

    row = (
        await db.execute(
            select(Volume).where(
                Volume.project_id == project.id, Volume.volume_no == int(volume_no)
            )
        )
    ).scalar_one_or_none()
    config = None
    if row is not None and row.pacing_json:
        try:
            config = normalize_pacing_config(json.loads(row.pacing_json))
        except (ValueError, TypeError):
            config = None
    if config:
        return config
    if not getattr(project, "root_path", None):
        return None
    from filesystem.paths import BOOK_PREFS_PATH
    from filesystem.storage import get_storage

    try:
        prefs = await get_storage().read_yaml(project.root_path, BOOK_PREFS_PATH) or {}
    except Exception:  # noqa: BLE001 — 读不到书默认按未设（拍位不注入）
        return None
    effective, _source = effective_of(None, book_pacing_default(prefs), int(volume_no))
    return effective


async def beat_context(
    db: Any,
    project_id: str,
    volume_no: int,
    chapter_no: int,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """章 → 拍位上下文；无卷列节奏且无书级默认 / 越界 → None（下游按无拍位口径照常）。

    返回 {seg, step_idx, step_name, task, preset_label, steps_len[, ch1_extra]}；
    task 组好「本循环第 K 步 · 步名——任务句」直接可进素材。
    ``config`` 给定时跳过 resolve_config（调用方已解析；用于锚点预览与注入同源）。
    """
    from models.project import Novel as NovelModel
    from models.volume import Volume

    if chapter_no is None or int(chapter_no) < 1:
        return None
    project = await db.get(NovelModel, str(project_id))
    if project is None:
        return None
    if config is None:
        config = await resolve_config(db, project, int(volume_no))
    if config is None:
        return None
    target = 0
    row = (
        await db.execute(
            select(Volume).where(
                Volume.project_id == project.id, Volume.volume_no == int(volume_no)
            )
        )
    ).scalar_one_or_none()
    target = int(row.chapter_target or 0) if row is not None else 0
    if target <= 0:
        return None
    beat = beat_of(int(chapter_no), config, target)
    if beat is None:
        return None
    preset = preset_or_default(config["preset"])
    out: dict[str, Any] = {
        "seg": beat["seg"],
        "step_idx": beat["step_idx"],
        "step_name": beat["step_name"],
        "task": f"本循环第 {beat['step_idx']} 步 · {beat['step_name']}——{beat['step_task']}",
        "step_task": beat["step_task"],
        "preset_label": preset["label"],
        "steps_len": config["steps_len"],
    }
    if int(volume_no) == 1 and int(chapter_no) == 1 and config.get("ch1_extra_on"):
        out["ch1_extra"] = config.get("ch1_extra") or preset.get("ch1_extra") or ""
    return out


def pacing_fingerprint(beat: dict[str, Any] | None, effective: bool) -> str:
    """抽卡会话的拍位指纹：覆盖实际会进素材的拍位信息。

    含 step_idx/step_name/step_task/ch1_extra 与「是否有生效配置」——只改任务句、
    只改第 1 章额外交代、目标清空导致拍位消失，都必须让旧批过期。
    """
    payload: dict[str, Any] = {"effective": bool(effective), "beat": None}
    if beat:
        payload["beat"] = {
            "step_idx": beat.get("step_idx"),
            "step_name": beat.get("step_name"),
            "step_task": beat.get("step_task"),
            "ch1_extra": beat.get("ch1_extra") or "",
        }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()[:16]
