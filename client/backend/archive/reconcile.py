"""归档收尾提案服务（archive-reconcile）。

归档即刻生效后，AI 在后台完成收尾（设定变化提取/关系建议/伏笔登记/lore 建议/
角色状态变化），产出一律先落 chapter_reconcile 待确认行；作者逐条采纳才经
目标对象自身服务写回。未确认提案不在目标对象上 → 天然不进后续章节的提示词。

设计要点（design.md D1-D3）：
- 提案行不复存对象数据（payload 只存待确认差异＋证据句）；采纳走对象自身服务。
- 同章同键未决行覆盖（防堆积）；已决行保留留痕。
- 后台单飞线程（每章一把锁）：照抄 backup/export._job 模式；asyncio.run 包异步主体。
- 收尾 AI 全归 PRO：免费档/模型未就绪 → 不产生提案行（归档本身不受影响）。
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import UTC, datetime

from sqlalchemy import select

from db import async_session
from models.chapter import Chapter
from models.hook import NovelHook
from models.project import Novel
from models.reconcile import ChapterReconcile

# 收尾类别 → 展示名（工作台「操作」页签用）
# c-chapter-dossier：set_changes/relations/char_states 三类迁章档页签，收尾通道
# 只剩伏笔登记与世界要素两类（采纳写回书级）；四域提取见 archive/dossier.py。
KINDS: dict[str, str] = {
    "hooks": "伏笔登记",
    "lore": "世界要素",
}

# c-lore-reconcile-guardrails：lore 势力聚焦软上限——提案层「先立两三个」口径
# （与势力格引导语同源）；不复用 FACTIONS_MAX=6（存储满员语义，用 6 做阈值
# 挡不住「3 真＋3 假占满」）
LORE_FACTION_SOFT_CAP = 3

# 单批候选上限：lore 一批覆盖四格取 4（hooks 每类 ≤3）；超限按模型给出顺序截断
LORE_BATCH_MAX = 4

# pending 提案名目注入上限（跨章排重源只列名目，防 prompt 膨胀）
PENDING_NAMES_MAX = 20


def _norm(s: str) -> str:
    """归一化名目（伏笔 planted 查重同口径 #589，c-lore-reconcile-guardrails 共用）：

    小写化＋仅保留字母数字与汉字；不做全角折叠（isalnum 对全角为真，原样保留）。
    """
    return "".join(
        ch for ch in s.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff"
    )

_job_lock = threading.Lock()
_job: dict | None = None  # 全局单飞：同一时刻只跑一章收尾（与提取的每章键控单飞不同）


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _load_pending(session, chapter_id: str, kind: str):
    """同章同键未决行（覆盖用）。"""
    return (
        await session.scalars(
            select(ChapterReconcile).where(
                ChapterReconcile.chapter_id == chapter_id,
                ChapterReconcile.kind == kind,
                ChapterReconcile.status == "pending",
            )
        )
    ).all()


async def _upsert_pending(session, chapter_id: str, novel_id: str, kind: str, payload: dict) -> str:
    """同章同键未决行覆盖；无未决则新建。返回行 id。"""
    pending = await _load_pending(session, chapter_id, kind)
    if pending:
        row = pending[0]
        for extra in pending[1:]:
            extra.status = "rejected"  # 多余未决行并入驳回（防御性，正常不出现）
        row.payload = json.dumps(payload, ensure_ascii=False)
        row.error = ""
        session.add(row)
        return row.id
    row = ChapterReconcile(
        novel_id=novel_id,
        chapter_id=chapter_id,
        kind=kind,
        status="pending",
        payload=json.dumps(payload, ensure_ascii=False),
        # created_at 走列 server_default（DateTime 列；此前的 ISO 字符串会在
        # SQLite 直接 TypeError——收尾任务一落行即炸，本测试首跑撕出）
    )
    session.add(row)
    await session.flush()  # id 为 insert 期默认值：不 flush 返回 None
    return row.id


def start_reconcile_job(
    novel_id: str,
    root_path: str,
    chapter_ref: str,
    chapter_id: str,
    kinds: list[str] | None = None,
) -> dict | None:
    """单飞：同章已跑收尾返回 None（调用方忽略即可，进度区以行状态为准）。

    kinds：按类按需触发（工作台右栏 AI 辅助的三处入口）；None＝全量五类。
    """
    global _job
    key = f"{novel_id}:{chapter_ref}"
    with _job_lock:
        if _job and _job.get("state") == "running":
            return None
        _job = {"state": "running", "key": key, "started": _now_iso(), "kinds": kinds}
    t = threading.Thread(
        target=_run_thread,
        args=(novel_id, root_path, chapter_ref, chapter_id, kinds),
        daemon=True,
    )
    t.start()
    return {"state": "running", "key": key}


def _run_thread(
    novel_id: str, root_path: str, chapter_ref: str, chapter_id: str,
    kinds: list[str] | None = None,
) -> None:
    try:
        asyncio.run(_run_async(novel_id, root_path, chapter_ref, chapter_id, kinds))
    except Exception as e:  # noqa: BLE001,S110 — 收尾失败不影响归档；留痕供排查
        print(f"[reconcile] chapter {chapter_ref} 收尾失败：{e}")
    finally:
        global _job
        with _job_lock:
            _job = None


async def _run_async(
    novel_id: str, root_path: str, chapter_ref: str, chapter_id: str,
    kinds: list[str] | None = None,
) -> None:
    from ai_client import get_ai_client_for_novel
    from chapters.store import load_chapter

    # 模型未就绪：静默不产生提案（免费/未配置）
    try:
        client = await get_ai_client_for_novel(novel_id)
    except Exception:  # noqa: BLE001
        client = None
    if client is None:
        return

    chapter = await load_chapter(root_path, chapter_ref)
    full_text = chapter.get("prose", "")
    if not full_text.strip():
        return

    # ① 伏笔登记（埋下/收束＋证据句）→ kind=hooks
    # ② 世界要素建议 → kind=lore
    # （set_changes/relations/char_states 三类已迁章档，c-chapter-dossier）
    outline_chars = (chapter.get("outline") or {}).get("characters") or []
    cast = [str(n) for n in outline_chars if str(n).strip()]
    # lore 段带「现有世界设定」：只提与外面对不上的新要素（防重复提案）
    from filesystem.storage import get_storage
    from settings.world_model import world_summary_text

    world_raw = await get_storage().read_yaml(root_path, "settings/world-setting.yaml") or {}
    world_now = world_summary_text(world_raw, None).strip()

    # 角色名册（真机实锤 09-28：邵青梧/阿蓟等已登记角色的背景被当「新世界要素」
    # 提案——lore 只带世界设定排重、没带名册，模型无从知道谁是已登记角色）
    roster = ""
    try:
        from db import async_session as _as
        from models.project import Novel as _Novel

        async with _as() as _db:
            _proj = await _db.get(_Novel, novel_id)
            if _proj is not None:
                from settings.name_registry import known_names, roster_text

                roster = roster_text(await known_names(_db, _proj))
    except Exception:  # noqa: BLE001 — 名册取不到：lore 退回无名册（不阻塞收尾）
        roster = ""

    # 伏笔对账块（c-hooks-advance-ledger）：带编号＋计划收束章注入——模型先对账
    # （兑现/推进既有条目，按编号引用）再判新埋；#589 的纯排重升级为对账制
    hooks_now = ""
    try:
        from db import async_session as _as

        async with _as() as _db:
            _hooks = (
                await _db.scalars(
                    select(NovelHook).where(
                        NovelHook.novel_id == novel_id,
                        NovelHook.status == "active",
                    )
                )
            ).all()
            # 计划收束章号一次取回（章已删 SET NULL → 该行不带计划标注）
            _ch_ids = {h.planned_chapter_id for h in _hooks if h.planned_chapter_id}
            _planned: dict[str, int] = {}
            if _ch_ids:
                from models.chapter import Chapter as _Chapter

                _ch_rows = (
                    await _db.scalars(select(_Chapter).where(_Chapter.id.in_(_ch_ids)))
                ).all()
                _planned = {c.id: c.chapter for c in _ch_rows}
            lines = []
            for h in _hooks[:40]:
                desc = (h.description or "").strip()
                if not desc:
                    continue
                plan = _planned.get(h.planned_chapter_id or "")
                lines.append(
                    f"- #H-{h.seq:04d} {desc}"
                    + (f"（计划收束：第 {plan} 章）" if plan else "")
                )
            if lines:
                hooks_now = (
                    "本书已有伏笔台账（先对账：判断本章是否兑现或推进了其中条目，"
                    "resolved/advanced 按编号引用；相同或高度相似的不要重复登记为新埋）：\n"
                    + "\n".join(lines)
                )
    except Exception:  # noqa: BLE001 — 台账取不到：hooks 退回无对账块（不阻塞收尾）
        hooks_now = ""

    # ── c-lore-reconcile-guardrails：护栏注入与过滤素材 ──────────────────────
    # ① 现有势力名单（势力聚焦）：软上限计数只认有名目条目（v1 迁移可产无名行，
    #    无名行不计入也不放行）
    faction_names: list[str] = []
    faction_names_norm: list[str] = []
    faction_line = ""
    try:
        from settings.world_model import normalize_world as _nw

        for _f in (_nw(world_raw) or {}).get("factions") or []:
            if isinstance(_f, dict) and str(_f.get("name", "")).strip():
                _name = str(_f["name"]).strip()
                faction_names.append(_name)
                faction_names_norm.append(_norm(_name))
        if faction_names:
            faction_line = f"现有势力（{len(faction_names)} 个）：{'、'.join(faction_names)}"
    except Exception:  # noqa: BLE001 — 名单取不到：lore 退回无势力块（不阻塞收尾）
        faction_names = []
        faction_names_norm = []
        faction_line = ""

    # ② 本书其他章 pending lore 提案名目（跨章排重源）。排除本章：同章重复由
    #    _upsert_pending 覆盖语义兜住，注入含本章会自吞未决提案（旧名目被
    #    「不要重复提」压掉 → 新批省略 → 整行覆盖 → 未拍板提案静默蒸发）
    pending_line = ""
    try:
        async with async_session() as _db:
            _pend = (
                await _db.scalars(
                    select(ChapterReconcile).where(
                        ChapterReconcile.novel_id == novel_id,
                        ChapterReconcile.kind == "lore",
                        ChapterReconcile.status == "pending",
                        ChapterReconcile.chapter_id != chapter_id,
                    )
                )
            ).all()
            _names: list[str] = []
            for _r in _pend:
                try:
                    _data = json.loads(_r.payload or "{}")
                except ValueError:
                    continue
                _items = _data.get("items") if isinstance(_data, dict) else None
                for _it in _items or []:
                    if isinstance(_it, dict) and str(_it.get("key", "")).strip():
                        _names.append(str(_it["key"]).strip())
            _names = list(dict.fromkeys(_names))[:PENDING_NAMES_MAX]
            if _names:
                pending_line = "以下名目已有提案待作者确认，不要重复提：" + "、".join(_names)
    except Exception:  # noqa: BLE001 — pending 名目取不到：lore 退回无排重块（不阻塞收尾）
        pending_line = ""

    # ③ 出场人物归一化集合（提案侧人物过滤，两侧同口径）
    cast_norm = {_norm(n) for n in cast}

    for kind, prompt in _collect_prompts(
        chapter_ref, chapter, full_text, cast, world_now, roster, hooks_now,
        faction_line=faction_line, pending_line=pending_line,
    ):
        if kinds is not None and kind not in kinds:
            continue
        usage: dict = {}
        try:
            text = await client.chat(
                model="haiku", system="", messages=[{"role": "user", "content": prompt}],
                # 1600＝四域提取同预算：600 下 planted/resolved 各几条带证据句
                # 必截断（真机实锤：断在半句 evidence → JSON 断裂 → parse 失败）
                max_tokens=1600, usage=usage,
                operation=f"reconcile_{kind}",
            )
            await _record(novel_id, kind, usage)
            data = _parse_json_lenient(text, allow_bare_array=(kind == "lore"))
            if not data:
                # 返回了文字但不是 JSON：显式落失败行（可重试），不得静默蒸发；
                # 末尾无 "}"/"]" ＝大概率被输出预算截断（诊断提示直达原因；
                # 结尾带括号的完整短输出如 `[]` 不算截断——真机 09-29 误诊实锤）
                truncated = bool(text) and not text.rstrip().endswith(("}", "]"))
                hint = "；输出疑似被输出预算截断" if truncated else ""
                await _record_fail(novel_id, kind, usage)
                await _mark_failed(
                    novel_id, chapter_id, kind,
                    f"parse: 模型输出不是可解析的 JSON{hint}（{str(text)[:120]}）",
                )
                continue
        except Exception:  # noqa: BLE001 — 单类失败不拖垮其他收尾
            await _record_fail(novel_id, kind, usage)
            await _mark_failed(novel_id, chapter_id, kind, str(usage))
            continue
        if kind == "lore":
            # c-lore-reconcile-guardrails：提案侧护栏（截断/人物/势力聚焦），确定性执行
            _raw_items = data.get("items") if isinstance(data, dict) else None
            kept, trace = _filter_lore_items(
                _raw_items if isinstance(_raw_items, list) else [],
                cast_norm, faction_names_norm,
            )
            if trace["dropped"] or trace["truncated"]:
                print(f"[reconcile] chapter {chapter_ref} lore 护栏丢弃："
                      f"{json.dumps(trace, ensure_ascii=False)}")
            if not kept:
                # 整批过滤为空：不落行、不覆盖既有未决行（空行＝「待确认 1（无明细）」
                # 假信号）；本轮 AI 已成功（可解析），旧失败行照清防永久挂列表
                print(f"[reconcile] chapter {chapter_ref} lore 过滤后无候选，不落提案行")
                async with async_session() as session:
                    for old in (
                        await session.scalars(
                            select(ChapterReconcile).where(
                                ChapterReconcile.chapter_id == chapter_id,
                                ChapterReconcile.kind == kind,
                                ChapterReconcile.status == "failed",
                            )
                        )
                    ).all():
                        await session.delete(old)
                    await session.commit()
                continue
            data = {"items": kept, "guard": trace}
        async with async_session() as session:
            await _upsert_pending(session, chapter_id, novel_id, kind, data)
            # 重试/重跑成功：旧失败行使命已尽（新 pending 承接），清掉防永久挂列表
            for old in (
                await session.scalars(
                    select(ChapterReconcile).where(
                        ChapterReconcile.chapter_id == chapter_id,
                        ChapterReconcile.kind == kind,
                        ChapterReconcile.status == "failed",
                    )
                )
            ).all():
                await session.delete(old)
            await session.commit()


def _collect_prompts(
    chapter_ref: str, chapter: dict, full_text: str, cast: list[str],
    world_now: str = "", roster: str = "", hooks_now: str = "",
    faction_line: str = "", pending_line: str = "",
):
    """两类收尾的 prompt；正文全量给（章目标上限 6000，旧 [:3000] 会丢掉章末钩子）。

    lore 段（c-lore-reconcile-guardrails 护栏版）：恒定世界事实判据（正反成对＋
    可操作测试句）、势力聚焦（faction_line 名单＋「先立两三个」，已有 3 个及以上
    不再提新势力、禁改放 extra/history 变相提交）、名目不得是人名（value 可提及）、
    set 四格含 constraints（规则戒律类——三选项口径是「同一教规两格双落」成因）、
    排重源＝现有世界设定＋其他章待确认提案（pending_line 独立成块）、≤4 条宁缺勿滥、
    key/value 长度口径、evidence 接地、尾提醒防无 JSON 文字。
    锚点纪律：首句「识别新出现或变化的世界要素」＝e2e 桩路由子串＋pytest 断言
    双重依赖，逐字保留；禁复用 dossier 桩分支子串「只输出一个 JSON 对象，四键齐全」。
    hooks 段带「真伏笔判据＋条数上限＋现有台账」：剧情走向（进行中的冲突/行动/
    因果紧接的下一步）、章末悬念断点、氛围/场景/角色状态不登记（角色状态归章档
    认知域），每章 planted/resolved 各最多 3 条（真机实锤：
    无判据无上限时第 1 章提了 11 条），已有台账防重复归档反复入账。
    """
    body = full_text
    world_block = f"现有世界设定（与之重复的不要提）：\n{world_now}\n\n" if world_now else ""
    hooks_block = f"{hooks_now}\n\n" if hooks_now else ""
    yield "hooks", (
        f"判断第 {chapter_ref} 章对既有伏笔的兑现与推进，以及新埋了哪些伏笔。"
        f"先对账（台账见下）：resolved＝本章兑现收束的条目、advanced＝本章有实质揭示或"
        f"强化的条目（纯提及不算），都按编号 ref 引用并给证据；再判新埋：只登记作者有意"
        f"埋下、后文必须回收的「未解承诺」——读者此刻被明确引去期待一件尚未发生或尚未"
        f"揭示的事（谜团、异常、警告、约定、来历不明之物）；自检：这一条若后文永不回收，"
        f"读者会觉得被辜负，才算伏笔。剧情走向不是伏笔：正在发生的冲突、行动、事件本身，"
        f"以及因果紧接的下一步（去了哪里、和谁交手、下一步打算、危机怎么升级），再重要"
        f"也只是剧情推进，不要登记；当场提出当场解答的疑点（问完即答≠伏笔）、只为吸引"
        f"读者看下一章的章末悬念断点、氛围描写、场景细节、角色的身体或状态变化，一律"
        f"不要登记（角色状态另有人物状态域负责）。"
        f"resolved、advanced、planted 各最多 3 条；本章没有新悬念时 planted 输出空数组，宁缺勿滥。"
        f'JSON 对象输出，形如 {{"resolved": [{{"ref": "#H-0003", "note": "怎么收的一句话", '
        f'"evidence": "原文一句话"}}], "advanced": [{{"ref": "#H-0001", "note": "推进说明", '
        f'"evidence": "…"}}], "planted": [{{"description": "信标坐标漂移", '
        f'"evidence": "…"}}]}}。\n\n{hooks_block}正文：\n{body}'
    )
    roster_block = (
        f"{roster}\n已登记角色（上表人物）的背景、身份、经历属于角色卡——不要作为世界要素提案。\n\n"
        if roster else ""
    )
    faction_block = f"{faction_line}。势力先立两三个即可；超过此数后不再提新势力。\n\n" if faction_line else ""
    pending_block = f"{pending_line}\n\n" if pending_line else ""
    yield "lore", (
        f"从第 {chapter_ref} 章正文识别新出现或变化的世界要素（地点/组织/历史/规则）。"
        f"只提「后续章节还会当既定设定引用的恒定世界事实」，用这条测试判断：把一条拿掉，"
        f"后文是否还会把它当既定设定引用。应提：长期有效的规则/条约/戒律（哪怕本章才立下）、"
        f"首次登场且后文还会用到的地点/组织/物种/制度、世界层面的恒定改变（势力兴亡、禁令生效）。"
        f"不应提：本章情节经过与拍点（谁做了什么、某场考验/冲突/仪式的经过）、人物状态与外貌、"
        f"一次性场景细节。「变化」只指世界层面恒定状态从此改变，不是主角推动的剧情转折。"
        f"名目（key）不得是人名（含未登记人物）；value 陈述事实时可以提及人物。"
        f"势力聚焦：势力先立两三个即可（现有势力名单见下）。已有 3 个及以上时不再提新势力，"
        f"本章势力相关的变化并进既有势力条目（key 直接用既有势力名）；除非新势力取代或吞并了"
        f"既有势力，否则整条不提，也不要把新势力改放 extra/history 变相提交。"
        f"排重：与现有世界设定或待确认提案重复的名目不要提；同一要素已存在于现有设定或提案时，"
        f"沿用其既有归属，不要改换 set。"
        f"只挑对后续最重要的，最多 4 条，宁缺勿滥；本章没有新世界要素则输出 {{\"items\": []}}，不要硬凑。"
        f"key ≤10 字，value 一句话 ≤60 字。"
        f"set 取 history（大事与旧账）/factions（势力）/constraints（世界铁律与戒律）/"
        f"extra（其余世界细节），规则戒律类用 constraints，拿不准用 extra。"
        f'JSON 对象输出，形如 {{"items": [{{"key": "静默带", "value": "无信号的深空航段", '
        f'"set": "extra", "evidence": "正文原句不超过 40 字"}}]}}。'
        f"\n\n{world_block}{faction_block}{pending_block}{roster_block}正文：\n{body}"
        f"\n（只输出上面的 JSON 对象，不要输出任何其他文字。）"
    )


def _parse_json_lenient(text: str, allow_bare_array: bool = False) -> dict | None:
    """模型输出宽松 JSON 解析：截取首个 { 到末个 }；失败返回 None。

    形状按首个 JSON 结构判定，且数组段**确能解析为 list** 才定形：
    lore 兜底包装 {"items": list}（旧提示词教过「没有则输出空数组」，真机
    09-29 实锤模型照字面回 `[]` 被误判失败）；hooks 合法裸数组＝契约违例
    维持解析失败（SHALL NOT 把数组首元素的内层 { 误当顶层对象）；数组段
    解析失败（前导杂文带 [、截断数组）→ 回退对象路径——对账输出常带
    [#H-xxxx] 前导台账引用（评审 #607：此处不得倒退成失败行）。
    """
    import json as _json

    if not text:
        return None
    o_start, o_end = text.find("{"), text.rfind("}")
    a_start, a_end = text.find("["), text.rfind("]")
    if a_start >= 0 and (o_start < 0 or a_start < o_start) and a_end > a_start:
        try:
            items = _json.loads(text[a_start : a_end + 1])
        except Exception:  # noqa: BLE001 — 杂文/截断非合法数组 → 对象回退
            items = None
        if isinstance(items, list):
            return {"items": items} if allow_bare_array else None
    if o_start >= 0 and o_end > o_start:
        try:
            data = _json.loads(text[o_start : o_end + 1])
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001
            return None
    return None


def _filter_lore_items(
    items: list, cast_norm: set[str], faction_names_norm: list[str],
) -> tuple[list[dict], dict]:
    """c-lore-reconcile-guardrails 提案侧护栏（确定性，不依赖模型自觉）。

    顺序＝先按模型给出顺序截前 LORE_BATCH_MAX 条，再逐条过滤：
    - 名目归一化命中出场角色名单 → 丢弃（人物归角色域；两侧同口径归一化，
      银铎案形状：cast 有名、名册无卡）
    - 势力计数 ≥ LORE_FACTION_SOFT_CAP 时 set=factions 的新名目 → 丢弃
      （命中既有势力放行；计数只认有名目条目，v1 迁移无名行不计入）
    返回 (kept, trace)：trace 记录丢弃名目与原因、截断名目（payload/日志留痕，
    不静默蒸发）。非法条目（非 dict/缺 key）直接丢，不进 trace——形状错误非内容问题。
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    head, overflow = items[:LORE_BATCH_MAX], items[LORE_BATCH_MAX:]
    for it in head:
        if not isinstance(it, dict) or not str(it.get("key", "")).strip():
            continue
        key = str(it["key"]).strip()
        nm = _norm(key)
        if nm and nm in cast_norm:
            dropped.append({"key": key, "reason": "cast"})
            continue
        if (
            str(it.get("set", "")).strip() == "factions"
            and len(faction_names_norm) >= LORE_FACTION_SOFT_CAP
            and nm not in faction_names_norm
        ):
            dropped.append({"key": key, "reason": "faction_cap"})
            continue
        kept.append(it)
    trace: dict = {
        "dropped": dropped,
        "truncated": [
            str(x.get("key", "")) if isinstance(x, dict) else "" for x in overflow
        ],
    }
    return kept, trace


async def _record(novel_id: str, kind: str, usage: dict) -> None:
    from archive.service import _record_ai_usage

    await _record_ai_usage(novel_id, f"reconcile_{kind}", usage)


async def _record_fail(novel_id: str, kind: str, usage: dict) -> None:
    from archive.service import _record_ai_usage

    await _record_ai_usage(novel_id, f"reconcile_{kind}_fail", usage, force=True)


async def _mark_failed(novel_id: str, chapter_id: str, kind: str, message: str) -> None:
    async with async_session() as session:
        row = ChapterReconcile(
            novel_id=novel_id,
            chapter_id=chapter_id,
            kind=kind,
            status="failed",
            payload="{}",
            error=message[:500],
        )
        session.add(row)
        await session.commit()


async def apply_accept(db, row: ChapterReconcile) -> None:
    """采纳：经目标对象自身服务写回。任一步失败抛异常（行置 failed 保留 payload）。

    c-chapter-dossier 后只剩两类：lore → lore-apply 幂等合并；hooks → 伏笔服务。
    退役 kind（set_changes/relations/char_states）到达此处 → ValueError（上游
    run/retry 白名单已拦，历史已决行不会再被采纳）。
    """
    import json as _json

    payload = _json.loads(row.payload or "{}")

    if row.kind == "lore":
        # 世界要素建议 → lore-apply 幂等合并（origin=本章 ref）
        # c-lore-reconcile-guardrails：采纳侧复检＋归并（与提案侧护栏同构）
        from filesystem.storage import get_storage
        from settings.world_model import (
            lore_apply_entries,
            normalize_world,
            put_world_merged,
        )

        novel = await db.get(Novel, row.novel_id)
        ch = await db.get(Chapter, row.chapter_id)
        items = payload.get("items") or []
        from settings.world_model import SET_NAMES as _WORLD_SETS

        raw_entries = []
        for i in items:
            if not isinstance(i, dict) or not str(i.get("key", "")).strip():
                continue
            set_name = str(i.get("set", "")).strip()
            if set_name not in _WORLD_SETS:
                set_name = "extra"  # 归属缺失/非法 → 「更多世界细节」（可后补名目）
            raw_entries.append({
                "key": str(i.get("key", "")).strip(),
                "value": str(i.get("value", "")).strip(),
                "origin": ch.ref if ch else "",
                "set": set_name,
            })

        # ① 采纳侧人物复检（兜存量未决行与章纲漏填章的提案）：出场名单同款归一化
        cast_norm: set[str] = set()
        if ch is not None:
            cast_norm = {
                _norm(cc.character_name) for cc in ch.characters if cc.character_name
            }
        guard: dict = {"dropped_cast": []}
        checked = []
        for e in raw_entries:
            if cast_norm and _norm(e["key"]) in cast_norm:
                guard["dropped_cast"].append(e["key"])
                continue
            checked.append(e)

        # ② 批内同名目去重（保留首条）：归并匹配采纳时刻既有集，批内同名目 set 各异
        #    会双双无既有命中、双双落新格（停战条款案批内变体）
        deduped = []
        seen: set[str] = set()
        for e in checked:
            nm = _norm(e["key"])
            if nm and nm in seen:
                continue
            if nm:
                seen.add(nm)
            deduped.append(e)

        # ③ 归一化归并：命中 history/extra/factions 既有条目 → 用既有条目**字面**
        #    key/origin/set 改写为更新（幂等命中靠字面精确相等，用提案 key 重写会
        #    dup 查不中复活双落）；constraints 不进归并目标（作者手写铁律不被 AI
        #    value 覆盖；其新提案由 lore_apply_entries 按 key 幂等原地更新，不冲突）
        if deduped:
            from filesystem.paths import KEY_TO_PATH as _K2P

            # 路径唯一来源（filesystem.paths.KEY_TO_PATH）：硬编码 settings/world.yaml
            # 会写进一个全仓没人读的野文件（本测试撕出）
            raw = await get_storage().read_yaml(novel.root_path, _K2P["world"]) or {}
            v2 = normalize_world(raw)
            merge_index: dict[str, tuple[str, dict]] = {}
            for set_name in ("history", "extra", "factions"):
                for ent in v2.get(set_name) or []:
                    if not isinstance(ent, dict):
                        continue
                    _name = ent.get("name", "") if set_name == "factions" else ent.get("key", "")
                    _nm = _norm(str(_name))
                    if _nm and _nm not in merge_index:
                        merge_index[_nm] = (set_name, ent)
            entries = []
            guard["merged_into"] = []
            for e in deduped:
                nm = _norm(e["key"])
                hit = merge_index.get(nm) if nm else None
                if hit is None:
                    entries.append(e)
                    continue
                set_name, ent = hit
                if set_name == "factions":
                    entries.append({
                        "key": str(ent.get("name", "")),
                        "value": e["value"],
                        "origin": e["origin"],
                        "set": "factions",
                    })
                else:
                    entries.append({
                        "key": str(ent.get("key", "")),
                        "value": e["value"],
                        "origin": str(ent.get("origin") or ""),
                        "set": set_name,
                    })
                guard["merged_into"].append({
                    "key": e["key"],
                    "into": str(ent.get("name") or ent.get("key", "")),
                    "set": set_name,
                })
            v2 = lore_apply_entries(v2, entries)
            merged = put_world_merged(raw, v2)
            await get_storage().write_yaml(novel.root_path, _K2P["world"], merged)

        # 护栏留痕进 payload（审计可测、前端零改动——对账区只读 items 渲染）
        if guard.get("dropped_cast") or guard.get("merged_into"):
            payload["guard"] = guard
            row.payload = json.dumps(payload, ensure_ascii=False)

    elif row.kind == "hooks":
        # 伏笔登记（c-hooks-advance-ledger 对账制）：
        #   resolved → 按编号 ref 精确命中台账行 → patch resolved＋收束章＋payoff_note
        #   advanced → 按编号 ref 命中 → mentioned_chapter_id 回填本章（最近推进留痕，
        #              状态不动——models/hook.py 注释预留的「归档 UI 归写作期」口子）
        #   planted  → 建新条（归一化查重，#589）
        # ref 解析失败/行不存在 → 跳过该条目（模型幻觉编号不毁整批）；
        # 旧格式（resolved 无 ref 有 description，存量 pending 行）→ 兼容按描述包含匹配。
        from settings.hooks_service import create_hook, patch_hook

        # _norm 已提为模块级（c-lore-reconcile-guardrails 与 lore 归并共用，行为不变）

        def _seq_of(ref: str) -> int | None:
            import re as _re

            m = _re.fullmatch(r"#?H-?0*(\d{1,6})", str(ref or "").strip())
            return int(m.group(1)) if m else None

        existing = {
            _norm(h.description or "")
            for h in (
                await db.scalars(select(NovelHook).where(NovelHook.novel_id == row.novel_id))
            ).all()
        }

        for item in payload.get("resolved") or []:
            if not isinstance(item, dict):
                continue
            seq = _seq_of(item.get("ref"))
            note = str(item.get("note", "")).strip()[:300]
            target = None
            if seq is not None:
                target = await db.scalar(
                    select(NovelHook).where(
                        NovelHook.novel_id == row.novel_id, NovelHook.seq == seq
                    )
                )
            elif item.get("description"):
                desc = str(item["description"]).strip()[:300]
                hooks = (
                    await db.scalars(
                        select(NovelHook).where(
                            NovelHook.novel_id == row.novel_id,
                            NovelHook.status == "active",
                        )
                    )
                ).all()
                target = next(
                    (h for h in hooks if desc and desc in (h.description or "")), None
                )
            if target is None:
                continue  # 幻觉编号/行不存在：跳过，不中断整批
            fields: dict = {"status": "resolved", "resolved_chapter_id": row.chapter_id}
            if note:
                fields["payoff_note"] = note
            await patch_hook(db, row.novel_id, target.id, fields)

        for item in payload.get("advanced") or []:
            if not isinstance(item, dict):
                continue
            seq = _seq_of(item.get("ref"))
            if seq is None:
                continue
            target = await db.scalar(
                select(NovelHook).where(
                    NovelHook.novel_id == row.novel_id, NovelHook.seq == seq
                )
            )
            if target is None or target.status != "active":
                continue
            target.mentioned_chapter_id = row.chapter_id

        for item in payload.get("planted") or []:
            desc = str(item.get("description", "")).strip()[:300]
            key = _norm(desc)
            if not desc or not key or key in existing:
                continue
            existing.add(key)
            await create_hook(db, row.novel_id, {
                "description": desc,
                "type": "mystery",
                "priority": 2,
                "status": "active",
                # 服务契约：章引用列只认章 id（ref 字符串会被白名单拒绝）
                "introduced_chapter_id": row.chapter_id,
            })

    else:
        raise ValueError(f"未知的收尾类别：{row.kind}")

    row.status = "accepted"
    row.decided_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(row)


async def migrate_legacy_pending() -> dict:
    """存量退役 kind 的 pending 行一次性迁移（c-chapter-dossier，启动幂等）。

    - set_changes/relations pending → 物化成对应章档子表 pending 行
      （与既有章档行合并后整批重建；无证据句置空）；
    - char_states pending → 置 rejected（数据生成时已直写 state_change，非提案语义）；
    - 已迁移的 pending 行删除（chapter_reconcile 是运行态待办、不进备份，
      历史已决行原地留痕不搬）。
    """
    import json as _json

    from chapters.store import _apply_dossier
    from models.chapter import Chapter

    migrated = 0
    rejected = 0
    async with async_session() as session:
        rows = (
            await session.scalars(
                select(ChapterReconcile).where(
                    ChapterReconcile.status == "pending",
                    ChapterReconcile.kind.in_(("set_changes", "relations", "char_states")),
                )
            )
        ).all()
        by_chapter: dict[str, list[ChapterReconcile]] = {}
        for r in rows:
            by_chapter.setdefault(r.chapter_id, []).append(r)
        for chapter_id, group in by_chapter.items():
            chapter = await session.get(Chapter, chapter_id)
            if chapter is None:
                continue
            # 现有章档行并入 payload（_apply_dossier 是整批替换语义）
            payload = {
                "settings": [
                    {"area": s.area, "content": s.content, "evidence": s.evidence,
                     "status": s.status, "flags": s.flags}
                    for s in chapter.dossier_settings
                ],
                "relations": [
                    {"owner": r_.owner_name, "other": r_.other_name,
                     "rel_type": r_.rel_type, "change_note": r_.change_note,
                     "evidence": r_.evidence, "status": r_.status, "flags": r_.flags}
                    for r_ in chapter.dossier_relations
                ],
                "items": [], "knowledge": [],
            }
            touched = False
            for rec in group:
                if rec.kind == "char_states":
                    rec.status = "rejected"
                    rec.decided_at = datetime.now(UTC).replace(tzinfo=None)
                    rejected += 1
                    continue
                try:
                    data = _json.loads(rec.payload or "{}")
                except ValueError:
                    data = {}
                items = data.get("items") if isinstance(data, dict) else None
                if rec.kind == "set_changes":
                    for i in items or []:
                        if isinstance(i, dict) and str(i.get("value", "")).strip():
                            payload["settings"].append({
                                "area": str(i.get("set", "extra"))[:50],
                                "content": str(i.get("key", "") + "：" + i.get("value", ""))[:300],
                                "evidence": "", "status": "pending", "flags": "",
                            })
                            migrated += 1
                            touched = True
                elif rec.kind == "relations":
                    for i in items or []:
                        if isinstance(i, dict) and str(i.get("owner", "")).strip() \
                                and str(i.get("other", "")).strip():
                            payload["relations"].append({
                                "owner": str(i.get("owner", ""))[:50],
                                "other": str(i.get("other", ""))[:50],
                                "rel_type": str(i.get("rel_type", ""))[:50],
                                "change_note": str(i.get("stance", "") or i.get("note", ""))[:300],
                                "evidence": "", "status": "pending", "flags": "",
                            })
                            migrated += 1
                            touched = True
                # 已物化/已驳回的原 pending 行删除（char_states 除外——置 rejected 留痕）
                await session.delete(rec)
            if touched:
                for attr in ("dossier_settings", "dossier_relations",
                             "dossier_items", "dossier_knowledge"):
                    getattr(chapter, attr).clear()
                await session.flush()
                _apply_dossier(chapter, payload, {})
        await session.commit()
    return {"migrated": migrated, "char_states_rejected": rejected}
