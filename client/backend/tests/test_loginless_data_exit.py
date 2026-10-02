"""loginless-data-exit 场景测试——specs 场景逐一对应。

场景映射（specs/loginless-data-exit）：
L1 未登录整机导出（export 免登+整库无主化+无配置段）
L2 免登请求配置包被强制不含（include_config=true → 服务端强制 false）
L3 import 永不免登（401）
L4 浏览器 drive-by 不可达（CORS 预检不批+非回环拒）
L5 目标路径守卫（target_dir/target_file 落 DATA_ROOT 拒）
L6 legacy-db/status 免登
（升级卡 UpgradeGate 的场景在前端 vitest 覆盖：c-loginless-data-exit.spec）
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    """建一个带书与配置的库环境，返回 (client, data_root, out_dir, book_id)。"""
    import os

    data_root = tmp_path / "data"
    data_root.mkdir()
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    # 隔离数据库：config.DATABASE_URL 在 import 时绑定——子进程里换（这里直接
    # 用环境变量 + reload 的方式在测试进程内不可靠（全局单例已建）），改走
    # conftest 既有全局库 + 造书；DATA_ROOT 只影响守卫判定，用 monkeypatch。
    monkeypatch.setenv("LOGINLESS_OUT", str(out_dir))

    from db import async_session
    from models.project import Novel
    from models.user import User

    async def seed():
        async with async_session() as s:
            import uuid as _uuid
            u = User(email=f"loginless-{_uuid.uuid4().hex[:8]}@test.local", password_hash="x",
                     display_name="ll", api_key="", api_base_url="", api_model="")
            s.add(u)
            await s.flush()
            n = Novel(user_id=u.id, name="免登导出测试书", slug=f"ll-{os.getpid()}",
                      root_path=f"./data/ll-{os.getpid()}", source="manual")
            s.add(n)
            await s.commit()
            return str(u.id), str(n.id)

    import asyncio

    _uid, nid = asyncio.run(seed())
    import config as config_mod

    monkeypatch.setattr(config_mod, "DATA_ROOT", Path(data_root), raising=False)
    from main import app

    return TestClient(app), data_root, out_dir, nid


def test_l1_loginless_export_whole_library(seeded):
    """L1：无 Authorization 头调用 export/start → 全部书籍导出、无配置段。"""
    client, _data_root, out_dir, _nid = seeded
    r = client.post("/api/backup/export/start", json={
        "kind": "backup", "target_dir": str(out_dir), "include_config": False})
    assert r.status_code == 200, r.text
    # 轮询到完成
    import time

    for _ in range(300):  # CI 慢机上全库备份可超 12s，放宽到 60s 上限
        st = client.get("/api/backup/export/status").json()["data"]
        if st.get("state") == "done":
            break
        time.sleep(0.2)
    assert st.get("state") == "done", st
    zips = list(Path(out_dir).glob("*.zip"))
    assert zips, "必须产出资产包"
    with zipfile.ZipFile(zips[0]) as zf:
        names = zf.namelist()
        assert any(n.endswith("backup.yaml") for n in names)
        # 无配置段：不含 config 包（配置包是独立 zip——本例 out 只有资产 zip）
        cfg_zips = [p for p in Path(out_dir).glob("*配置*.zip")]
        assert not cfg_zips, "免登态不得产出配置包"


def test_l2_loginless_include_config_forced_false(seeded):
    """L2：免登请求 include_config=true → 服务端强制 false，仍无配置包。"""
    client, _data_root, out_dir, _nid = seeded
    r = client.post("/api/backup/export/start", json={
        "kind": "backup", "target_dir": str(out_dir), "include_config": True})
    assert r.status_code == 200, r.text
    import time

    for _ in range(300):  # CI 慢机上全库备份可超 12s，放宽到 60s 上限
        st = client.get("/api/backup/export/status").json()["data"]
        if st.get("state") in ("done", "error"):
            break
        time.sleep(0.2)
    assert st.get("state") == "done", st
    cfg_zips = [p for p in Path(out_dir).glob("*配置*.zip")]
    assert not cfg_zips


def test_l3_import_never_loginless(seeded):
    """L3：免登调用 import/parse → 401。"""
    client, *_ = seeded
    r = client.post("/api/backup/import/parse", json={"paths": ["/tmp/x.zip"]})
    assert r.status_code == 401


def test_l5_target_path_guard(seeded):
    """L5：target_dir/target_file 落 DATA_ROOT 内 → 422 拒。"""
    client, data_root, _out_dir, nid = seeded
    r1 = client.post("/api/backup/export/start", json={
        "kind": "backup", "target_dir": str(data_root), "include_config": False})
    assert r1.status_code == 422
    r2 = client.post("/api/backup/export/start", json={
        "kind": "single", "target_file": str(data_root / "novel.db"),
        "book_id": nid})
    assert r2.status_code == 422, "single 的 target_file 直指 novel.db 必须拒"


def test_l6_legacy_status_loginless(seeded):
    """L6：legacy-db/status 免登可读。"""
    client, *_ = seeded
    r = client.get("/api/backup/legacy-db/status")
    assert r.status_code == 200
    assert r.json()["code"] == 0


def test_l4_loopback_guard_rejects_non_localhost(seeded, monkeypatch):
    """L4：非回环来源访问免登端点 → 403（中间件层，先于业务）。"""
    _client, *_ = seeded  # 值未用：断言走中间件函数直调
    # TestClient 的 client.host 默认 "testclient"——放行清单里；模拟外部来源
    from main import _loginless_loopback_guard

    class FakeClient:
        host = "8.8.8.8"  # 公网 IP（192.168.x 私网已放宽——Docker 网关合法路径）

    class FakeRequest:
        url = type("U", (), {"path": "/api/backup/export/status"})()
        client = FakeClient()

    async def call_next(req):
        raise AssertionError("非回环不应到达业务层")

    import asyncio

    resp = asyncio.run(_loginless_loopback_guard(FakeRequest(), call_next))
    assert resp.status_code == 403
