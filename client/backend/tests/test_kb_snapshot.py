"""启用库落设定测试（c-kb-snapshot 批3）：互斥/快照取基线/落设定保留手改/同步差异/解绑。"""

import asyncio
import json
import uuid

from db import async_session
from models.kb import KbEntry, KbLibrary
from models.project import Novel
from models.user import User


def _run(coro):
    return asyncio.run(coro)


def _entry(user_id: str, genre: str, concept: str, payload: dict, when: dict | None = None) -> KbEntry:
    return KbEntry(
        user_id=user_id,
        genre=genre,
        concept=concept,
        concept_id=f"{genre}:{concept}",
        title="t",
        payload_json=json.dumps(payload, ensure_ascii=False),
        instruction="x。",
        when_json=json.dumps(when or {}, ensure_ascii=False),
        src_kind="manual",
    )


async def _seed() -> dict:
    uid = f"kbsnap-{uuid.uuid4().hex[:8]}"
    slug = f"kbsnap-{uuid.uuid4().hex[:8]}"
    async with async_session() as db:
        db.add(User(
            id=uid, email=f"{uid}@t.local", password_hash="x", display_name="快照测试",
            api_key="", api_base_url="", api_model="",
        ))
        novel = Novel(
            user_id=uid, name="快照测试书", slug=slug, root_path=f"./data/{slug}",
            source="manual", current_phase="write",
        )
        db.add(novel)
        await db.flush()
        # 仙侠/修真 文风库（2 基线 1 场景）＋ 世界库（2 基线）＋ 第二文风库（互斥用）
        lib_style = KbLibrary(user_id=uid, genre="仙侠/修真", concept="文风", name="文风库", contract="snapshot", rule_kind="auto")
        # 同格第二库只能走手动圈选（auto 库 (user,genre,concept) 唯一索引天然互斥）
        lib_style2 = KbLibrary(user_id=uid, genre="仙侠/修真", concept="文风", name="文风库B", contract="snapshot", rule_kind="manual")
        lib_craft = KbLibrary(user_id=uid, genre="仙侠/修真", concept="文笔", name="文笔库", contract="snapshot", rule_kind="auto")
        lib_world = KbLibrary(user_id=uid, genre="仙侠/修真", concept="世界设定", name="世界库", contract="snapshot", rule_kind="auto")
        db.add_all([lib_style, lib_style2, lib_craft, lib_world])
        await db.flush()
        entries = [
            # 文风基线：role ＋ sample
            _entry(uid, "仙侠/修真", "文风", {"slot": "role", "role": "冷峻克制的旁白"}),
            _entry(uid, "仙侠/修真", "文风", {"slot": "sample", "sample": "他收剑入鞘，半晌无言。"}),
            # 文风场景条目（不进快照）
            _entry(uid, "仙侠/修真", "文风", {"slot": "tone", "text": "打斗要短促"}, {"scene": "打斗"}),
            # 文笔基线：rule ＋ banned_word
            _entry(uid, "仙侠/修真", "文笔", {"slot": "rule", "rule": "一句不超过22字"}),
            _entry(uid, "仙侠/修真", "文笔", {"slot": "banned_word", "banned": "不禁"}),
            # 世界基线：stage ＋ constraint ＋ faction
            _entry(uid, "仙侠/修真", "世界设定", {"part": "stage", "content": "灵气枯竭的南崖大陆"}),
            _entry(uid, "仙侠/修真", "世界设定", {"part": "constraint", "content": "断剑之誓：剑断裂者不得再战"}),
            _entry(uid, "仙侠/修真", "世界设定", {"part": "factions", "content": "青冥剑宗"}),
        ]
        for e in entries:
            db.add(e)
        await db.commit()
        return {
            "uid": uid, "novel_id": novel.id, "root_path": novel.root_path,
            "lib_style": lib_style.id, "lib_style2": lib_style2.id,
            "lib_craft": lib_craft.id, "lib_world": lib_world.id,
            "entry_ids": [e.id for e in entries],
        }


