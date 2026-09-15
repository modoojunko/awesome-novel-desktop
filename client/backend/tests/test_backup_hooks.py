"""伏笔段的导入契约测试（foreshadow-settings-v2 tasks 3.1/3.2）。

roundtrip 第十层在 test_backup_roundtrip.py；本文件专测导入侧两条路：
  - v1 读窗：settings/hooks.yaml KV 三数组 → novel_hooks 行——数组名→status、
    mentioned→active＋mentioned 列、introduced_in 自由文本归一绑 ref（绑不上
    NULL＋warning 不丢行）、priority/type 混形归一、空描述留行、seq 取号、
    project_settings 无 hooks 残留
  - v3 直读：hooks/hooks.yaml ref→id 重绑（章循环落库之后）、悬空 ref→NULL＋
    warning 不丢行、包内 id 撞车重排沿角色先例
"""

import asyncio
import io
import uuid
import zipfile

import yaml
from sqlalchemy import select, text

from backup.importer import _import_single_book
from db import async_session

# 本文件所有 async 调用走同一个常驻 event loop（理由同 test_backup_roundtrip：
# asyncio.run 每次新 loop 与引擎连接池跨 loop 复用在 SQLite 下偶发 database is locked）
_LOOP = asyncio.new_event_loop()


def _run(coro):
    return _LOOP.run_until_complete(coro)


def _v1_hooks_yaml() -> str:
    """v1 KV 三数组混形样例（tasks 3.2 点名的每种形状逐条在场）。"""
    return yaml.safe_dump({
        "active": [
            {
                "description": "mentioned 旧状态样例",
                "introduced_in": "1-1",
                "status": "mentioned",
                "priority": 1,
                "hook_type": "clue",
                "seed_text": "旧字段，读窗无归宿（随迁移退役）",
            },
            {
                "description": "短格式引入",
                "introduced_in": "1-1",
                "priority": "2",
                "hook_type": "mystery",
            },
            {
                "description": "垃圾文本引入",
                "introduced_in": "不知道写在哪一章",
                "priority": 99,
                "hook_type": "weird",
            },
            {
                "description": "",
                "introduced_in": "",
                "priority": "high",
            },
        ],
        "resolved": [
            {
                "description": "已收束样例",
                "introduced_in": "vol-1-ch-1",
                "priority": 3,
                "hook_type": "promise",
            },
        ],
        "abandoned": [
            {
                "description": "悬空引用样例",
                "introduced_in": "3-7",
                "priority": 2,
                "hook_type": "threat",
            },
        ],
    }, allow_unicode=True, sort_keys=False)


