"""check-auth 契约对拍（s-contract-live-check）——C端 消费侧

C端 处理的 check-auth code 闭集 {0,1,2,3} 必须被 docs/contracts 单源 fixture 覆盖；
fixture 本身必须可解析且 code 闭集自洽。
"""

import json
from pathlib import Path

_FIXTURE_PATH = (
    Path(__file__).parents[3] / "docs" / "contracts" / "check-auth.example.json"
)


def test_fixture_covers_client_handled_codes():
    fixture = json.loads(_FIXTURE_PATH.read_text())
    # C端 设备轮询/auth heal 处理的全部 code：0=已授权 1=未授权/已注销 2=注销进行中 3=客户端过期
    assert {"0", "1", "2", "3"} <= set(fixture["codes"])


def test_fixture_top_level_contract_present():
    fixture = json.loads(_FIXTURE_PATH.read_text())
    assert fixture["top_level"]["code"].startswith("int")
    assert "msg" in fixture["top_level"] and "data" in fixture["top_level"]
