"""人味检测端点（c-renwei-check）：POST /api/novels/{id}/chapters/{ref}/renwei-check。

门禁口径是本能力的关键契约：**只挂登录**——不挂档位门、不挂 Key 门、无配置态；
0 模型 0 额度 0 外发。用例覆盖：200 契约、短章打不了分、空正文 400、404、免档位。
"""

import asyncio
import os
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from auth_local.middleware import get_current_user
from db import async_session
from main import app
from models.chapter import Chapter, ChapterContent
from models.project import Novel
from models.user import User
from models.volume import Volume

_UIDS: dict[str, str] = {}

LONG_PROSE = (
    "巡灯是亥时来的，光贴着水面一寸一寸扫过来的时候，阿槎正把最后半碗咸鱼粥推给陆沉……"
    "粥凉了，结了层薄油皮，腥气呛得嗓子发紧。\n"
    "「吃。」阿槎把碗往他手边又推了推，「查完这趟，天就该亮了。」\n"
    "陆沉没接话，几口把粥扒完，把碗扣在膝上，指甲一下一下刮着碗沿……"
    "巡灯的光从船头量到船尾，停了停，很快又退回去……船上只剩灯芯偶尔爆的一声轻响。\n"
    "「没查我们？还是查了没说！」\n"
    "「查的是灯。」阿槎朝桅顶努了努嘴，那盏旧灯照旧挂着，晃晃悠悠，"
    "把两个人的影子投在舱板上，一会儿长，一会儿短。\n"
    "陆沉盯着那点灯火看了半晌，忽然把袖子里的图按了按……还在。\n"
    "潮水开始涨了，缆绳绷紧又松开，绷紧又松开，像船在夜里慢慢呼吸……"
    "夜里最磨人的不是黑，是等。\n"
    "他把水位的记号又看了一遍，刻度在水线下面一点点爬，爬得不快，但一直在爬……\n"
    "「什么时辰了？」\n"
    "「丑时过半。」陆沉看了看水位的记号，「再有一个时辰，进暗礁区。」\n"
    "「潮水几点转？」\n"
    "「卯时。」陆沉竖起一根手指，「进礁区之前，还有一涨。」\n"
    "阿槎没再问，呼吸又匀了……\n"
    "后半夜，风换了方向，从岛那边过来，带着潮水的凉意，把舱里那点浊气换了换……\n"
    "潮声一层压着一层，从远处的礁区滚过来，到了船底，散成细碎的响……\n"
    "他数潮。数到一百，乱了，重新数……\n"
    "水一滴一滴从船板上退回去，退潮的节奏比涨潮慢……\n"
    "灯影里，阿槎已经靠着舱门睡着了，手里还攥着那把刀，指节松了一圈。\n"
    "夜航的门道他比谁都熟，什么时候换岗，什么时候点灯，什么时候该把图贴身收着……\n"
    "他把这几天的潮时在心里排了一遍，明晚是单日，灯可以点得稍晚一些……\n"
    "按港里的规矩，查完灯就该装睡，陆沉把灯芯捻暗了半分，和衣躺下……\n"
    "夜航的门道他比谁都熟，什么时候换岗，什么时候点灯，什么时候该把图贴身收着……\n"
    "灯影在舱壁上晃，把梁的影子拉长又缩短，他盯着那道梁看了很久，直到眼睛发酸……\n"
    "前半夜的潮最稳，稳得能听见自己的心跳，一下，一下，跟潮错开半拍……\n"
    "阿槎翻了个身，说了半句梦话，没说完整，只剩两个字的尾音……\n"
    "陆沉应了一声，也不知道阿槎听见没有，舱里又静下来，只剩缆绳的吱呀……\n"
    "睡意是一阵一阵来的，来的时候沉，退的时候耳朵反而更尖……\n"
    "水声贴着船底走，从缓到急，又从急到缓，一圈一圈，跟着潮的性子……\n"
    "潮头一次比一次高，船身抬起的角度也一次比一次明显，连舱门都跟着吱呀了一声……\n"
    "他把碗摞好，收进桶里，又把桶往舱角推了推，免得船身一晃叮当响……\n"
    "水位在涨，船身一点点抬高，系缆的绳子绷出新的角度……\n"
    "门缝里透进来的风变凉了，是后半夜的凉，露水气顺着门缝爬进来……\n"
    "他把外衣裹紧了些，凉意从脚底爬上来，爬到膝盖，就停在那儿，不往上走……\n"
    "夜里的时间走得慢，黑不可怕，等才磨人，这是夜航的规矩。\n"
    "潮声里偶尔夹一声两声鱼跳，啪的一声，很快归于安静……\n"
    "陆沉把水位的记号又看了一遍，刻度在水线下面一点点爬，爬得不快，但一直在爬……\n"
    "他数潮，数到一百，乱了，重新数……\n"
    "港口那边传来一声闷响，像是谁把跳板放了下来……\n"
    "阿槎的刀横在膝上，刀鞘被月光照出一道白边……\n"
    "陆沉把图角又按了按，纸的边角已经被他摸得发毛……\n"
    "舱里没有人说话，只有呼吸和潮声混在一起……\n"
    "风从岛那边绕过来，带着咸味和一点湿木头的气息……\n"
    "远处的礁区黑得比别处更沉，浪打上去，碎成一蓬白沫……\n"
    "阿槎睁开眼，看了看水位的记号，又闭上……\n"
    "陆沉把舵位让给阿槎，自己靠着舱门坐下，刀放在手边……\n"
    "潮水把船推得微微偏了一点，又被缆绳拉了回来……\n"
    "他想起白天码头上的那场争执，想起那些没有说出口的话……\n"
    "灯芯又爆了一下，火苗矮了半分，又慢慢立起来……\n"
    "阿槎低声说了句什么，被风吹散了大半，只剩「图」和「信」两个字……\n"
    "陆沉没有回头，只把手在袖口上按了按……\n"
    "港里的梆子又响了一遍，一声比一声远……\n"
    "再过一会儿，巡灯就该折返了，折返之后，这条水道就只剩他们……\n"
    "他把这些都记在心里，像记潮时一样，一条一条排好……\n"
    "船身轻轻一晃，把两个人的影子从舱板上摇开，又摇回原处……\n"
    "后半夜的潮退得慢，水线一寸一寸往下挪，露出船板上一道旧的水痕……\n"
    "阿槎把刀鞘上的绳结解开又系上，系了三遍，才把结打在顺手的位置……\n"
    "陆沉看着那道旧水痕，忽然想起这船第一次下水的时候，船板上还没有这么多道痕……\n"
    "风停了一阵，甲板上安静得能听见灯芯烧着的细响……\n"
    "远处的巡灯转了半圈，又转回去，像在犹豫要不要过来……\n"
    "没有人抬头。所有人的眼睛都在暗处，跟着那点光走……\n"
    "光退回去的时候，舱里有人轻轻吐了口气，像是把一整夜的气都吐了出来……\n"
    "陆沉把手从袖口上拿开，掌心全是汗，风一吹，凉得发紧……\n"
    "阿槎低声说，差不多了。陆沉点头，起身，把刀递过去……\n"
)


