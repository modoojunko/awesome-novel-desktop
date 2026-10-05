"""章纲人物精盘 · AI 链路（c-character-intro）。

- 盘点：POST /api/novels/{id}/chapters/{ref}/cast/ai-review（免费只读——`require_novel_model`
  例外，照 ai-selfcheck 先例；输入＝请求体表单快照，不读库回退）
- 抽卡：POST /api/novels/{id}/chapters/{ref}/cast/ai-draw（PRO 生成类——`require_ai_access`）

复用纪律：生成/解析/计量走 volumes.ai_plan 既有链路（_generate/_parse_json/_render），
等级走 chapters.ai_plan._grades/_ranks_ok（维名＋S 阈值双参数化：本卡 3 维＝2、拆章 4 维＝3）。
本模块只加：表单快照素材装配、闭集归一化（分流＋否定护栏）、提案卡对拍（decision 10）
与重试阶梯（MAX_ATTEMPTS=3；exclude 撞车重抽不降温）。

输出骨架两张表（design 决策 9）：模型出 idx/echo/verdict/who/as/why/gap{need,why_not_old,suggest}
（cast_draw：axis/name/duty/persona/entrance/exit_kind/exit_note/ranks/reasons，why_not_old 不输出）；
服务端加 defaulted/gapId/quota/hints/warnings、grade（服务端算，模型不出等级字母）。
"""

from __future__ import annotations

import difflib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_local.deps import (
    ai_feature,
    get_current_user,
    require_ai_access,
    require_novel_model,
)
from db import get_db
from novels.service import get_novel
from prompts import load_layers
from settings import character_service
from volumes.ai_plan import _book_material, _generate, _parse_json, _render
from workflow.engine import _validate_ref, strip_suffix

router = APIRouter(
    prefix="/api/novels/{project_id}/chapters/{chapter_ref}/cast", tags=["chapter-cast"]
)

# ── 闭集单源（人话标签即取值；与前端 lib/castReviewApi.ts parity 对拍）────────
VERDICTS = ("老角色能演", "不起名也行", "缺一个新角色")
VERDICT_OLD, VERDICT_UNNAMED, VERDICT_NEW = VERDICTS
SUGGESTS = ("加人", "改段", "延后")
SUGGEST_DEFAULT = "加人"
AXES = ("身份", "关系", "功能")
EXIT_KINDS = ("章内退场", "本卷退场", "申请常驻")
CAST_DIMS = ("合不合适", "差别在哪", "好不好落地")
GRADES = ("S", "A", "B")
ROW_UNJUDGED = "这一段没判出来"  # 出界丢行后的警示行（不静默少行、不重抽）

MAX_ATTEMPTS = 3  # 重试封顶（照拆章）
SIM_LIMIT = 0.6  # 人设句相似阈值（沿用 one_liner/spine 先例）
GRADE_S_MIN = 2  # 3 维提案卡的 S 阈值（拆章 4 维＝3——共用函数不共用阈值）

_REVIEW_TEMP = 0.2
_REVIEW_RETRY_TEMP = 0.1
_DRAW_TEMP = 0.7
_DRAW_RETRY_TEMP = 0.3  # 结构性重试降温；exclude 撞车重抽维持 0.7
_REVIEW_MAX_TOKENS = 4096
_DRAW_MAX_TOKENS = 8192

# 字段界（clamp 不拒收；why_not_old 例外——抽卡侧服务端直抄不 clamp）
_ECHO_LEN = 60
_WHY_LEN = 30
_AS_LEN = 20
_WHO_LEN = 20
_NEED_LEN = 40
_WHY_NOT_OLD_LEN = 40
_NAME_LEN = 12
_DUTY_LEN = 30
_PERSONA_LEN = 60
_ENTRANCE_LEN = 40
_EXIT_NOTE_LEN = 40
_REASON_LEN = 20
_NOTE_LEN = 60
_LINE_LEN = 200  # 剧情条目展示界（与存储预算同值）
_MAIN_LEN = 100  # 主线截取界（句读截断）

_SENT_ENDS = "。！？；…"
_EDGE_PUNCT = "。！？；…、，,．;：:？！?!…—–-·「」『』“”‘’\"'（）()《》【】〔〕 \t\r\n　"
# 否定护栏词表（命中位前二字窗口；单字窗挡不住「不是加人」——决策 11 二轮终审）
_NEGATIONS = ("不能", "不必", "不是", "未必", "不", "没", "非", "无", "未", "别", "莫")

