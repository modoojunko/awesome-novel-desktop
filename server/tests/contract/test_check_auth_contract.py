"""check-auth 契约对拍（s-contract-live-check）——S端 侧

响应形状与 docs/contracts/check-auth.example.json 单源对拍：
- 缺 pc_hash → {code:1, msg}
- 未知设备 → {code:1, ...} 等待授权
- code 闭集与 fixture codes 一致（0/1/2/3）
"""

import json
from pathlib import Path

import pytest

_FIXTURE = json.loads(
    (Path(__file__).parents[3] / "docs" / "contracts" / "check-auth.example.json").read_text()
)


def test_fixture_codes_closed_set():
    codes = set(_FIXTURE["codes"])
    assert codes == {"0", "1", "2", "3"}


def test_missing_pc_hash_shape(client):
    body = client.get("/api/check-auth").json()
    assert body["code"] == 1
    assert isinstance(body.get("msg"), str) and body["msg"]
    # 顶层键不越 fixture 清单
    assert set(body) <= set(_FIXTURE["top_level"])


def test_unknown_device_waits_for_authorize(client):
    body = client.get(
        "/api/check-auth", params={"pc_hash": f"live-probe-{id(object())}"}
    ).json()
    assert body["code"] == 1
    assert set(body) <= set(_FIXTURE["top_level"])
