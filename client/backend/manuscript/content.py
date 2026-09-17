"""成稿内容装配单点（c-manuscript-download PR2）。

内容边界 = 读者最终读到的：主线正文（题名 + 正文段落），按卷/章序。
- 主线判定唯一入口 chapters/scope.py::mainline_stmt（ghost_of IS NULL——同时
  排除重写型 `-r{8hex}` 与回退型保原 ref 两种旧稿支线）；消费面登记表第 6 项。
- 只收 has_prose 为真的章（与预览目录/概览口径同源，空章跳过）。
- 正文在 chapter_contents（Chapter.content relationship），不在 Chapter 行上。
渲染器（render.py）只消费本模块产出的 Manuscript 结构，不各自查库。
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from chapters.scope import mainline_stmt
from models.chapter import Chapter
from models.volume import Volume


@dataclass
class ManuscriptChapter:
    no: int
    title: str
    prose: str


@dataclass
class ManuscriptVolume:
    no: int
    title: str
    chapters: list[ManuscriptChapter] = field(default_factory=list)


@dataclass
class Manuscript:
    title: str
    volumes: list[ManuscriptVolume] = field(default_factory=list)

    @property
    def chapter_count(self) -> int:
        return sum(len(v.chapters) for v in self.volumes)

    @property
    def word_count(self) -> int:
        """字数口径与章 store 的 count_chars 同族：去空白计数。"""
        return sum(
            len("".join(ch.prose.split()))
            for v in self.volumes
            for ch in v.chapters
        )


async def build_manuscript(db, project) -> Manuscript:
    """装配主线成稿。只消费 db（调用方持会话），零副作用。"""
    vol_rows = (
        await db.scalars(
            select(Volume)
            .where(Volume.project_id == project.id)
            .order_by(Volume.volume_no)
        )
    ).all()
    ch_rows = (
        await db.scalars(
            mainline_stmt(project.id)
            .where(Chapter.has_prose.is_(True))
            .options(selectinload(Chapter.content))
            .order_by(Chapter.volume_id, Chapter.chapter_no)
        )
    ).all()

    # 卷序 = volume_no（chapters 按 volume_id（UUID）排序无意义，必须按卷表序组装）
    ms = Manuscript(title=project.name)
    by_vol: dict[str, ManuscriptVolume] = {}
    for v in vol_rows:
        mv = ManuscriptVolume(no=v.volume_no, title=v.title)
        by_vol[v.id] = mv
        ms.volumes.append(mv)
    for ch in ch_rows:
        mv = by_vol.get(ch.volume_id)
        if mv is None:  # 卷已被删的孤儿章（理论不可达，防御）
            continue
        prose = (ch.content.prose if ch.content else "") or ""
        mv.chapters.append(ManuscriptChapter(no=ch.chapter_no, title=ch.title, prose=prose))
    # 没有正文章的空卷不出现在成稿里
    ms.volumes = [mv for mv in ms.volumes if mv.chapters]
    return ms