_RETAIN_LABELS = (
    ("梗概", "summary"),
    ("挑战", "challenge"),
    ("阶段", "plot_stage"),
    ("章末落点", "ladder_exit"),
)

# 重试喂回尾块（进 user 段末尾；system 各轮恒定——保供应商 prompt 缓存）
_RETRY_BLOCK = "=====【上次失败原因】====="

# exclude 中性禁令段（decision 10 钉词源；「换结构上不同」措辞退役）
_EXCLUDE_RULE = (
    "轴照旧三张各出一张（身份／关系／功能），轴可以再用、必须再用；禁的是同一条人物路子："
    "同一个轴上一句人设与上面是同一路人的（或换个称呼还是那个人的），不要再出。"
    "换路子要换在人身上，但仍要贴合【缺的人】——不要为了不同而不同。"
)
_NONE_TEXT = "（本次无）"


# ═══════════════ 请求体（表单快照；照 SelfcheckBody 先例，不读库回退） ═══════════════


class CastReviewBody(BaseModel):
    """章纲表单快照：留存格＋剧情条目＋出场名单（3s 自动保存未落库也不漏）。"""

    summary: str = ""
    challenge: str = ""
    plot_stage: str = ""
    ladder_exit: str = ""
    plot_items: list[str] = Field(default_factory=list, max_length=24)
    characters: list[str] = Field(default_factory=list, max_length=80)
    extra: str = Field(default="", max_length=200)  # 临时要求（可空；空渲染「（本次无）」）


class CastGapBody(BaseModel):
    """缺人行（抽卡缺口锚）：idx＝段锚；why_not_old 服务端直抄、不 clamp。"""

    idx: int | None = None
    need: str = ""
    why_not_old: str = ""


class CastExcludeItem(BaseModel):
    """重抽排除项（decision 10 自建形制——既有 ExcludeItem.line≤40 装不下人设句 ≤60）。"""

    axis: str = Field(default="", max_length=20)
    name: str = Field(default="", max_length=_NAME_LEN)
    persona: str = Field(default="", max_length=_PERSONA_LEN)


class CastDrawBody(BaseModel):
    gap: CastGapBody = Field(default_factory=CastGapBody)
    characters: list[str] = Field(default_factory=list, max_length=80)
    exclude: list[CastExcludeItem] = Field(default_factory=list, max_length=9)
    extra: str = Field(default="", max_length=200)


# ═══════════════ 闭集归一化（决策 11：分流＋否定护栏＋命中计数语义） ═══════════════


def _edge_strip(value) -> str:
    return str(value or "").strip().strip(_EDGE_PUNCT)


def _negated(text: str, pos: int) -> bool:
    """命中位前二字窗口内出现否定词 ⇒ 该命中作废（「不是加人」不得归一成「加人」）。"""
    win = text[max(0, pos - 2) : pos]
    return any(w in win for w in _NEGATIONS)


def normalize_closed(value, closed: tuple[str, ...], *, allow_substring: bool) -> str | None:
    """闭集归一：strip → 剥句读 → 精确 →（可选）唯一子串（带否定护栏）→ None（出界）。

    命中计数语义＝剥句读后按闭集全组计：跨值恰一命中且该值恰现一次才归一；
    否定护栏打掉的命中不计；≥2 值命中或同值多次按出界。
    2 字短值（suggest／差异轴）只做精确＋剥句读，不做子串兜底——
    「加人或改段」这类混入句宁可走缺省/出界，不猜。
    """
    s = _edge_strip(value)
    if not s:
        return None
    if s in closed:
        return s
    if not allow_substring:
        return None
    hits: dict[str, int] = {}
    for val in closed:
        cnt = 0
        start = 0
        while True:
            i = s.find(val, start)
            if i < 0:
                break
            if not _negated(s, i):
                cnt += 1
            start = i + len(val)
        if cnt:
            hits[val] = cnt
    if len(hits) == 1 and next(iter(hits.values())) == 1:
        return next(iter(hits))
    return None


