"""章内剧情条目 plot_items 保存契约（c-plot-split tasks 2.1/2.2/2.3）。

覆盖：
- 2.1 列落地与装配输出：恒带键、round-trip（含换行条目单条完整不切条）、
  损坏 JSON/空串/非数组不阻塞读取（按 []）、真导出携带＋真导入往返、
  导入缺失键按 []；
- 2.2 保存契约：presence-gate（缺键/None 保持现值、显式 [] 清空、非列表不误清）
  ＋预算静默夹（单条 200、上限 12，单源 chapters.schemas.normalize_plot_items）
  ＋schemas 形状校验（非数组才 422）；
- 2.3 预算不进整表问题清单：超长/超条数输入不产生保存错误（静默夹不 422）。

用法：
    cd client/backend
    python -m pytest tests/test_plot_items_save.py -v
"""

import asyncio
import io
import os
import tempfile
import zipfile

_tmp_db = tempfile.NamedTemporaryFile(suffix="_plot_items.db", delete=False)  # noqa: SIM115
_tmp_db.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = tempfile.mkdtemp(prefix="test_plot_items_")

import pytest  # noqa: E402
import yaml  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from conftest import seed_chapter_db  # noqa: E402
from db import Base, async_session, engine  # noqa: E402
from models.chapter import Chapter  # noqa: E402
from models.project import Novel  # noqa: E402

_ITEMS = ["开场：荒庙接头", "中段：调包账册\n暗线：有人尾随", "结尾：她回头一望"]


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _ensure_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def _seed(root: str, items=None) -> None:
    data = {
        "volume": 1,
        "chapter": 1,
        "title": "第一章",
        "outline": {"summary": "主角来到边境城邦。", "characters": []},
        "memo": {},
    }
    if items is not None:
        data["plot_items"] = items
    _run(seed_chapter_db(root, data))


async def _load(root: str, ref: str = "vol-1-ch-1") -> dict:
    from chapters.store import load_chapter

    return await load_chapter(root, ref)


async def _set_plot_raw(root: str, raw: str) -> None:
    """把 plot_items 原始列写成给定字符串（模拟损坏值/旧库空串）。"""
    async with async_session() as session:
        row = (await session.scalars(
            select(Chapter)
            .join(Novel, Novel.id == Chapter.project_id)
            .where(Novel.root_path == root, Chapter.ref == "vol-1-ch-1")
        )).one()
        row.plot_items = raw
        await session.commit()


# ── 预算单源与形状校验（纯函数，无 DB）─────────────────────────────────────


def test_normalize_budget_and_newline_intact():
    from chapters.schemas import PLOT_MAX_ITEMS, PLOT_MAX_LEN, normalize_plot_items

    out = normalize_plot_items(["汉" * 205, "含\n换行的一条", 5])
    assert len(out[0]) == PLOT_MAX_LEN
    assert out[1] == "含\n换行的一条"  # 含换行的条目单条完整保留，不切条
    # c-og-slim-v2：非字符串项丢弃（不再 str() 成 "5" / "{'text':…}" 落库）
    assert len(out) == 2
    assert len(normalize_plot_items([f"第{i}条" for i in range(15)])) == PLOT_MAX_ITEMS


def test_validate_plot_items_shape_and_silent_clamp():
    from chapters.schemas import validate_chapter_fields

    # 超长/超条数只静默夹，不 422——保存链不报错（2.3：超长输入不产生保存错误）
    body = {"plot_items": ["汉" * 500] * 15}
    validate_chapter_fields(body)
    assert len(body["plot_items"]) == 12
    assert all(len(x) == 200 for x in body["plot_items"])

    # 形状非数组才 422
    with pytest.raises(HTTPException) as e:
        validate_chapter_fields({"plot_items": "不是数组"})
    assert e.value.status_code == 422

    # 缺键/None 跳过（presence-gate 在落库层，校验层不动 body）
    untouched = {"summary": "s"}
    validate_chapter_fields(untouched)
    assert "plot_items" not in untouched
    with_none = {"plot_items": None}
    validate_chapter_fields(with_none)
    assert with_none["plot_items"] is None


# ── 2.1 装配输出与 round-trip ───────────────────────────────────────────────


def test_assemble_always_emits_and_roundtrips():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="plot_rt_")
    _seed(root, _ITEMS)
    data = _run(_load(root))
    assert data["plot_items"] == _ITEMS  # 含换行的仍是同一条，不切条不合并

    # 空书装配也恒带键
    empty_root = tempfile.mkdtemp(prefix="plot_empty_")
    _seed(empty_root)
    assert _run(_load(empty_root))["plot_items"] == []


