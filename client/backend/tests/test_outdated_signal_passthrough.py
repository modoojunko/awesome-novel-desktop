"""s-auth-outdated-signal C端 透传——specs 场景「旧 C端 不误清凭据」的 C端 侧对应
＋新 C端 code=3 透传断言。"""

import pytest


@pytest.mark.asyncio
async def test_check_auth_code3_passthrough(monkeypatch):
    """S端 check-auth 返回 code=3 → C端 browser_auth(silent) 透传 client_outdated 载荷，
    不清 config 凭据。"""
    import auth_local.service as svc

    async def fake_call(path, **kw):
        return {
            "code": 3,
            "msg": "需要更新后重试",
            "data": {
                "client_outdated": True,
                "latest_version": "0.25",
                "download_url": "https://example.com/dl",
            },
        }

    monkeypatch.setattr(svc, "call_server_api", fake_call)
    cfg_snapshot = {"pc_hash": "pc-x", "token": "tok-old", "username": "u", "tier": "pro"}

    class FakeCfg(dict):
        pass

    fake = FakeCfg(cfg_snapshot)
    monkeypatch.setattr(svc, "load_or_create_config", lambda: fake)
    saved = {}
    monkeypatch.setattr(svc, "save_local_config", lambda c: saved.update(c))

    result = await svc.browser_auth(silent=True)

    assert result["code"] == 3
    assert result["data"]["client_outdated"] is True
    assert result["data"]["latest_version"] == "0.25"
    assert result["data"]["download_url"] == "https://example.com/dl"
    # 凭据未被清除（对比 code=1 分支的清凭据行为）
    assert fake["token"] == "tok-old"
    assert not saved, "code=3 不写回 config"