def _clip_sentence(text, limit: int) -> str:
    """句读截断（照 clip_plot_item 手法）：截到最后一个句读点，末句不腰斩；无句读才硬截。"""
    t = str(text or "").strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    for i in range(len(cut) - 1, -1, -1):
        if cut[i] in _SENT_ENDS:
            return cut[: i + 1]
    return cut


# ═══════════════ 素材装配（裁剪子集：主线截取＋三个人名单块＋配额档位行） ═══════════════


def _quota_line(regime: str, *, draw: bool) -> str:
    """配额档位行（服务端按本卷已排章数派生；提示词只声明数值区间）。

    review 行尾钉「配额只影响建议的分寸，不得改变三分类判定」；
    draw 行尾钉「配额只影响建议分寸」（收紧期注明每章新增 1–3 约束的是申报）。
    """
    if regime == "open":
        head = "本卷配额档位：开卷期——本卷累计约 5–8 个有名有姓合适。"
    else:
        head = "本卷配额档位：收紧期——本章新增有名有姓约 1–3 个合适（约束的是申报）。"
    tail = "配额只影响建议分寸。" if draw else "配额只影响建议的分寸，不得改变三分类判定。"
    return head + tail


def _roster_brief(items: list[dict]) -> str:
    """人物全名单一行卡（含别名）。"""
    rows = sorted(items, key=lambda it: 0 if it.get("role") == "主角" else 1)
    out = []
    for it in rows:
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        aliases = [str(a).strip() for a in (it.get("aliases") or []) if str(a).strip()]
        head = f"{name}（别名：{'、'.join(aliases)}）" if aliases else name
        out.append(f"- {head}（{it.get('role') or ''}）：{str(it.get('persona') or '')[:80]}")
    return "\n".join(out) or "（人物表还是空的）"


def _seg_label(idx: int | None) -> str:
    return f"第 {idx + 1} 段" if idx is not None else "整章"


class _CastStats:
    """出场聚合（零新存储，全部派生）：当前章按快照并入（3s 未存名不漏）。

    - visits：无卡名字 → {(vol_no, chapter_no)}（软提示计数；同章多行只算一章）
    - vol_names：本卷出场名单去重名字数（含无卡名；配额计数）
    """

    def __init__(self) -> None:
        self.visits: dict[str, set[tuple[int, int]]] = {}
        self.vol_names: set[str] = set()

    def add(self, name: str, vol_no: int, ch_no: int, *, carded: bool, in_vol: bool) -> None:
        nm = str(name or "").strip()
        if not nm:
            return
        if in_vol:
            self.vol_names.add(nm)
        if carded:
            return
        self.visits.setdefault(nm, set()).add((vol_no, ch_no))


async def _cast_visit_rows(db: AsyncSession, project_id: str):
    """全书出场访问行（(vol_no, chapter_no, name)；剔 ghost 章）——软提示与配额的计数单源。"""
    from models.chapter import Chapter, ChapterCharacter
    from models.volume import Volume

    stmt = (
        select(Volume.volume_no, Chapter.chapter_no, ChapterCharacter.character_name)
        .join(Chapter, Chapter.id == ChapterCharacter.chapter_id)
        .join(Volume, Volume.id == Chapter.volume_id)
        .where(Chapter.project_id == project_id, Chapter.ghost_of.is_(None))
        .order_by(Volume.volume_no, Chapter.chapter_no)
    )
    return (await db.execute(stmt)).all()


async def _collect_cast_stats(
    db: AsyncSession,
    project_id: str,
    *,
    carded: set[str],
    vol_no: int,
    ch_no: int,
    snapshot: list[str],
) -> _CastStats:
    stats = _CastStats()
    for r_vol, r_ch, raw_name in await _cast_visit_rows(db, project_id):
        nm = str(raw_name or "").strip()
        if not nm:
            continue
        v, c = int(r_vol), int(r_ch)
        stats.add(nm, v, c, carded=nm in carded, in_vol=v == vol_no)
    for nm in snapshot:  # 当前章按快照并入（不覆盖库内行——「不漏」优先）
        stats.add(nm, vol_no, ch_no, carded=nm in carded, in_vol=True)
    return stats