def test_启用落设定_全链路(tmp_path):
    seed = _run(_seed())

    async def _go():
        async with async_session() as db:
            from kb.snapshot import bind_library

            binding, info, error = await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_style"],
            )
            return binding, info, error

    binding, info, error = _run(_go())
    assert error == ""
    # 快照只取基线：role+sample 两条；场景 tone 不进
    assert info["member_count"] == 2
    assert info["replaced_bindings"] == 0
    targets = {m["target"] for m in json.loads(binding.snapshot_json)["members"]}
    assert targets == {"role", "style_samples"}

    # 落设定：style KV 出现 role 与 style_samples；场景 tone 不落
    from filesystem.storage import get_storage
    from settings.style_model import normalize_style

    style_raw = _run(get_storage().read_yaml(seed["root_path"], "settings/writing-style.yaml")) or {}
    style = normalize_style(style_raw)
    assert style["role"] == "冷峻克制的旁白"
    assert "他收剑入鞘，半晌无言。" in style["style_samples"]
    assert "打斗要短促" not in json.dumps(style_raw, ensure_ascii=False)


def test_文笔与世界落设定(tmp_path):
    seed = _run(_seed())

    async def _go():
        async with async_session() as db:
            from kb.snapshot import bind_library

            _, info_c, err_c = await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_craft"],
            )
            _, info_w, err_w = await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_world"],
            )
            return info_c, err_c, info_w, err_w

    info_c, err_c, info_w, error = _run(_go())
    assert err_c == ""
    assert error == ""
    assert info_c["member_count"] == 2  # rule + banned_word
    assert info_w["member_count"] == 3  # stage+constraint+factions

    from filesystem.storage import get_storage
    from settings.style_model import normalize_style
    from settings.world_model import normalize_world

    style_raw = _run(get_storage().read_yaml(seed["root_path"], "settings/writing-style.yaml")) or {}
    style = normalize_style(style_raw)
    assert "一句不超过22字" in style["rules"]
    assert "不禁" in style["banned_words"]

    world_raw = _run(get_storage().read_yaml(seed["root_path"], "settings/world-setting.yaml")) or {}
    world = normalize_world(world_raw)
    assert "灵气枯竭的南崖大陆" in world["stage"]
    assert any("断剑之誓" in str(x.get("value") or "") for x in world["constraints"])
    assert any(f.get("name") == "青冥剑宗" for f in world["factions"])


def test_同格互斥_后启用替换前绑定():
    seed = _run(_seed())

    async def _go():
        async with async_session() as db:
            from kb.snapshot import bind_library, list_bindings

            await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_style"],
            )
            _, info2, err2 = await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_style2"],
            )
            rows = await list_bindings(db, novel_id=seed["novel_id"])
            return info2, err2, rows

    info2, err2, rows = _run(_go())
    assert err2 == ""
    assert info2["replaced_bindings"] == 1  # 文风库B 替换文风库
    enabled = [r for r in rows if r["enabled"]]
    assert len(enabled) == 1
    assert enabled[0]["library_id"] == seed["lib_style2"]


def test_本书改过保留_role不覆盖_列表追加去重():
    seed = _run(_seed())

    async def _preset():
        from filesystem.storage import get_storage
        from settings.style_model import put_style

        await get_storage().write_yaml(
            seed["root_path"], "settings/writing-style.yaml",
            put_style({}, {"role": "作家自己的声音", "rules": ["作家自己的规则"], "style_samples": ["他收剑入鞘，半晌无言。"]}),
        )

    _run(_preset())

    async def _go():
        async with async_session() as db:
            from kb.snapshot import bind_library

            _, info_s, err_s = await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_style"],
            )
            _, info_c, err_c = await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_craft"],
            )
            return info_s, info_c, err_s, err_c

    info_s, info_c, err_s, err_c = _run(_go())
    assert err_s == "" and err_c == ""
    # 文风库：role 被本书手改保留不落；示范段已存在去重零追加
    assert "style.role" not in info_s["landed"]
    assert "style.style_samples" not in info_s["landed"]
    # 文笔库：规则追加一条；禁用词追加一条
    assert info_c["landed"]["style.rules"] == 1
    assert info_c["landed"]["style.banned_words"] == 1

    from filesystem.storage import get_storage
    from settings.style_model import normalize_style

    style = normalize_style(_run(get_storage().read_yaml(seed["root_path"], "settings/writing-style.yaml")) or {})
    assert style["role"] == "作家自己的声音"
    assert style["rules"] == ["作家自己的规则", "一句不超过22字"]