def test_corrupt_values_do_not_block_read():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="plot_bad_")
    _seed(root, _ITEMS)
    for raw in ("{not json", "", '"裸字符串"', "[]]"):
        _run(_set_plot_raw(root, raw))
        assert _run(_load(root))["plot_items"] == [], raw


# ── 2.2 presence-gate ───────────────────────────────────────────────────────


def test_presence_gate_keeps_clears_and_never_wipes_by_shape():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="plot_gate_")
    _seed(root, _ITEMS)
    from chapters.store import save_chapter

    # 缺键保持现值（旧表单/旁路请求）
    _run(save_chapter(root, "vol-1-ch-1", {"title": "第一章改名"}))
    assert _run(_load(root))["plot_items"] == _ITEMS

    # None 按缺键处理，同样保持
    _run(save_chapter(root, "vol-1-ch-1", {"plot_items": None}))
    assert _run(_load(root))["plot_items"] == _ITEMS

    # 形状非列表按缺键处理，不误清
    _run(save_chapter(root, "vol-1-ch-1", {"plot_items": "脏形状"}))
    assert _run(_load(root))["plot_items"] == _ITEMS

    # 显式 [] 清空
    _run(save_chapter(root, "vol-1-ch-1", {"plot_items": []}))
    assert _run(_load(root))["plot_items"] == []


def test_over_budget_save_is_silent_not_error():
    """2.3：超长/超条数走完整保存链不报错（预算不产生保存错误、不冻结自动保存）。"""
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="plot_budget_")
    _seed(root, _ITEMS)
    from chapters.store import save_chapter

    big = ["汉" * 500] + [f"第{i}条" for i in range(20)]
    _run(save_chapter(root, "vol-1-ch-1", {"plot_items": big}))  # 不抛
    got = _run(_load(root))["plot_items"]
    assert len(got) == 12
    assert len(got[0]) == 200  # 超长条截 200，不报错
    assert got[1:] == [f"第{i}条" for i in range(11)]  # 超条数截 12，顺序不乱


# ── 2.1 导出导入（真导出 → 真导入；加键兼容）────────────────────────────────


def test_export_import_roundtrip_and_missing_key():
    _run(_ensure_tables())
    root = tempfile.mkdtemp(prefix="plot_zip_")
    _seed(root, _ITEMS)

    async def _export() -> bytes:
        from backup.export import dump_book_into

        async with async_session() as db:
            project = (await db.scalars(
                select(Novel).where(Novel.root_path == root)
            )).one()
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                await dump_book_into(zf, db, project, prefix="")
            return buf.getvalue()

    blob = _run(_export())
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        ch_name = next(n for n in names if n.endswith("chapters/vol-1-ch-1.yaml"))
        ch_yaml = yaml.safe_load(zf.read(ch_name))
    assert ch_yaml["plot_items"] == _ITEMS  # 导出携带

    async def _import(zip_path: str) -> str:
        from backup.importer import _import_single_book

        async with async_session() as db:
            novel_id = await _import_single_book(
                db, zipfile.ZipFile(zip_path), "", "plot-user"
            )
            await db.commit()
            return novel_id

    async def _assembled_of(novel_id: str) -> dict:
        from chapters.store import assemble_chapter

        async with async_session() as db:
            row = (await db.scalars(
                select(Chapter)
                .where(Chapter.project_id == novel_id, Chapter.ref == "vol-1-ch-1")
            )).one()
            return assemble_chapter(row)

    # 往返：4 条（含换行）原样回写
    path = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)  # noqa: SIM115
    path.write(blob)
    path.close()
    dst_id = _run(_import(path.name))
    assert _run(_assembled_of(dst_id))["plot_items"] == _ITEMS

    # 导入包缺失该键 → 按 [] 处理（加键兼容）
    stripped = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(blob)) as zin, zipfile.ZipFile(
        stripped, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for n in zin.namelist():
            payload = zin.read(n)
            if n == ch_name:
                doc = yaml.safe_load(payload)
                doc.pop("plot_items", None)
                payload = yaml.safe_dump(doc, allow_unicode=True).encode("utf-8")
            zout.writestr(n, payload)
    path2 = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)  # noqa: SIM115
    path2.write(stripped.getvalue())
    path2.close()
    dst_id2 = _run(_import(path2.name))
    assert _run(_assembled_of(dst_id2))["plot_items"] == []