def _cardless_brief(stats: _CastStats, vol_no: int) -> str:
    """无卡出场名单（本卷出现、未建卡）——与块题一致：只列本卷访问过的名字
    （跨卷口径＝「已经出现在 N 章」软提示，走 hints；终审 P2：别把别的卷出现的
    名字误标成「本章」）。"""
    lines = []
    for nm, seen in sorted(stats.visits.items()):
        chs = sorted(c for v, c in seen if v == vol_no)
        if not chs:
            continue
        lines.append(f"- {nm}（第{'、'.join(str(c) for c in chs)}章）")
    return "\n".join(lines)


def _cast_material(
    mat: dict,
    items: list[dict],
    *,
    row,
    snapshot: list[str],
    stats: _CastStats,
    banned: set[str],
    regime: str,
    draw: bool,
) -> str:
    """盘点/抽卡素材块（裁剪子集，不裸 dump known_entities）：
    主线（截取 ≤100 字）＋人物全名单（含别名）＋出场名单（快照）＋无卡名单（本卷）
    ＋（抽卡）【不要用这些名字】＋配额档位行。"""
    parts = [
        "【主线（截取）】\n" + (_clip_sentence(mat["fullstory"], _MAIN_LEN) or "（主线还没写）"),
        "【人物全名单（含别名）】\n" + _roster_brief(items),
        "【出场名单（本章）】\n"
        + ("\n".join(f"- {n}" for n in snapshot) or "（本章还没排出场角色）"),
        "【无卡出场名单（本卷出现、未建卡）】\n"
        + (_cardless_brief(stats, row.volume.volume_no) or "（没有）"),
    ]
    if draw:
        lines = "\n".join(f"- {n}" for n in sorted(b for b in banned if b))
        parts.append("【不要用这些名字】\n" + (lines or "（没有）"))
    parts.append("【本卷配额】\n" + _quota_line(regime, draw=draw))
    return "\n\n".join(parts)


async def _quota_regime(db: AsyncSession, vol) -> str:
    """配额档位（spec 配额软约束）：本卷已排章数 ≤3（或未达目标 1/3）＝开卷期，否则收紧期。"""
    from repositories import chapter_repo

    placed = len([c for c in await chapter_repo.list_by_volume(db, vol.id) if not c.ghost_of])
    target = vol.chapter_target or 0
    return "open" if (placed <= 3 or (target and placed * 3 < target)) else "tight"


# ═══════════════ 盘点输出契约（决策 11） ═══════════════


def _filter_who(values, known: set[str]) -> list[str]:
    """「演这段戏的角色」逐名对已知集合过滤——集合＝角色名∪别名∪出场名单∪无卡名
    （known_entities 里的势力/地点不在此集合：spec R2 名字来源域；素材禁令行同词）。"""
    out: list[str] = []
    for v in values if isinstance(values, list) else []:
        nm = str(v or "").strip()[:_WHO_LEN]
        if nm and nm in known and nm not in out:
            out.append(nm)
    return out[:6]


def _build_review_rows(
    parsed: dict | None, targets: list[tuple[int | None, str]], known: set[str]
) -> tuple[list[dict], list[str]]:
    """逐段行装配：等长按位置对位、不等长按 idx 对齐、无效 idx 丢行；
    verdict 出界＝该段换「这一段没判出来」警示行（不静默少行，不重抽）。
    返回 (rows, warnings)；可用行数（verdict 入闭集）由调用方判重试。
    """
    warn: list[str] = []
    model_rows = parsed.get("rows") if isinstance(parsed, dict) else None
    if not isinstance(model_rows, list):
        return [], ["AI 没有返回可读的盘点行"]
    model_rows = [r for r in model_rows if isinstance(r, dict)]

    pairs: list[tuple[dict, tuple[int | None, str]]] = []
    if len(model_rows) == len(targets):
        pairs = list(zip(model_rows, targets))
    else:
        target_idxs = {t[0] for t in targets}
        by_idx: dict[int | None, dict] = {}
        for r in model_rows:
            raw_idx = r.get("idx")
            idx = raw_idx if isinstance(raw_idx, int) and not isinstance(raw_idx, bool) else None
            if idx is None and None not in target_idxs:
                warn.append(f"段编号 {raw_idx!r} 对不上本章条目，这一行已丢弃")
                continue
            if idx is not None and idx not in target_idxs:
                warn.append(f"段编号 {raw_idx!r} 对不上本章条目，这一行已丢弃")
                continue
            if idx in by_idx:
                warn.append(f"段编号 {raw_idx!r} 重复，多余的行已丢弃")
                continue
            by_idx[idx] = r
        for t in targets:
            r = by_idx.get(t[0])
            if r is None:
                warn.append(f"{_seg_label(t[0])}没判出来")
                pairs.append(({}, t))
            else:
                pairs.append((r, t))

    rows = [_review_row(r, idx, echo, known, warn) for r, (idx, echo) in pairs]
    return rows, warn


