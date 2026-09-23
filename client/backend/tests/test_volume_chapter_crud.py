"""卷族 CRUD 入库测试（PR① 数据全量入库）

验证：create_volume MAX+1 忽略 vol_num + DB 唯一存储 + 计数自增；list_volumes DB 全量树；
update_volume 标量+子表整体替换；get_volume {ref} 容 .yaml + 卷纲四族组装；
卷纲结构化字段（扩列+4 子表）读写回环；delete_volume 级联删章+清残留文件；
create_chapter 章号自增 + 章/卷 YAML 均不落盘（DB 唯一属主）；get_chapter_row 无行即 None；
confirm 写 DB confirmed 态；delete_volume 级联清 chapter_versions 行；cleanup 只清归档 .md。

用法：
    cd client/backend
    python -m pytest tests/test_volume_chapter_crud.py -v
"""

import asyncio
import os
import tempfile

import pytest
from sqlalchemy import select

# ── Test environment (isolated temp DB + data root) ──────────────────────
_tmp_db = tempfile.NamedTemporaryFile(suffix="_crud.db", delete=False)  # noqa: SIM115
_tmp_db.close()
_tmp_data_root = tempfile.mkdtemp(prefix="test_volume_chapter_crud_")

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db.name}"
os.environ["DATA_ROOT"] = _tmp_data_root

from db import Base, async_session, engine
from filesystem.storage import LocalFileBackend
from models import Novel
from repositories import chapter_repo, volume_repo

USER_ID = "vcc_user"
storage = LocalFileBackend()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    _run_async(_create_tables())
    yield


async def _new_project(name: str) -> Novel:
    """建一个空项目（root_path 已建 volumes/chapters 目录）。"""
    root = os.path.join(_tmp_data_root, name)
    os.makedirs(os.path.join(root, "volumes"), exist_ok=True)
    os.makedirs(os.path.join(root, "chapters"), exist_ok=True)
    project = Novel(
        user_id=USER_ID,
        name=name,
        slug=name,
        root_path=root,
        source="manual",
        current_phase="settings",  # settings→outline 合法，create_volume 可推进
    )
    async with async_session() as session:
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


# ── 卷 CRUD（DB 唯一存储）────────────────────────────────────────────────