def _v1_package_bytes() -> bytes:
    """单书包：一章（vol-1-ch-1）＋ v1 KV 伏笔三数组。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.yaml", yaml.safe_dump({
            "name": "v1伏笔老书", "slug": f"v1hook-{uuid.uuid4().hex[:6]}",
            "current_phase": "write",
        }))
        zf.writestr("volumes/vol-1.yaml", yaml.safe_dump({
            "volume": 1, "title": "第一卷",
        }))
        zf.writestr("chapters/vol-1-ch-1.yaml", yaml.safe_dump({
            "volume": 1, "title": "锚点章", "prose": "信标亮起。", "status": "done",
        }))
        zf.writestr("settings/hooks.yaml", _v1_hooks_yaml())
    return buf.getvalue()


def _import_bytes(blob: bytes, tmp_path) -> tuple[str, list[str]]:
    """导入单书包，返回 (novel_id, warnings)。"""
    path = tmp_path / f"in-{uuid.uuid4().hex[:6]}.zip"
    path.write_bytes(blob)

    async def run():
        async with async_session() as db:
            warnings: list[str] = []
            nid = await _import_single_book(
                db, zipfile.ZipFile(str(path)), "", "hook-user", warnings=warnings
            )
            await db.commit()
            return nid, warnings

    return _run(run())


async def _load_hooks(novel_id: str) -> list:
    from models.hook import NovelHook

    async with async_session() as db:
        return (
            await db.scalars(
                select(NovelHook).where(NovelHook.novel_id == novel_id)
                .order_by(NovelHook.seq)
            )
        ).all()


async def _dst_chapter_id(novel_id: str, ref: str) -> str | None:
    from models.chapter import Chapter

    async with async_session() as db:
        ch = (
            await db.scalars(
                select(Chapter).where(
                    Chapter.project_id == novel_id, Chapter.ref == ref
                )
            )
        ).first()
        return ch.id if ch else None


class TestV1ReadWindow:
    def test_v1_kv_arrays_become_rows_without_loss(self, tmp_path):
        novel_id, warnings = _import_bytes(_v1_package_bytes(), tmp_path)
        hooks = _run(_load_hooks(novel_id))

        # 行数 = 有效条数（4 active + 1 resolved + 1 abandoned），不丢行
        assert len(hooks) == 6

        async def run():
            async with async_session() as db:
                from models.project import Novel

                novel = await db.get(Novel, novel_id)
                return novel.hook_seq_high

        by_desc = {h.description: h for h in hooks}
        ch_id = _run(_dst_chapter_id(novel_id, "vol-1-ch-1"))
        assert ch_id, "包内章 vol-1-ch-1 未落库"

        # 数组名 → status；旧 status:"mentioned" → active＋mentioned=引入章
        mentioned = by_desc["mentioned 旧状态样例"]
        assert mentioned.status == "active"
        assert mentioned.introduced_chapter_id == ch_id  # 短格式 "1-1" 归一绑 ref
        assert mentioned.mentioned_chapter_id == ch_id

        # 短格式 "1-1" 绑定；字符串数字 priority 归一
        short = by_desc["短格式引入"]
        assert short.status == "active"
        assert short.introduced_chapter_id == ch_id
        assert short.priority == 2

        # 垃圾文本 → NULL＋warning 不丢行；priority 非法置默认 2；未知 type → mystery
        garbage = by_desc["垃圾文本引入"]
        assert garbage.introduced_chapter_id is None
        assert garbage.priority == 2
        assert garbage.type == "mystery"

        # 空描述留行；priority 英文词 "high" → 1
        empty = by_desc[""]
        assert empty.description == ""
        assert empty.priority == 1
        assert empty.introduced_chapter_id is None

        # resolved / abandoned 数组映射；规范 ref 形态直接通过
        assert by_desc["已收束样例"].status == "resolved"
        assert by_desc["已收束样例"].introduced_chapter_id == ch_id
        assert by_desc["悬空引用样例"].status == "abandoned"
        assert by_desc["悬空引用样例"].introduced_chapter_id is None  # "3-7" 包内无此章

        # 状态逐条清点：mentioned 条目并入 active → active 4
        statuses = sorted(h.status for h in hooks)
        assert statuses == ["abandoned", "active", "active", "active", "active", "resolved"]

        # seq 缺失 → 按导入顺序取号器补（1..6，单调不复用）
        assert [h.seq for h in hooks] == [1, 2, 3, 4, 5, 6]
        assert _run(run()) == 6

        # ref 解析失败的 warning 计数（垃圾文本 + 悬空 3-7）＝ 2，行未丢
        unresolved = [w for w in warnings if "无法解析" in w]
        assert len(unresolved) == 2

    def test_v1_import_leaves_no_hooks_key_in_project_settings(self, tmp_path):
        novel_id, _warnings = _import_bytes(_v1_package_bytes(), tmp_path)

        async def run():
            async with async_session() as db:
                from models.project import Novel

                novel = await db.get(Novel, novel_id)
                rows = (
                    await db.execute(text(
                        "SELECT key FROM project_settings WHERE root_path = :rp"
                    ), {"rp": novel.root_path})
                ).all()
                return {row[0] for row in rows}

        keys = _run(run())
        assert all(not str(k).startswith("hook") for k in keys), keys
        assert "hooks" not in keys


class TestV3DirectRead:
    def _v3_package_bytes(self, hooks: list[dict]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project.yaml", yaml.safe_dump({
                "format_version": 3,
                "name": "v3伏笔书", "slug": f"v3hook-{uuid.uuid4().hex[:6]}",
                "current_phase": "write",
            }))
            zf.writestr("volumes/vol-1.yaml", yaml.safe_dump({
                "volume": 1, "title": "第一卷",
            }))
            zf.writestr("chapters/vol-1-ch-1.yaml", yaml.safe_dump({
                "volume": 1, "title": "锚点章", "prose": "正文。", "status": "done",
            }))
            zf.writestr("hooks/hooks.yaml", yaml.safe_dump(
                {"hooks": hooks}, allow_unicode=True, sort_keys=False,
            ))
        return buf.getvalue()

    def test_refs_rebound_after_chapter_loop_and_dangling_to_null(self, tmp_path):
        hooks = [
            {
                "seq": 1, "description": "可解析引用", "type": "clue",
                "priority": 1, "status": "active",
                "introduced_chapter_ref": "vol-1-ch-1",
                "planned_chapter_ref": "vol-1-ch-1",
                "resolved_chapter_ref": "", "mentioned_chapter_ref": "",
                "payoff_note": "",
            },
            {
                "seq": 2, "description": "悬空引用", "type": "mystery",
                "priority": 2, "status": "active",
                "introduced_chapter_ref": "vol-9-ch-9",
                "planned_chapter_ref": "", "resolved_chapter_ref": "",
                "mentioned_chapter_ref": "", "payoff_note": "",
            },
        ]
        novel_id, warnings = _import_bytes(self._v3_package_bytes(hooks), tmp_path)
        rows = _run(_load_hooks(novel_id))
        assert len(rows) == 2  # 悬空不丢行

        ch_id = _run(_dst_chapter_id(novel_id, "vol-1-ch-1"))
        by_desc = {h.description: h for h in rows}
        # 可解析 ref → 新章 id（章循环落库之后的重绑）
        assert by_desc["可解析引用"].introduced_chapter_id == ch_id
        assert by_desc["可解析引用"].planned_chapter_id == ch_id
        # 悬空 ref → NULL＋warning
        assert by_desc["悬空引用"].introduced_chapter_id is None
        assert len([w for w in warnings if "无法解析" in w]) == 1
        # 包内 seq 原样保留
        assert [h.seq for h in rows] == [1, 2]

    def test_package_id_collision_remapped_like_characters(self, tmp_path):
        """包内 id 撞车重排沿角色先例：与库内已有伏笔同 id → 换 id 保内容。"""
        fixed_id = str(uuid.uuid4())
        hooks = [{
            "id": fixed_id,
            "seq": 1, "description": "撞车样例", "type": "clue",
            "priority": 2, "status": "active",
            "introduced_chapter_ref": "", "planned_chapter_ref": "",
            "resolved_chapter_ref": "", "mentioned_chapter_ref": "",
            "payoff_note": "",
        }]
        # 第一遍：正常落库（id 不撞车 → 原样保留）
        nid1, _ = _import_bytes(self._v3_package_bytes(hooks), tmp_path)
        first = _run(_load_hooks(nid1))[0]
        assert first.id == fixed_id

        # 第二遍：同一 id 已在本库（同包导回同一库）→ 重映射保内容不炸
        nid2, _ = _import_bytes(self._v3_package_bytes(hooks), tmp_path)
        second = _run(_load_hooks(nid2))[0]
        assert second.id != fixed_id
        assert second.description == "撞车样例" and second.seq == 1


class TestLegacySnapshotExport:
    def test_novels_export_snapshot_includes_hooks_section(self, tmp_path):
        """/novels/{id}/export（_dump_project_snapshot 作品包）与备份链共用导入器，
        伏笔段必须在场——否则该路径静默丢伏笔（foreshadow-settings-v2）。"""
        from models.chapter import Chapter
        from models.hook import NovelHook
        from models.project import Novel
        from models.user import User
        from models.volume import Volume
        from novels.router import _dump_project_snapshot

        async def seed_and_dump():
            uid = f"snap-{uuid.uuid4().hex[:8]}"
            slug = f"snap-{uuid.uuid4().hex[:8]}"
            async with async_session() as db:
                db.add(User(
                    id=uid, email=f"{uid}@test.local", password_hash="x",
                ))
                proj = Novel(
                    user_id=uid, name="快照导出书", slug=slug,
                    root_path=str(tmp_path / slug), source="manual",
                    current_phase="write",
                )
                db.add(proj)
                await db.flush()
                vol = Volume(id=str(uuid.uuid4()), project_id=proj.id,
                             volume_no=1, title="第一卷")
                db.add(vol)
                await db.flush()
                ch = Chapter(
                    id=str(uuid.uuid4()), project_id=proj.id, volume_id=vol.id,
                    ref="vol-1-ch-1", title="T", chapter_no=1, status="outline",
                    word_count=0, has_prose=False,
                )
                db.add(ch)
                await db.flush()
                db.add(NovelHook(
                    novel_id=proj.id, seq=1, description="快照导出样例",
                    type="clue", priority=1, status="active",
                    introduced_chapter_id=ch.id,
                ))
                import io as _io
                import zipfile as _zipfile

                buf = _io.BytesIO()
                with _zipfile.ZipFile(buf, "w", _zipfile.ZIP_DEFLATED) as zf:
                    await _dump_project_snapshot(zf, db, proj)
                await db.commit()
                return buf.getvalue()

        blob = _run(seed_and_dump())
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
            assert "hooks/hooks.yaml" in names
            assert "settings/hooks.yaml" not in names
            section = yaml.safe_load(zf.read("hooks/hooks.yaml"))
        assert section["hooks"][0]["introduced_chapter_ref"] == "vol-1-ch-1"
        assert section["hooks"][0]["description"] == "快照导出样例"