def _review_row(r: dict, idx: int | None, echo: str, known: set[str], warn: list[str]) -> dict:
    verdict = normalize_closed(r.get("verdict"), VERDICTS, allow_substring=True)
    if verdict is None:
        return {
            "idx": idx,
            "echo": echo,
            "verdict": ROW_UNJUDGED,
            "who": [],
            "as": "",
            "why": "",
            "gap": None,
            "defaulted": False,
        }
    who = _filter_who(r.get("who"), known)
    if verdict == VERDICT_OLD and not who:
        warn.append(
            f"{_seg_label(idx)}「老角色能演」列出的名字都不在已知名单里，这一行先留着，请自己核对"
        )
    defaulted = False
    if verdict == VERDICT_NEW:
        gap_raw = r.get("gap")
        gap_raw = gap_raw if isinstance(gap_raw, dict) else {}
        suggest = normalize_closed(gap_raw.get("suggest"), SUGGESTS, allow_substring=False)
        if suggest is None:
            suggest, defaulted = SUGGEST_DEFAULT, True
        gap = {
            "need": str(gap_raw.get("need") or "").strip()[:_NEED_LEN],
            "why_not_old": str(gap_raw.get("why_not_old") or "").strip()[:_WHY_NOT_OLD_LEN],
            "suggest": suggest,
        }
    else:
        gap = None
    return {
        "idx": idx,
        "echo": echo,
        "verdict": verdict,
        "who": who,
        "as": str(r.get("as") or "").strip()[:_AS_LEN] if verdict == VERDICT_UNNAMED else "",
        "why": str(r.get("why") or "").strip()[:_WHY_LEN],
        "gap": gap,
        "defaulted": defaulted,
    }


# ═══════════════ 提案卡输出契约（decision 10/11） ═══════════════


