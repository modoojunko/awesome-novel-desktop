"""本书题材关系化存储服务（genre-signup-redesign D19 / tasks 6.0b）。

对外契约仍是五字段 JSON：
    { core_promise, promise_note, forbidden_list[{tagId|text}], cost_ratio, battlefield[] }
`get_novel_genre` 组装、`put_novel_genre` 单事务拆分写 4 张表。
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.novel_genre import (
    GenreVocab,
    NovelGenre,
    NovelGenreBattlefield,
    NovelGenreForbidden,
)

from .vocab_presets import VOCAB_PRESETS

# ── 请求模型（D18 数据字典：长度/元素数/取值上限；SQLite 的 VARCHAR 长度不强制）──


class ForbiddenItemIn(BaseModel):
    """禁项：tagId（引用词汇）或 text（自定义），恰一个非空。"""

    tagId: str | None = Field(default=None, max_length=64)
    text: str | None = Field(default=None, max_length=100)

    @field_validator("tagId", "text")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class NovelGenreIn(BaseModel):
    """本书题材五字段（对外契约；空值统一：None/""/空白＝未填）。"""

    core_promise: str | None = Field(default=None, max_length=60)
    promise_note: str | None = Field(default=None, max_length=200)
    forbidden_list: list[ForbiddenItemIn] = Field(default_factory=list, max_length=50)
    cost_ratio: int | None = Field(default=None, ge=1, le=10)
    battlefield: list[str] = Field(default_factory=list, max_length=10)
    # `track`（剧情轨道）已随 2026-09-10 用户拍板从题材契约移除——它与「主线规划」
    # 是同一个概念（整本书怎么走），一处两存违反本体纪律；DB 列保留不迁移，已有值
    # 只是不再被读写（旧调用带 track 会被 Pydantic 忽略）。

    @field_validator("battlefield")
    @classmethod
    def _bf_length(cls, v: list[str]) -> list[str]:
        for item in v:
            # 词汇引用（kind:slug）不受 20 字限制——限的是用户自定义文本
            if item.startswith(("promise:", "forbidden:", "battlefield:")):
                continue
            if len(item) > 20:
                raise ValueError("战场项不超过 20 字")
        return v


async def ensure_seed_genre_vocab() -> None:
    """幂等插入候选源（只插缺失，不覆盖用户对预置项的改动）。启动时调用。"""
    from db import async_session

    async with async_session() as session:
        for preset in VOCAB_PRESETS:
            existing = await session.get(GenreVocab, preset["id"])
            if existing is None:
                session.add(
                    GenreVocab(
                        id=preset["id"],
                        kind=preset["kind"],
                        label=preset["label"],
                        sort=preset["sort"],
                        is_preset=True,
                    )
                )
        await session.commit()


def _clean(v: Any) -> str | None:
    """空值统一：None/""/纯空白 等价视为未填。"""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


_SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)


def custom_vocab_id(kind: str, label: str, taken: set[str] | None = None) -> str:
    """用户自定义词汇 id：`custom:{kind}:{slugify(label)}`，冲突加 -2/-3 后缀。

    稳定 slug 而非序号——序号会随常量顺序漂移，已存 tagId 会指向错误标签（不可逆）。
    中文标签原样保留（str 模式下 `\\w` 是 Unicode 感知的）。
    """
    base = _SLUG_RE.sub("-", label.strip().lower()).strip("-") or "item"
    candidate = f"custom:{kind}:{base}"
    taken = taken or set()
    if candidate not in taken:
        return candidate
    n = 2
    while f"{candidate}-{n}" in taken:
        n += 1
    return f"{candidate}-{n}"


async def ensure_custom_vocab(
    session: AsyncSession, kind: str, label: str
) -> str | None:
    """按 label 取得（或创建）用户自定义词汇，返回其 id。

    幂等：同 kind 同 label 复用已有行；空 label 返回 None（调用方落 custom_text）。
    """
    label = (label or "").strip()
    if not label:
        return None
    rows = (
        await session.execute(select(GenreVocab).where(GenreVocab.kind == kind))
    ).scalars().all()
    for r in rows:
        if r.label == label:
            return r.id
    new_id = custom_vocab_id(kind, label, {r.id for r in rows})
    session.add(
        GenreVocab(
            id=new_id,
            kind=kind,
            label=label,
            sort=max([r.sort for r in rows], default=0) + 10,
            is_preset=False,
        )
    )
    await session.commit()
    return new_id


async def list_candidates(session: AsyncSession) -> dict[str, list[dict[str, Any]]]:
    """按 kind 分组返回候选源（GET /api/genres/candidates）。"""
    rows = (
        await session.execute(select(GenreVocab).order_by(GenreVocab.kind, GenreVocab.sort))
    ).scalars().all()
    out: dict[str, list[dict[str, Any]]] = {"promise": [], "forbidden": [], "battlefield": []}
    for r in rows:
        out.setdefault(r.kind, []).append({"id": r.id, "label": r.label, "is_preset": r.is_preset})
    return out


async def get_novel_genre(session: AsyncSession, novel_id: str) -> dict[str, Any]:
    """组装本书题材为五字段 JSON（无行时返回全空）。

    题材目录（01 大类/子类）不在这里——它落 `story.yaml`（与简介同族、复用既有 `genre` 键），
    由调用方（settings/router）补齐 `theme`/`sub_genre` 两个字段再下发。
    """
    row = await session.get(NovelGenre, novel_id)
    forbid = (
        await session.execute(
            select(NovelGenreForbidden)
            .where(NovelGenreForbidden.novel_id == novel_id)
            .order_by(NovelGenreForbidden.sort)
        )
    ).scalars().all()
    bf = (
        await session.execute(
            select(NovelGenreBattlefield)
            .where(NovelGenreBattlefield.novel_id == novel_id)
            .order_by(NovelGenreBattlefield.sort)
        )
    ).scalars().all()
    return {
        "core_promise": (row.core_promise if row else None) or "",
        "promise_note": (row.promise_note if row else None) or "",
        "forbidden_list": [
            {"tagId": f.vocab_id} if f.vocab_id else {"text": f.custom_text} for f in forbid
        ],
        "cost_ratio": row.cost_ratio if row else None,
        "battlefield": [b.vocab_id or b.custom_text for b in bf],
    }


async def put_novel_genre(
    session: AsyncSession, novel_id: str, payload: dict[str, Any]
) -> None:
    """单事务：upsert novel_genre + delete/insert 两张关联表。"""
    core_promise = _clean(payload.get("core_promise"))
    promise_note = _clean(payload.get("promise_note"))
    raw_cost = payload.get("cost_ratio")
    cost = None
    if raw_cost not in (None, ""):
        cost = int(raw_cost)
        if not 1 <= cost <= 10:
            raise ValueError("cost_ratio must be within 1..10")

    row = await session.get(NovelGenre, novel_id)
    if row is None:
        row = NovelGenre(novel_id=novel_id)
        session.add(row)
    row.core_promise = core_promise
    row.promise_note = promise_note
    row.cost_ratio = cost

    # 关联表全量替换（顺序＝数组序，sort 从 0 连续）
    await session.execute(
        delete(NovelGenreForbidden).where(NovelGenreForbidden.novel_id == novel_id)
    )
    await session.execute(
        delete(NovelGenreBattlefield).where(NovelGenreBattlefield.novel_id == novel_id)
    )

    # 词汇引用先验存在（FK RESTRICT 会抛 IntegrityError→500；此处给 400 可读错误）
    refs: list[str] = []
    for item in payload.get("forbidden_list") or []:
        if isinstance(item, dict) and _clean(item.get("tagId")):
            refs.append(_clean(item["tagId"]))
    for item in payload.get("battlefield") or []:
        val = _clean(item)
        if val and val.startswith(("promise:", "forbidden:", "battlefield:")):
            refs.append(val)
    if refs:
        known = set(
            (
                await session.execute(
                    select(GenreVocab.id).where(GenreVocab.id.in_(refs))
                )
            )
            .scalars()
            .all()
        )
        missing = sorted(set(refs) - known)
        if missing:
            raise ValueError(f"未知的候选词汇：{'、'.join(missing)}")

    for i, item in enumerate(payload.get("forbidden_list") or []):
        if not isinstance(item, dict):
            continue
        tag = _clean(item.get("tagId"))
        text = _clean(item.get("text"))
        if tag:
            session.add(
                NovelGenreForbidden(novel_id=novel_id, vocab_id=tag, sort=i)
            )
        elif text:
            session.add(
                NovelGenreForbidden(novel_id=novel_id, custom_text=text, sort=i)
            )
    for i, item in enumerate(payload.get("battlefield") or []):
        val = _clean(item)
        if not val:
            continue
        if val.startswith(("promise:", "forbidden:", "battlefield:")):
            session.add(
                NovelGenreBattlefield(novel_id=novel_id, vocab_id=val, sort=i)
            )
        else:
            session.add(
                NovelGenreBattlefield(novel_id=novel_id, custom_text=val, sort=i)
            )
    await session.commit()


async def genre_is_filled(session: AsyncSession, novel_id: str) -> bool:
    """确认判据：核心键任一非空。

    02 的主输入是作家写的**那一句话**（`promise_note`，用户 2026-09-10 改版），
    故它也计入；短标签 `core_promise` 由起点胶囊/AI 写入，同样计入。
    （`readiness._check_genre` 另有「已选题材目录大类」一条，两处合并成题材就绪。）
    """
    g = await get_novel_genre(session, novel_id)
    return bool(
        _clean(g["core_promise"])
        or _clean(g["promise_note"])
        or g["forbidden_list"]
        or g["cost_ratio"] is not None
        or g["battlefield"]
    )

