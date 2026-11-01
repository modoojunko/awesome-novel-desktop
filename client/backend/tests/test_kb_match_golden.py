"""写法块选择器 golden 集（c-kb-write-block 批E E2——spec 硬闸进 CI）。

- fixture：7 场面类 × 5 章（措辞取各别名表真实别名）＋无信号章 2（一走通用兜底、
  一走零命中 None）＝37 章；知识库 seed 每类「命中手法×1＋他类手法×1＋无条件手法×1
  ＋场景文风×1＋场景文笔×1」（走 create_entry 真实闸门口径）。
- 确定性三锁：seed 后 updated_at 冻结；select_block(now=固定)；prefs 不 seed
  （有用率全 1.0）；角色插入序固定。
- 断言：只钉 id 序列（不钉 score/reason/块文本）；零命中章断言 None；
  不变式：配额（手法≤6/场景定性≤4）、双跑确定性、预算≤3200 字符、
  跨 run 影子泄漏=0（量化条目不出现在任何章的块里）。
- 重录：REGEN=1 pytest 本文件 → 重录 expected 并跑不变式自验证（防录进退化结果）。
"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select as sel
from sqlalchemy import update as _upd

from db import async_session
from kb.match import select_block
from models.chapter import Chapter
from models.kb import KbEntry
from models.project import Novel
from models.user import User
from models.volume import Volume
from write.write_block import extract_signals

GOLDEN_DIR = Path(__file__).parent / "golden" / "kb_match"
NOW = datetime(2026, 11, 2, 12, 0, 0)

# 7 场面类 × 每类 5 章的章纲措辞（取各别名表真实别名——顺带是 E1 判例放大集）
_SCENE_CHAPTER_TEXTS = {
    "打斗": ["与山贼正面交锋，硬撼对方底牌", "巷口两人交手，招招夺命", "深夜偷袭敌营，火光四起",
             "两军对垒厮杀整夜", "船头对决，刀光映水"],
    "文戏": ["两人在茶楼谈心，各怀心事", "炉边闲聊，话里带话", "她终于开口表白，他沉默",
             "师徒谈天，说到旧事", "灯下对话，句句机锋"],
    "开篇": ["新书第一章，主角登场亮相", "开场即是雪夜入城", "首章引入少年出山",
             "开局起手落子无回", "大幕拉开主角初露锋芒"],
    "转折": ["密信揭底，局势急转", "真相揭穿，满座哗然", "一夜之间局面翻盘",
             "突然生变，前约尽废", "旧案重提，案情急转"],
    "收尾": ["这一卷落幕，众人散场", "恩怨了结，收刀入鞘", "故事尾声，渡口送别",
             "尘埃落定，收场的一幕", "终局终结，封刀归山"],
    "对峙": ["两帮人马街头僵持", "隔桌谈判，寸步不让", "殿上对视，杀意暗涌",
             "冷战三日，谁都不肯先动", "囚室博弈，一句一刀"],
    "日常": ["市井烟火的一天", "柴米油盐的生活流水", "小镇集市闲逛半日",
             "平凡日子里的一顿晚饭", "午后无事，生活继续"],
}
_NO_SIGNAL_CHAPTERS = [
    {"ref": "g-nosig-1", "summary": "整理行囊，闲话家常", "mood": "", "stage": "", "items": []},
    {"ref": "g-nosig-2", "summary": "", "mood": "", "stage": "", "items": []},
]

# 知识库 seed：每场面类一组（走 create_entry 口径；genre 空＝跨题材通用）
def _seed_entries() -> list[dict]:
    out = []
    for scene in _SCENE_CHAPTER_TEXTS:
        out.append({"concept": "手法", "title": f"{scene}·命中手法",
                    "payload": {"instruction": f"{scene}场面：先守后攻，见招拆招。", "scene": scene},
                    "instruction": f"{scene}场面：先守后攻，见招拆招。"})
        out.append({"concept": "手法", "title": f"{scene}·他类手法",
                    "payload": {"instruction": f"{scene}备用：声东击西。", "scene": scene},
                    "instruction": f"{scene}备用：声东击西。", "when": {"scene": "收尾" if scene != "收尾" else "打斗"}})
        out.append({"concept": "手法", "title": f"{scene}·通用手法",
                    "payload": {"instruction": f"{scene}通用：对话不要每次说完。", "scene": "日常"},
                    "instruction": f"{scene}通用：对话不要每次说完。"})
        out.append({"concept": "文风", "title": f"{scene}·场景基调",
                    "payload": {"slot": "tone", "text": f"{scene}基调要稳。"},
                    "instruction": f"{scene}基调要稳。", "when": {"scene": scene}})
        out.append({"concept": "文笔", "title": f"{scene}·场景句式",
                    "payload": {"slot": "rule", "rule": f"{scene}一句不超过22字。"},
                    "instruction": f"{scene}一句不超过22字。", "when": {"scene": scene}})
    return out


def _chapters_fixture() -> list[dict]:
    out = []
    for scene, texts in _SCENE_CHAPTER_TEXTS.items():
        for i, text in enumerate(texts, 1):
            out.append({
                "ref": f"g-{scene}-{i}", "summary": text,
                "mood": {"打斗": "燃", "文戏": "静", "开篇": "疑", "转折": "疑",
                         "收尾": "静", "对峙": "冷", "日常": "甜"}.get(scene, ""),
                "stage": "高潮爆发" if scene == "打斗" else "",
                "items": [f"{text}（续）"], "characters": ["沈青崖"],
            })
    out.extend(_NO_SIGNAL_CHAPTERS)
    return out


async def _seed_all(uid: str) -> dict[str, str]:
    """播种用户＋章纲＋知识库。返回 ref→chapter_row_id（无意义，只保 ref 稳定）。"""
    from kb.service import create_entry

    async with async_session() as db:
        db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x", display_name="golden"))
        novel = Novel(
            user_id=uid, name="golden书", slug=f"g{uuid.uuid4().hex[:10]}",
            root_path=f"./data/g{uuid.uuid4().hex[:10]}", source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        vol = Volume(project_id=novel.id, volume_no=1, title="卷")
        db.add(vol)
        await db.flush()
        for i, ch in enumerate(_chapters_fixture(), 1):
            db.add(Chapter(
                project_id=novel.id, volume_id=vol.id, chapter_no=i, ref=ch["ref"],
                title=ch["ref"], summary=ch["summary"], primary_mood=ch["mood"] or None,
                plot_stage=ch["stage"] or None,
                plot_items=json.dumps(ch["items"], ensure_ascii=False),
            ))
        entry_ids: dict[str, str] = {}
        for e in _seed_entries():
            entry, _gate, err = await create_entry(
                db, user_id=uid, genre="", concept=e["concept"], title=e["title"],
                payload=e["payload"], instruction=e["instruction"],
                when_json=e.get("when"),
            )
            assert entry is not None, str(err)
            entry_ids[e["title"]] = entry.id
        # 确定性锁①：updated_at 冻结（select_block 新鲜度输入）
        await db.execute(
            _upd(KbEntry).where(KbEntry.user_id == uid)
            .values(updated_at=NOW - timedelta(days=1))
        )
        await db.commit()
        return {"novel_id": novel.id, "entries": entry_ids}


def _run(coro):
    return asyncio.run(coro)


def test_golden_选集一致率与不变式():
    """REGEN=1 重录 expected；否则逐章断言 id 序列一致（spec 硬闸 100%）。"""
    uid = f"golden-{uuid.uuid4().hex[:8]}"
    seeded = _run(_seed_all(uid))
    chapters = _chapters_fixture()

    async def _select_all():
        out = {}
        async with async_session() as db:
            for ch in chapters:
                signals = await extract_signals(
                    db, novel_id=seeded["novel_id"], chapter_ref=ch["ref"], genre=""
                )
                selr = await select_block(
                    db, user_id=uid, signals=signals, genre="", now=NOW
                )
                out[ch["ref"]] = {
                    "signals": signals.brief(),
                    "ids": [i.entry.id for i in selr.items] if selr else None,
                }
        return out
    actual = _run(_select_all())

    # title→id 映射（expected 用 title 序列存盘，可读＋不受 id 随机影响）
    id_to_title = {v: k for k, v in seeded["entries"].items()}

    regen = __import__("os").environ.get("REGEN") == "1"
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    expected_path = GOLDEN_DIR / "expected.json"
    golden = {ref: rec["ids"] and [id_to_title[i] for i in rec["ids"]] for ref, rec in actual.items()}
    if regen or not expected_path.exists():
        expected_path.write_text(json.dumps(golden, ensure_ascii=False, indent=1))
    expected = json.loads(expected_path.read_text())

    # ── 一致率 100%（spec 硬闸）──
    mismatch = {
        ref: {"expected": expected.get(ref), "actual": rec["ids"] and [id_to_title[i] for i in rec["ids"]]}
        for ref, rec in actual.items()
        if expected.get(ref) != (rec["ids"] and [id_to_title[i] for i in rec["ids"]])
    }
    if mismatch:
        (GOLDEN_DIR / "last_mismatch.json").write_text(
            json.dumps(mismatch, ensure_ascii=False, indent=1)
        )
    assert not mismatch, f"golden 漂移 {len(mismatch)} 章——详见 tests/golden/kb_match/last_mismatch.json"

    # ── 无信号章口径（spec：仅通用兜底，不含题材场景条目）──
    async def _nosig_check():
        async with async_session() as db:
            ids = actual["g-nosig-2"]["ids"] or []
            scenes = []
            for eid in ids:
                row = await db.get(KbEntry, eid)
                w = json.loads(row.when_json or "{}")
                if w.get("scene"):
                    scenes.append(row.title)
            return ids, scenes
    _nosig_ids, nosig_scenes = _run(_nosig_check())
    assert nosig_scenes == []  # 无信号章不出任何带场面条件的条目（通用兜底可出）

    # ── 不变式：配额／确定性／预算 ──
    for ch in chapters:
        rec = actual[ch["ref"]]
        if rec["ids"] is None:
            continue
        ids_now = list(rec["ids"])  # 绑定循环变量（B023）
        async def _concepts(ids=ids_now):
            async with async_session() as db:
                return [(await db.get(KbEntry, eid)).concept for eid in ids]
        row_concepts = _run(_concepts())
        n_tech = row_concepts.count("手法")
        n_style = len(row_concepts) - n_tech
        assert n_tech <= 6 and n_style <= 4, f"{ch['ref']} 超配额：手法{n_tech}/写法{n_style}"
    # 双跑确定性：任抽一章再跑一遍 id 序列不变
    ref = chapters[0]["ref"]
    again = _run(_select_all())[ref]["ids"]
    assert again == actual[ref]["ids"]


def test_golden_跨run影子泄漏为零():
    """C4 扩展（批E）：量化条目命中且书有基线时→转影子不进块；断言「同槽双写=0」
    ＋跨 run 影子泄漏=0（素材变化后旧「知识库·」行被清，不残留注入）。"""
    from models.chapter import Chapter as _Chapter
    from write.write_block import _clear_kb_shadow_rows, _split_quantitative

    uid = f"goldensh-{uuid.uuid4().hex[:8]}"

    async def _seed():
        from filesystem.paths import STYLE_QUANT_PATH
        from filesystem.storage import get_storage
        from kb.service import create_entry

        async with async_session() as db:
            db.add(User(id=uid, email=f"{uid}@t.local", password_hash="x"))
            novel = Novel(
                user_id=uid, name="影子golden", slug=f"gs{uuid.uuid4().hex[:10]}",
                root_path=f"./data/gs{uuid.uuid4().hex[:10]}",
                source="manual", current_phase="write",
            )
            db.add(novel)
            await db.flush()
            vol = Volume(project_id=novel.id, volume_no=1, title="卷")
            db.add(vol)
            await db.flush()
            db.add(_Chapter(
                project_id=novel.id, volume_id=vol.id, chapter_no=1, ref="gs-1",
                title="打斗章", summary="与老祖正面交锋", primary_mood="燃",
                plot_stage="高潮爆发",
            ))
            quant, _g, e1 = await create_entry(
                db, user_id=uid, genre="", concept="文笔",
                title="打斗句长", payload={"slot": "rule", "rule": "交手时句长不超过12字"},
                instruction="交手时句长不超过12字", when_json={"scene": "打斗"},
            )
            assert quant is not None, str(e1)
            await get_storage().write_yaml(
                novel.root_path, STYLE_QUANT_PATH,
                {"confidence": 80, "baseline": {"syntax": {"value": "约18字", "tolerance": 20}}},
            )
            await db.commit()
            return novel.id, quant.id
    novel_id, quant_id = _run(_seed())

    async def _select_and_split():
        async with async_session() as db:
            signals = await extract_signals(db, novel_id=novel_id, chapter_ref="gs-1", genre="")
            selr = await select_block(db, user_id=uid, signals=signals, genre="", now=NOW)
            assert selr is not None and any(i.entry.id == quant_id for i in selr.items)
            ch = await db.get(_Chapter, (await db.execute(
                sel(_Chapter.id).where(_Chapter.project_id == novel_id)
            )).scalar_one())
            selr2 = await _split_quantitative(
                db, chapter_id=ch.id, selection=selr,
            )
            await db.commit()
            return [i.entry.id for i in selr2.items], ch.style_shadow
    ids_after, shadow_raw = _run(_select_and_split())

    # 冲突率=0：量化条目不进块
    assert quant_id not in ids_after
    # 影子行落位（知识库来源）
    shadow = json.loads(shadow_raw or "{}")
    rows = shadow.get("rows", {})
    assert "syntax" in rows and rows["syntax"].get("source") == "kb"

    # 跨 run 泄漏=0：清路径跑一遍（模拟停用/零命中）→「知识库·」行归零
    async def _clear():
        async with async_session() as db:
            ch_id = (await db.execute(
                sel(_Chapter.id).where(_Chapter.project_id == novel_id)
            )).scalar_one()
            await _clear_kb_shadow_rows(db, ch_id)
            await db.commit()
            ch = await db.get(_Chapter, ch_id)
            return json.loads(ch.style_shadow or "{}")
    after_clear = _run(_clear())
    assert not [k for k, v in after_clear.get("rows", {}).items()
                if str(v.get("reason") or "").startswith("知识库·")]