def _as_int(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and v.strip().isdigit():
        return int(v.strip())
    return None


def _sanitize_cast_cards(
    parsed: dict | None,
) -> tuple[list[dict], list[int], list[str], dict[str, list[int | None]]]:
    """逐卡兜底：axis/exit_kind 出闭集、缺称呼或人设、批内同轴/同名 → 丢卡（不改写）。
    返回 (可用卡, 各保留卡原始下标, warnings, 全批名次表)——名次按模型输出原始卡序带出。"""
    warn: list[str] = []
    ranks_by_dim: dict[str, list[int | None]] = {d: [] for d in CAST_DIMS}
    if not isinstance(parsed, dict):
        return [], [], ["出卡不是合法 JSON"], ranks_by_dim
    cards_in = parsed.get("cards")
    if not isinstance(cards_in, list):
        return [], [], ["cards 缺失"], ranks_by_dim
    out: list[tuple[int, dict]] = []
    for i, c in enumerate(cards_in):
        raw_ranks = c.get("ranks") if isinstance(c, dict) else None
        raw_ranks = raw_ranks if isinstance(raw_ranks, dict) else {}
        for d in CAST_DIMS:
            ranks_by_dim[d].append(_as_int(raw_ranks.get(d)))
        if not isinstance(c, dict):
            continue
        axis = normalize_closed(c.get("axis"), AXES, allow_substring=False)
        exit_kind = normalize_closed(c.get("exit_kind"), EXIT_KINDS, allow_substring=True)
        name = str(c.get("name") or "").strip()[:_NAME_LEN]
        persona = str(c.get("persona") or "").strip()[:_PERSONA_LEN]
        if axis is None:
            warn.append(f"第 {i + 1} 张差异轴不合法，已丢弃")
            continue
        if exit_kind is None:
            warn.append(f"第 {i + 1} 张怎么退场不合法，已丢弃")
            continue
        if not name or not persona:
            warn.append(f"第 {i + 1} 张缺称呼或一句人设，已丢弃")
            continue
        if any(card["axis"] == axis for _, card in out):
            warn.append(f"第 {i + 1} 张与前面某张同轴，已丢弃")
            continue
        if any(card["name"] == name for _, card in out):
            warn.append(f"第 {i + 1} 张称呼与前面某张重复，已丢弃")
            continue
        reasons_raw = c.get("reasons")
        reasons_raw = reasons_raw if isinstance(reasons_raw, dict) else {}
        out.append((
            i,
            {
                "axis": axis,
                "name": name,
                "duty": str(c.get("duty") or "").strip()[:_DUTY_LEN],
                "persona": persona,
                "entrance": str(c.get("entrance") or "").strip()[:_ENTRANCE_LEN],
                "exit_kind": exit_kind,
                "exit_note": str(c.get("exit_note") or "").strip()[:_EXIT_NOTE_LEN],
                "reasons": {
                    d: str(reasons_raw.get(d) or "").strip()[:_REASON_LEN] for d in CAST_DIMS
                },
            },
        ))
    return [c for _, c in out], [i for i, _ in out], warn, ranks_by_dim


def _drop_clashed_cards(
    cards: list[dict],
    keep_map: list[int],
    banned: set[str],
    exclude: list[CastExcludeItem],
    warn: list[str],
) -> tuple[list[dict], list[int], bool]:
    """对拍兜底（decision 10）：称呼撞已知/已出、或「同轴且人设句相似」、或称呼等值 → 丢卡。

    exclude 撞车（称呼等值／同轴近似）置 clash=True（重抽不降温）；
    撞已知实体属结构性（照常降温）。
    """
    clash = False
    kept_cards: list[dict] = []
    kept_idx: list[int] = []
    ex_names = {e.name.strip() for e in exclude if e.name.strip()}
    for card, oi in zip(cards, keep_map):
        name = card["name"]
        if name in ex_names:
            clash = True
            warn.append(f"「{name}」与已出的称呼相同，已丢弃")
            continue
        if name in banned:
            warn.append(f"「{name}」撞了已有的名字，已丢弃——称呼必须是新名字")
            continue
        hit = next(
            (
                e
                for e in exclude
                if e.axis.strip() == card["axis"]
                and e.persona.strip()
                and difflib.SequenceMatcher(
                    None, card["persona"], e.persona.strip()
                ).ratio()
                >= SIM_LIMIT
            ),
            None,
        )
        if hit is not None:
            clash = True
            warn.append(f"「{name}」与已出的「{hit.name}」是同一条人物路子，已丢弃")
            continue
        kept_cards.append(card)
        kept_idx.append(oi)
    return kept_cards, kept_idx, clash


def _grades_cards(ranks_by_dim: dict[str, list[int | None]], keep_map: list[int]) -> list[str]:
    """三维名次 → S/A/B（服务端算；模型不出等级字母）：唯一第一才计分，≥2 项第一＝S。"""
    from chapters.ai_plan import _grades

    n_orig = len(ranks_by_dim[CAST_DIMS[0]])
    return _grades(
        {"ranks": ranks_by_dim}, n_orig, keep_map, dims=CAST_DIMS, s_min=GRADE_S_MIN
    )


def _exclude_block(exclude: list[CastExcludeItem]) -> str:
    """中性禁令块内容（decision 10 钉词源；块界住模板，这里只产内容行）。"""
    if not exclude:
        return _NONE_TEXT
    lines = [
        f"- {e.axis.strip()}｜{e.name.strip()}｜{e.persona.strip()}"
        for e in exclude
        if e.name.strip() or e.persona.strip()
    ]
    return "\n".join(lines) + "\n" + _EXCLUDE_RULE


# ═══════════════ 端点 ═══════════════


async def _load_chapter(db, project, chapter_ref: str):
    from repositories import chapter_repo

    _validate_ref(chapter_ref)
    row = await chapter_repo.get_by_ref(db, project.id, strip_suffix(chapter_ref))
    if row is None:
        raise HTTPException(404, "Chapter not found")
    return row


@router.post("/ai-review")
async def cast_ai_review(
    project_id: str,
    chapter_ref: str,
    body: CastReviewBody,
    user: dict = Depends(get_current_user),
    __: bool = Depends(require_novel_model),  # 只读例外：免费可用（不挂 require_ai_access）
    db: AsyncSession = Depends(get_db),
):
    """逐段人物盘点（只读、不落库；零新增是常态输出）。输入＝请求体表单快照。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    row = await _load_chapter(db, project, chapter_ref)

    items = [str(x or "").strip() for x in body.plot_items]
    snapshot: list[str] = []
    for x in body.characters:
        nm = str(x or "").strip()
        if nm and nm not in snapshot:
            snapshot.append(nm)
    has_items = any(items)
    has_form = any(
        str(v or "").strip() for v in (body.summary, body.challenge, body.ladder_exit)
    )
    if not has_items and not has_form:
        raise HTTPException(
            422, "先写剧情再盘点——这一章还没有剧情条目，梗概、挑战、章末落点也空着"
        )

    vol = row.volume
    mat = await _book_material(db, project, with_hooks=False)  # 不给伏笔台账
    carded = set(mat["card_names"])  # 角色名∪别名（_book_material 收集）
    known = set(mat["known_entities"]) | set(snapshot)  # 仅丢卡对拍口径（本端点不丢卡）
    stats = await _collect_cast_stats(
        db, project.id, carded=carded, vol_no=vol.volume_no,
        ch_no=row.chapter_no, snapshot=snapshot,
    )
    regime = await _quota_regime(db, vol)
    items_list = await _character_items(db, project.id)
    # who 过滤域（spec R2）：角色名∪别名∪出场名单∪无卡名——不含势力/地点
    cast_known = carded | set(snapshot) | set(stats.visits)
    material = _cast_material(
        mat, items_list, row=row, snapshot=snapshot, stats=stats,
        banned=known, regime=regime, draw=False,
    )

    targets = [(i, t[:_ECHO_LEN]) for i, t in enumerate(items) if t]
    if targets:
        items_block = "\n".join(f"{i}. {t[:_LINE_LEN]}" for i, t in targets)
    else:
        echo_text = "；".join(
            str(v or "").strip()
            for v in (body.summary, body.challenge, body.ladder_exit)
            if str(v or "").strip()
        )[:_ECHO_LEN]
        targets = [(None, echo_text)]
        items_block = "（本章没有剧情条目）"
    retained = "\n".join(
        f"{label}：{str(getattr(body, key) or '').strip() or '（未填）'}"
        for label, key in _RETAIN_LABELS
    )
    system, user_tpl = load_layers("cast_review")

    def _user_msg(fail_cause: str = "") -> str:
        msg = _render(
            user_tpl,
            material=material,
            items=items_block,
            retained=retained,
            extra=str(body.extra or "").strip() or _NONE_TEXT,
        )
        return msg + (f"\n\n{_RETRY_BLOCK}\n{fail_cause}" if fail_cause else "")

    raw, _u = await _generate(
        project, system, _user_msg(),
        temperature=_REVIEW_TEMP, db=db, user=user,
        operation="cast_review", max_tokens=_REVIEW_MAX_TOKENS,
    )
    parsed = _parse_json(raw)
    rows, warn = _build_review_rows(parsed, targets, cast_known)
    attempts = 1
    # 整批重试只认「0 条可用行／JSON 不可解析」——判读类问题（滤空、单段出界）一律不重抽
    while not _has_judged(rows) and attempts < MAX_ATTEMPTS:
        cause = "；".join(warn[:2]) or "输出不可解析"
        raw, _u = await _generate(
            project, system, _user_msg(cause),
            temperature=_REVIEW_RETRY_TEMP, db=db, user=user,
            operation="cast_review_retry", max_tokens=_REVIEW_MAX_TOKENS,
        )
        parsed = _parse_json(raw)
        rows, warn = _build_review_rows(parsed, targets, known)
        attempts += 1
    if not _has_judged(rows):
        raise HTTPException(502, "AI 这次没盘出结果，可再试一次")

    hints = [
        {"name": nm, "text": f"「{nm}」已经出现在 {len(seen)} 章的出场名单里，建议建卡"}
        for nm, seen in sorted(stats.visits.items())
        if len(seen) >= 2
    ]
    return {
        "rows": rows,
        "quota": {"named_count": len(stats.vol_names), "regime": regime},
        "hints": hints,
        "warnings": warn[:5],
    }


def _has_judged(rows: list[dict]) -> bool:
    return any(r["verdict"] in VERDICTS for r in rows)


async def _character_items(db: AsyncSession, project_id: str) -> list[dict]:
    data = await character_service.list_characters(db, project_id)
    return list(data.get("items", []))


@router.post("/ai-draw")
@ai_feature("ai-plan")
async def cast_ai_draw(
    project_id: str,
    chapter_ref: str,
    body: CastDrawBody,
    user: dict = Depends(get_current_user),
    _: bool = Depends(require_ai_access),  # 生成类归 PRO
    __: bool = Depends(require_novel_model),
    db: AsyncSession = Depends(get_db),
):
    """提案抽卡：一次 3 张互斥提案卡（不落库）；等级服务端算、why_not_old 服务端直抄。"""
    project = await get_novel(db, project_id, user["id"])
    if not project:
        raise HTTPException(404, "Novel not found")
    row = await _load_chapter(db, project, chapter_ref)

    snapshot: list[str] = []
    for x in body.characters:
        nm = str(x or "").strip()
        if nm and nm not in snapshot:
            snapshot.append(nm)
    exclude = [e for e in body.exclude if e.name.strip() or e.persona.strip()][:9]
    vol = row.volume
    mat = await _book_material(db, project, with_hooks=False)
    carded = set(mat["card_names"])
    known = set(mat["known_entities"]) | set(snapshot)
    banned = known | {e.name.strip() for e in exclude if e.name.strip()}
    stats = await _collect_cast_stats(
        db, project.id, carded=carded, vol_no=vol.volume_no,
        ch_no=row.chapter_no, snapshot=snapshot,
    )
    regime = await _quota_regime(db, vol)
    items_list = await _character_items(db, project.id)
    material = _cast_material(
        mat, items_list, row=row, snapshot=snapshot, stats=stats,
        banned=banned, regime=regime, draw=True,
    )
    gap_block = (
        f"这段戏缺的是：{body.gap.need}\n老角色为什么不行：{body.gap.why_not_old}"
    )
    system, user_tpl = load_layers("cast_draw")

    def _user_msg(fail_cause: str = "") -> str:
        msg = _render(
            user_tpl,
            gap=gap_block,
            material=material,
            exclude=_exclude_block(exclude),
            extra=str(body.extra or "").strip() or _NONE_TEXT,
        )
        return msg + (f"\n\n{_RETRY_BLOCK}\n{fail_cause}" if fail_cause else "")

    raw, _u = await _generate(
        project, system, _user_msg(),
        temperature=_DRAW_TEMP, db=db, user=user,
        operation="cast_draw", max_tokens=_DRAW_MAX_TOKENS,
    )
    parsed = _parse_json(raw)
    cards, keep_map, warn, ranks_by_dim = _sanitize_cast_cards(parsed)
    cards, keep_map, clash = _drop_clashed_cards(cards, keep_map, banned, exclude, warn)
    attempts = 1
    while len(cards) < 2 and attempts < MAX_ATTEMPTS:
        cause = "；".join(warn[:2]) or "输出不可解析"
        # exclude 撞车重抽求差异，SHALL NOT 降温；纯结构性失败照阶梯降温
        temp = _DRAW_TEMP if clash else _DRAW_RETRY_TEMP
        raw, _u = await _generate(
            project, system, _user_msg(cause),
            temperature=temp, db=db, user=user,
            operation="cast_draw_retry", max_tokens=_DRAW_MAX_TOKENS,
        )
        parsed = _parse_json(raw)
        cards, keep_map, warn, ranks_by_dim = _sanitize_cast_cards(parsed)
        cards, keep_map, clash = _drop_clashed_cards(cards, keep_map, banned, exclude, warn)
        attempts += 1
    if len(cards) < 2:
        return {"cards": [], "note": ""}

    grades = _grades_cards(ranks_by_dim, keep_map)
    why_not_old = str(body.gap.why_not_old or "")  # 服务端直抄缺人行：不 clamp、逐字
    out = []
    for pos, (card, grade) in enumerate(zip(cards, grades)):
        orig = keep_map[pos]
        entry = dict(card)
        entry["why_not_old"] = why_not_old
        entry["grade"] = grade
        entry["ranks"] = {
            d: ranks_by_dim[d][orig] if ranks_by_dim[d][orig] is not None else 0
            for d in CAST_DIMS
        }
        out.append(entry)
    note = (
        str(parsed.get("note") or "").strip()[:_NOTE_LEN] if isinstance(parsed, dict) else ""
    )
    return {"cards": out, "note": note}