async def _seed(prose: str, *, ref: str = "vol-1-ch-1", chapter_no: int = 1) -> str:
    root = tempfile.mkdtemp(prefix="test_renwei_")
    uid = f"rw-{os.path.basename(root)[-12:]}"
    async with async_session() as session:
        session.add(User(
            id=uid, email=f"{uid}@test.local", password_hash="x",
            display_name="人味测试", api_key="", api_base_url="", api_model="",
        ))
        session.add(Novel(
            user_id=uid, name="人味书", slug=f"rw-{os.path.basename(root)}", root_path=root,
            source="manual", current_phase="write",
        ))
        await session.flush()
        proj = (await session.scalars(select(Novel).where(Novel.root_path == root))).one()
        vol = Volume(project_id=proj.id, volume_no=1, title="第一卷")
        session.add(vol)
        await session.flush()
        ch = Chapter(
            project_id=proj.id, volume_id=vol.id, chapter_no=chapter_no,
            ref=ref, title="第1章", status="writing", has_prose=bool(prose),
        )
        session.add(ch)
        await session.flush()
        session.add(ChapterContent(chapter_id=ch.id, prose=prose))
        await session.commit()
        _UIDS[proj.id] = uid
        return proj.id


def _post(nid: str, ref: str = "vol-1-ch-1"):
    c = TestClient(app)
    c.__enter__()
    app.dependency_overrides[get_current_user] = lambda: {"id": _UIDS[nid]}
    try:
        return c.post(f"/api/novels/{nid}/chapters/{ref}/renwei-check")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        c.__exit__(None, None, None)


def test_endpoint_returns_full_report():
    nid = asyncio.run(_seed(LONG_PROSE))
    r = _post(nid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["chars"] > 0
    assert len(body["metrics"]) == 19
    assert body["score"] is not None
    assert body["score"]["band"] in ("很像人", "边缘", "偏机器", "机器味重")
    assert isinstance(body["findings"], list)
    # findings 契约：0-based 段序＋摘录三件套＋为什么/怎么改
    for f in body["findings"]:
        assert {"rule_id", "rule", "sev", "para", "before", "hit", "after", "why", "fix"} <= set(f)
        assert isinstance(f["para"], int) and f["para"] >= 0


def test_endpoint_short_chapter_no_rate():
    nid = asyncio.run(_seed("他按住她的手——掌心一片凉。\n「三更了。」陆沉说。"))
    r = _post(nid)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["short_chapter"] is True
    assert body["score"] is None
    assert body["priorities"] == []
    assert any(f["rule_id"] == "dash" for f in body["findings"])


def test_endpoint_empty_prose_400():
    nid = asyncio.run(_seed(""))
    r = _post(nid)
    assert r.status_code == 400


def test_endpoint_missing_chapter_404():
    nid = asyncio.run(_seed(LONG_PROSE))
    r = _post(nid, ref="vol-9-ch-9")
    assert r.status_code == 404


def test_endpoint_has_no_tier_or_key_gate():
    """只挂登录：不注入任何档位/Key 依赖也不 403/503（免费作家直接可用）。"""
    nid = asyncio.run(_seed(LONG_PROSE))
    r = _post(nid)
    assert r.status_code == 200, r.text


def test_endpoint_deterministic():
    nid = asyncio.run(_seed(LONG_PROSE))
    a = _post(nid).json()
    b = _post(nid).json()
    assert a["metrics"] == b["metrics"]
    assert a["score"] == b["score"]
    assert a["findings"] == b["findings"]
