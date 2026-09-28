"""提示词组装来源端点测试（prompt-sources，storyline.html 四期尾）。

覆盖：六来源固定行序与标签、chars/total 一致、各处来源的真实组装投影
（题材/前提、量化基线＋本章影子覆盖标记、禁用词单源、伏笔真表、角色投影）、
空来源 empty 标记（卷纲未填）。
"""

import asyncio
import json
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.middleware import get_current_user
from db import async_session
from filesystem.storage import get_storage
from main import app
from models.chapter import Chapter, ChapterCharacter
from models.hook import NovelHook
from models.project import Novel
from models.volume import Volume

REF = "vol-1-ch-1"
# c-chapter-dossier：第七处来源「故事状态（截至上章）」追加（章档已采纳折叠态）
LABELS = [
    "全书设定",
    "大纲 · 卷纲",
    "本章章纲",
    "全书文风 ＋ 本章调整",
    "伏笔进展 · 截至上一章",
    "本章涉及角色",
    "故事状态（截至上章）",
]


async def _seed(plots: list | None = None) -> tuple[str, str]:
    root = tempfile.mkdtemp(prefix="test_prompt_sources_")
    slug = f"psrc-{os.path.basename(root)}"
    async with async_session() as session:
        session.add(Novel(
            user_id="psrc_user", name="来源书", slug=slug,
            root_path=root, source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(
            select(Novel).where(Novel.root_path == root)
        )).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=1,
            ref=REF, title="第1章", status="outline",
            summary="林晚在渡口等一班不存在的船。",
        )
        if plots:
            ch.plot_items = json.dumps(plots, ensure_ascii=False)
        # 本章文风影子：syntax 行覆盖基线（提示词来源应显示「本章覆盖」）
        ch.style_shadow = json.dumps(
            {"syntax": {"value": "短句为主", "reason": "打斗章节奏"}}, ensure_ascii=False
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterCharacter(chapter_id=ch.id, sort_order=1, character_name="林晚"))
        session.add(NovelHook(
            novel_id=proj.id, seq=1, description="谁在暗中跟着她",
            type="mystery", priority=1, status="active",
        ))
        await session.commit()

    st = get_storage()
    await st.write_yaml(root, "story.yaml", {"synopsis": "一封匿名信牵出旧案。"})
    await st.write_yaml(root, "settings/goal.yaml", {})  # 占位热身（无内容容忍）
    await st.write_yaml(root, "settings/writing-style.yaml", {"banned_words": ["突然"]})
    await st.write_yaml(root, "settings/style-quant.yaml", {
        "confidence": 88,
        "baseline": {"syntax": {"value": "中长句为主", "tolerance": 10, "locked": False}},
    })
    return root, proj.id


def _get(nid: str):
    with TestClient(app) as c:
        app.dependency_overrides[get_current_user] = lambda: {"id": "psrc_user"}
        r = c.get(f"/api/novels/{nid}/chapters/{REF}/prompt-sources")
        app.dependency_overrides.clear()
        return r


class TestPromptSources:
    def test_labels_order_total_and_projection(self):
        _root, nid = asyncio.run(_seed())
        r = _get(nid)
        assert r.status_code == 200, r.text
        d = r.json()
        sources = d["sources"]
        assert [s["label"] for s in sources] == LABELS
        assert [s["key"] for s in sources] == [
            "book", "volume", "outline", "style", "hooks", "cast", "story_state",
        ]
        assert d["total_chars"] == sum(s["chars"] for s in sources)

        by_key = {s["key"]: s for s in sources}
        # ① 全书设定：故事前提
        assert "匿名信牵出旧案" in by_key["book"]["preview"]
        # ② 卷纲未填 → empty
        assert by_key["volume"]["empty"] is True and by_key["volume"]["chars"] == 0
        # ③ 章纲：概要 + 出场角色；关键情节点与场景行随 c-og-slim-v2 退役
        assert "等一班不存在的船" in by_key["outline"]["preview"]
        assert "关键情节点" not in by_key["outline"]["preview"]
        assert "场景：" not in by_key["outline"]["preview"]
        # 剧情条目空则不计（c-plot-split）
        assert "剧情条目" not in by_key["outline"]["preview"]
        # ④ 文风：影子行覆盖基线（本章覆盖标记）+ 禁用词单源
        style = by_key["style"]
        assert "短句为主" in style["preview"]
        assert "本章覆盖：打斗章节奏" in style["preview"]
        assert "中长句为主" not in style["preview"]
        assert "禁用词：突然" in style["preview"]
        # ⑤ 伏笔：真表 active 注入
        assert "谁在暗中跟着她" in by_key["hooks"]["preview"]
        # ⑥ 本章涉及角色（认知层投影入口）
        assert "林晚" in by_key["cast"]["preview"]
        assert d["cast_count"] == 1

    def test_plot_items_in_outline_source(self):
        """4.3（c-plot-split）：剧情条目计入「本章章纲」来源（一条一行），
        chars 计入该行与总数；六处行序不变。"""
        plots = ["甲一：她翻墙进了库房", "乙一：灯下的账册是假的", "丙一：她吹熄了灯"]
        _root, nid = asyncio.run(_seed(plots=plots))
        r = _get(nid)
        assert r.status_code == 200, r.text
        d = r.json()
        assert [s["label"] for s in d["sources"]] == LABELS
        outline = {s["key"]: s for s in d["sources"]}["outline"]
        assert "剧情条目：" in outline["preview"]
        for p in plots:
            assert p in outline["preview"]
        assert outline["chars"] >= sum(len(p) for p in plots)
        assert d["total_chars"] == sum(s["chars"] for s in d["sources"])

    def test_not_found(self):
        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "psrc_user"}
            r = c.get("/api/novels/nope/chapters/vol-1-ch-1/prompt-sources")
            app.dependency_overrides.clear()
        assert r.status_code == 404

    def test_missing_chapter_404(self):
        """章不存在 → 404（不得回 200 全空来源，与 style-shadow/推演同语义）。"""
        _root, nid = asyncio.run(_seed())
        with TestClient(app) as c:
            app.dependency_overrides[get_current_user] = lambda: {"id": "psrc_user"}
            r = c.get(f"/api/novels/{nid}/chapters/vol-1-ch-9/prompt-sources")
            app.dependency_overrides.clear()
        assert r.status_code == 404