def test_create_volume_max_plus_one_ignores_vol_num():
    async def _run():
        project = await _new_project("cv1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            # 两次都传 vol_num=5，MAX+1 应生成 vol-1、vol-2
            r1 = await _create_volume(session, proj, title="第一卷", vol_num=5)
            r2 = await _create_volume(session, proj, title="第二卷", vol_num=5)
            assert r1["ref"] == "vol-1"
            assert r2["ref"] == "vol-2"
            assert r1["vol_num"] == 1 and r2["vol_num"] == 2
            assert await volume_repo.count_by_project(session, proj.id) == 2
            assert proj.total_volumes == 2
            # 卷族 DB 唯一属主，不再落 YAML
            assert await storage.read_yaml(proj.root_path, "volumes/vol-1.yaml") == {}

    _run_async(_run())


def test_list_volumes_returns_db_tree_with_chapter_meta():
    async def _run():
        project = await _new_project("lv1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="第一卷")
            await _create_chapter(session, proj, "vol-1", title="第一章")
            vols = await _list_volumes(session, proj)
            assert len(vols) == 1
            assert vols[0]["ref"] == "vol-1"
            assert vols[0]["title"] == "第一卷"
            assert vols[0]["chapter_count"] == 1
            ch = vols[0]["chapters"][0]
            assert ch["ref"] == "vol-1-ch-1"
            assert ch["title"] == "第一章"
            assert ch["status"] == "outline"
            assert ch["word_count"] == 0
            assert ch["archived"] is False

    _run_async(_run())


def test_update_volume_scalars_and_children_replace():
    async def _run():
        project = await _new_project("uv1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="原卷", summary="旧摘要")
            await _create_chapter(session, proj, "vol-1", title="第一章")
            # update 只带 title/summary → DB 行更新；章列表始终由 Chapter 行派生
            await _update_volume(
                session, proj, "vol-1",
                {"title": "新卷名", "summary": "新摘要"},
            )
            vol = await volume_repo.get_by_volume_no(session, proj.id, 1)
            assert vol.title == "新卷名"
            assert vol.summary == "新摘要"
            data = await _get_volume(session, proj, "vol-1")
            assert data["title"] == "新卷名"
            assert data["summary"] == "新摘要"
            assert data["chapters"][0]["title"] == "第一章"

    _run_async(_run())


def test_get_volume_tolerates_yaml_suffix():
    async def _run():
        project = await _new_project("gv1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="容尾缀", summary="s")
            data = await _get_volume(session, proj, "vol-1.yaml")
            assert data["title"] == "容尾缀"
            assert data["ref"] == "vol-1"

    _run_async(_run())


def test_volume_structured_fields_roundtrip():
    """卷纲结构化（c-volume-antagonist 终版字段集）：标量＋antagonist＋剧情节点行集。

    退役键（template_name/goal/plants/reveals/cast_members）显式携带＝422（同文件另测）。
    """
    async def _run():
        project = await _new_project("sv1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="结构卷")
            await _update_volume(
                session, proj, "vol-1",
                {
                    "core_conflict": "主角想查清真相，被幕后组织追杀",
                    "ending": "内鬼落网，但主角也失去警队身份",
                    "chapter_target": 40,
                    "antagonist_type": "人物",
                    "antagonist_line": "副队长——一边查案一边销毁证据",
                },
            )
            data = await _get_volume(session, proj, "vol-1")
            assert data["core_conflict"].startswith("主角想查")
            assert data["antagonist_type"] == "人物"
            assert "副队长" in data["antagonist_line"]
            # 退役键不再回显
            for gone in ("template_name", "goal", "plan_line", "plants", "reveals"):
                assert gone not in data
            # 卷角色＝聚合视图：无章即空
            assert data["cast_members"] == []

    asyncio.run(_run())



def test_volume_line_list_validation():
    """终版校验：antagonist_type 闭集 422；退役键 422；stage 六档 422。"""
    import pytest
    from pydantic import ValidationError
    from volumes.schemas import VolumeUpdate

    with pytest.raises(ValidationError):
        VolumeUpdate(antagonist_type="不属于闭集")
    with pytest.raises(ValidationError):
        VolumeUpdate(plants=["a"])  # 退役键硬拒
    ok = VolumeUpdate(antagonist_type="自我", antagonist_line="体内饥渴——越压越饿")
    assert ok.antagonist_type == "自我"


def test_delete_volume_cascades_chapters_and_files():
    async def _run():
        project = await _new_project("dv1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="待删卷")
            await _create_chapter(session, proj, "vol-1", title="第一章")
            await _create_chapter(session, proj, "vol-1", title="第二章")
            # 写正文：chapter_contents 子行随章行 CASCADE，并产生版本快照行
            from chapters.service import save_prose
            from models.chapter import Chapter, ChapterContent, ChapterVersion

            await save_prose(session, proj, "vol-1-ch-1", "正文")
            snaps = (
                await session.scalars(
                    select(ChapterVersion)
                    .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
                    .where(Chapter.project_id == proj.id)
                )
            ).all()
            assert snaps, "prose 变化应生成版本快照行"
            await _delete_volume(session, proj, "vol-1")

            assert await volume_repo.count_by_project(session, proj.id) == 0
            assert await chapter_repo.count_by_project(session, proj.id) == 0
            assert proj.total_volumes == 0
            assert proj.total_chapters == 0
            # 正文子行级联清理
            contents = (
                await session.scalars(
                    select(ChapterContent).join(
                        Chapter, Chapter.id == ChapterContent.chapter_id
                    ).where(Chapter.project_id == proj.id)
                )
            ).all()
            assert contents == []
            # 版本快照行随章行 FK CASCADE 一并清理
            versions = (
                await session.scalars(
                    select(ChapterVersion)
                    .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
                    .where(Chapter.project_id == proj.id)
                )
            ).all()
            assert versions == []

    _run_async(_run())


# ── 章 CRUD ──────────────────────────────────────────────────────────────


def test_create_chapter_max_plus_one_no_embedded_list():
    async def _run():
        project = await _new_project("cc1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="第一卷")
            c1 = await _create_chapter(session, proj, "vol-1", title="第一章")
            c2 = await _create_chapter(session, proj, "vol-1", title="第二章")
            assert c1["ref"] == "vol-1-ch-1"
            assert c2["ref"] == "vol-1-ch-2"
            # 章族入库：DB 唯一属主，章/卷 YAML 均不落盘
            assert await storage.read_yaml(
                proj.root_path, "chapters/vol-1-ch-1.yaml"
            ) == {}
            assert await storage.read_yaml(proj.root_path, "volumes/vol-1.yaml") == {}
            # 行内即元数据
            row = await chapter_repo.get_by_ref(session, proj.id, "vol-1-ch-1")
            assert row.title == "第一章"
            assert row.chapter_no == 1
            # 计数同事务
            vol = await volume_repo.get_by_volume_no(session, proj.id, 1)
            assert vol.chapter_count == 2
            assert proj.total_chapters == 2

    _run_async(_run())


def test_save_prose_status_derivation_outline_to_writing():
    """状态机系统维护（PR2）：首次落非空正文 outline → writing。

    派生点在统一写入口 store.save_chapter —— 正文自动保存 / AI 写本章 /
    续写三条路径共用；空正文不动；writing 幂等；confirmed 不被改写。
    """

    async def _run():
        project = await _new_project("spd1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="第一卷")
            await _create_chapter(session, proj, "vol-1", title="第一章")

            from chapters.service import save_prose

            # save_prose 在独立 session 提交，用全新 session 读回防身份映射陈旧行
            async def _reload():
                async with async_session() as fresh:
                    return await chapter_repo.get_by_ref(fresh, proj.id, "vol-1-ch-1")

            # 空正文保存 → 仍是 outline（未开始写作不算派生）
            await save_prose(session, proj, "vol-1-ch-1", "")
            row = await _reload()
            assert row.status == "outline"

            # 首次非空正文 → 派生 writing（has_prose / outline_status 同步）
            await save_prose(session, proj, "vol-1-ch-1", "正文第一段。")
            row = await _reload()
            assert row.status == "writing"
            assert row.has_prose is True
            assert row.outline_status == "in_progress"

            # 再次保存幂等（仍是 writing，不回退）
            await save_prose(session, proj, "vol-1-ch-1", "正文第一段。续写。")
            row = await _reload()
            assert row.status == "writing"

            # confirmed 章保存正文不被派生改写（确认态由 confirm 端点独占）
            confirmed_row = await chapter_repo.get_by_ref(
                session, proj.id, "vol-1-ch-1"
            )
            confirmed_row.status = "confirmed"
            await session.commit()
            await save_prose(session, proj, "vol-1-ch-1", "确认后的正文修订。")
            row = await _reload()
            assert row.status == "confirmed"

    _run_async(_run())


def test_get_chapter_row_missing_returns_none():
    async def _run():
        project = await _new_project("sh1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            # 章族入库：无行即无章（文件自愈已随文件层移除）
            meta = await _get_chapter_row(session, proj, "vol-3-ch-1")
            assert meta is None

    _run_async(_run())


def test_cleanup_chapter_artifacts_gone_archives_cascade():
    """删章产物清理函数已废（PR④）：归档/提示词随章行 FK CASCADE，无需文件清理。"""
    from models.archive import Archive, ChapterPrompt

    async def _run():
        project = await _new_project("ca1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="第一卷")
            ch = await _create_chapter(session, proj, "vol-1", title="第一章")
            ref = ch["ref"]
            # 直接挂归档行 + 提示词行（模拟已归档已生成提示词的章）
            row = await chapter_repo.get_by_ref(session, proj.id, ref)
            session.add(Archive(chapter_id=row.id, title="第一章", summary="s", content="c"))
            session.add(ChapterPrompt(chapter_id=row.id, name="seg-1-prompt", content="p"))
            await session.commit()

            # 服务层路径：chapter_repo.delete 后行随 FK CASCADE
            await chapter_repo.delete(session, row.id)
            await session.commit()

            arch = await session.scalar(
                select(Archive).where(Archive.chapter_id == row.id)
            )
            prompt = await session.scalar(
                select(ChapterPrompt).where(ChapterPrompt.chapter_id == row.id)
            )
            assert arch is None, "归档行应随章行 CASCADE 删除"
            assert prompt is None, "提示词行应随章行 CASCADE 删除"

    _run_async(_run())


# ── service 包装（模块内统一异步 session 入口）─────────────────────────────


def test_chapter_structured_fields_roundtrip():
    """章纲结构化字段（扩列+11 子表）读写回环：统一写入口拆装、组装还原。"""

    async def _run():
        project = await _new_project("csfr1")
        async with async_session() as session:
            proj = await session.get(Novel, project.id)
            await _create_volume(session, proj, title="第一卷")
            await _create_chapter(session, proj, "vol-1", title="第一章")

            from workflow.engine import load_chapter, save_chapter

            full = {
                "volume": 1, "chapter": 1, "title": "第一章", "prose": "正文开头",
                "word_target": 2500,
                "outline": {
                    "summary": "主角在城中村落脚，地头蛇上门。",
                    "location": "城中村面馆",
                    "time": "初秋傍晚",
                    "narrative_pov": "第三人称有限",
                    "perspective_guidance": "贴着主角写",
                    "key_points": ["[推进剧情·对话]主角拒绝上供", "[造悬念]刀疤男在门外"],
                    "characters": ["林拓", "刀疤男"],
                },
                "memo": {
                    "current_task": "守住面馆不低头",
                    "reader_expectation": {
                        "state": "担心主角安危",
                        "strategy": "must_resolve",
                        "detail": "读者在等地头蛇出招",
                    },
                    "payoff_plan": {
                        "must_resolve": ["上供冲突落地"],
                        "must_hold": ["师父死因悬念"],
                        "partial_advance": ["仇家线索+1"],
                    },
                    "downtime_functions": ["收摊夜谈：交代背景"],
                    "key_choices": ["拒交保护费：验证不低头人设"],
                    "required_changes": ["关系：与地头蛇撕破脸", "信息：得知哥哥失踪"],
                    "prohibitions": ["不让主角直接动手"],
                },
                "emotional_design": {
                    "primary_mood": "紧张",
                    "mood_progression": "平静→警觉→对峙",
                    "intensity_peak": "保护费摊牌对峙",
                    "intensity_level": 7,
                    "emotional_hook": "门外刀疤男",
                },
                "scene_cards": [
                    {"scene_name": "傍晚面馆", "goal": "拒交保护费",
                     "obstacle": "地头蛇威胁", "hook": "门外来了人"},
                ],
                "knowledge_states": [
                    {"character_name": "林拓", "knows": "哥哥曾来过此城",
                     "unknowns": "哥哥现状", "gap_relation": "仇家知道哥哥下落",
                     "gap_change": "无→怀疑"},
                ],
                "segments": [
                    {"summary": "拒交保护费", "target_words": 1200, "goal": "守住底线",
                     "emotional_tone": "紧张", "characters": ["林拓", "地头蛇"],
                     "function": "主线推进"},
                ],
            }
            await save_chapter(proj.root_path, "vol-1-ch-1", full)
            data = await load_chapter(proj.root_path, "vol-1-ch-1")

            assert data["title"] == "第一章"
            assert data["prose"] == "正文开头"
            assert data["word_target"] == 2500
            out = data["outline"]
            assert out["summary"] == "主角在城中村落脚，地头蛇上门。"
            assert out["location"] == "城中村面馆"
            assert out["time"] == "初秋傍晚"
            assert out["narrative_pov"] == "第三人称有限"
            assert out["perspective_guidance"] == "贴着主角写"
            assert out["key_points"] == [
                "[推进剧情·对话]主角拒绝上供", "[造悬念]刀疤男在门外",
            ]
            assert out["characters"] == ["林拓", "刀疤男"]
            memo = data["memo"]
            assert memo["current_task"] == "守住面馆不低头"
            assert memo["reader_expectation"]["state"] == "担心主角安危"
            assert memo["reader_expectation"]["strategy"] == "must_resolve"
            assert memo["payoff_plan"]["must_resolve"] == ["上供冲突落地"]
            assert memo["payoff_plan"]["must_hold"] == ["师父死因悬念"]
            assert memo["payoff_plan"]["partial_advance"] == ["仇家线索+1"]
            assert memo["downtime_functions"] == ["收摊夜谈：交代背景"]
            assert memo["key_choices"] == ["拒交保护费：验证不低头人设"]
            assert memo["required_changes"] == [
                "关系：与地头蛇撕破脸", "信息：得知哥哥失踪",
            ]
            assert memo["prohibitions"] == ["不让主角直接动手"]
            emo = data["emotional_design"]
            assert emo["primary_mood"] == "紧张"
            assert emo["mood_progression"] == "平静→警觉→对峙"
            assert emo["intensity_level"] == 7
            assert emo["emotional_hook"] == "门外刀疤男"
            assert data["scene_cards"][0]["scene_name"] == "傍晚面馆"
            assert data["scene_cards"][0]["obstacle"] == "地头蛇威胁"
            ks = data["knowledge_states"][0]
            assert ks["character_name"] == "林拓"
            assert ks["gap_relation"] == "仇家知道哥哥下落"
            seg = data["segments"][0]
            assert seg["summary"] == "拒交保护费"
            assert seg["target_words"] == 1200
            assert seg["goal"] == "守住底线"
            assert seg["emotional_tone"] == "紧张"
            assert seg["characters"] == ["林拓", "地头蛇"]
            assert seg["function"] == "主线推进"

            # 子表整体替换：key_points 换一条，其余族不动
            full["outline"]["key_points"] = ["[过渡]收摊打烊"]
            await save_chapter(proj.root_path, "vol-1-ch-1", full)
            data2 = await load_chapter(proj.root_path, "vol-1-ch-1")
            assert data2["outline"]["key_points"] == ["[过渡]收摊打烊"]
            assert data2["outline"]["characters"] == ["林拓", "刀疤男"]
            assert len(data2["memo"]["payoff_plan"]["must_resolve"]) == 1
            assert len(data2["segments"]) == 1

    _run_async(_run())


async def _create_volume(session, project, *, title, summary="", vol_num=None):
    from volumes.service import create_volume

    return await create_volume(
        session, project, title=title, summary=summary
    )


async def _list_volumes(session, project):
    from volumes.service import list_volumes

    return await list_volumes(session, project)


async def _get_volume(session, project, ref):
    from volumes.service import get_volume

    return await get_volume(session, project, ref)


async def _update_volume(session, project, ref, body):
    from volumes.schemas import VolumeUpdate
    from volumes.service import update_volume

    return await update_volume(session, project, ref, VolumeUpdate(**body))


async def _delete_volume(session, project, ref):
    from volumes.service import delete_volume

    return await delete_volume(session, project, ref)


async def _create_chapter(session, project, volume_ref, *, title):
    from chapters.service import create_chapter

    return await create_chapter(session, project, volume_ref, title)


async def _get_chapter_row(session, project, ref):
    from chapters.service import get_chapter_row

    return await get_chapter_row(session, project, ref)