def test_同步差异_库进新书显式同步收口():
    seed = _run(_seed())

    async def _go():
        async with async_session() as db:
            from kb.snapshot import bind_library, binding_status, sync_binding

            binding, _, error = await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_world"],
            )
            st0 = await binding_status(db, binding)
            # 库里新增一条基线 → 有更新
            db.add(_entry(seed["uid"], "仙侠/修真", "世界设定", {"part": "cost", "content": "施法一次折寿一年"}))
            await db.commit()
            st1 = await binding_status(db, binding)
            # 显式同步收口
            result = await sync_binding(db, binding, seed["root_path"])
            st2 = await binding_status(db, binding)
            return st0, st1, st2, result, error

    st0, st1, st2, result, error = _run(_go())
    assert error == ""
    assert st0["added"] == 0 and st0["removed"] == 0
    assert st1["added"] == 1
    assert result["member_count"] == 4
    assert st2["added"] == 0

    from filesystem.storage import get_storage
    from settings.world_model import normalize_world

    world = normalize_world(_run(get_storage().read_yaml(seed["root_path"], "settings/world-setting.yaml")) or {})
    assert "施法一次折寿一年" in world["cost"]


def test_解绑_设定保留():
    seed = _run(_seed())

    async def _go():
        async with async_session() as db:
            from kb.snapshot import bind_library, list_bindings, unbind

            binding, _, _ = await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id=seed["lib_style"],
            )
            bid = binding.id
            removed = await unbind(db, novel_id=seed["novel_id"], binding_id=bid)
            rows = await list_bindings(db, novel_id=seed["novel_id"])
            return removed, rows

    removed, rows = _run(_go())
    assert removed is True
    assert rows == []

    from filesystem.storage import get_storage
    from settings.style_model import normalize_style

    style = normalize_style(_run(get_storage().read_yaml(seed["root_path"], "settings/writing-style.yaml")) or {})
    assert style["role"] == "冷峻克制的旁白"  # 设定保留


def test_库不存在_报错():
    seed = _run(_seed())

    async def _go():
        async with async_session() as db:
            from kb.snapshot import bind_library

            return await bind_library(
                db, user_id=seed["uid"], novel_id=seed["novel_id"],
                root_path=seed["root_path"], library_id="no-such-lib",
            )

    binding, _info, error = _run(_go())
    assert binding is None
    assert error == "库不存在"


# ─── HTTP 面（鉴权/路由/信封）─────────────────────────────


def test_绑定端点_全链路():
    from fastapi.testclient import TestClient

    from auth_local.middleware import get_current_user
    from main import app

    seed = _run(_seed())
    app.dependency_overrides[get_current_user] = lambda: {"id": seed["uid"]}
    try:
        with TestClient(app) as c:
            # 绑定文风库
            r = c.post(
                "/api/kb/bindings",
                json={"novel_id": seed["novel_id"], "library_id": seed["lib_style"]},
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["data"]["member_count"] == 2
            binding_id = body["data"]["binding_id"]

            # 列表：来源行＋差异零
            r = c.get(f"/api/kb/bindings?novel_id={seed['novel_id']}")
            rows = r.json()["data"]
            assert len(rows) == 1
            assert rows[0]["library_name"] == "文风库"
            assert rows[0]["added"] == 0 and rows[0]["library_missing"] is False

            # 同步
            r = c.post(f"/api/kb/bindings/{binding_id}/sync")
            assert r.status_code == 200
            assert r.json()["data"]["member_count"] == 2

            # 解绑
            r = c.delete(f"/api/kb/bindings/{binding_id}?novel_id={seed['novel_id']}")
            assert r.status_code == 200
            r = c.get(f"/api/kb/bindings?novel_id={seed['novel_id']}")
            assert r.json()["data"] == []

            # 别人的 novel 404
            r = c.post(
                "/api/kb/bindings",
                json={"novel_id": "no-such-novel", "library_id": seed["lib_style"]},
            )
            assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()
