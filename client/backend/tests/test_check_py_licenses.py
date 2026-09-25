"""check_py_licenses 门禁解析逻辑的单测（relicense-proprietary）。

只测 extract/parse/normalize 的纯函数面——`main()` 扫的是运行环境，不在单测面
（门禁语义由 CI step 在干净 venv 上真跑；本地全量 venv 必红属预期，见脚本 docstring）。
"""

from email.message import Message

import pytest

from scripts.check_py_licenses import check, extract_licenses, parse_tokens


def _meta(**kw) -> Message:
    """email.message.Message＝importlib.metadata.PackageMetadata 的实际载体
    （3.12 里 PackageMetadata 是 Protocol 不能实例化）。"""
    m = Message()
    for k, v in kw.items():
        m[k] = v
    return m


def test_pep639_expression_only():
    """主流包现状：License=None，仅 License-Expression（PEP 639）。"""
    m = _meta(**{"License-Expression": "MIT"})
    assert extract_licenses(m) == ["MIT"]


def test_classifier_only():
    """aiosqlite 现状：只有 classifier 行。"""
    m = _meta(Classifier="License :: OSI Approved :: MIT License")
    assert extract_licenses(m) == ["MIT License"]


def test_free_text_license_normalized():
    """distro/uvloop 现状：License 为自由文本。"""
    assert parse_tokens("Apache License, Version 2.0") == ["Apache-2.0"]
    assert parse_tokens("MIT License") == ["MIT"]
    assert parse_tokens("MIT License") == ["MIT"]


def test_or_expression_any_bad_is_red():
    assert parse_tokens("MIT OR Apache-2.0") == ["MIT", "Apache-2.0"]
    assert parse_tokens("Apache-2.0 OR BSD-3-Clause") == ["Apache-2.0", "BSD-3-Clause"]
    # OR 任一不在白名单即红（保守方向）
    meta = {"pkg": _meta(**{"License-Expression": "MIT OR GPL-3.0-only"})}
    assert check(meta) != []


def test_and_expression_all_must_pass():
    assert parse_tokens("MIT AND Apache-2.0") == ["MIT", "Apache-2.0"]
    meta = {"pkg": _meta(**{"License-Expression": "MIT AND CC-BY-4.0"})}
    assert check(meta) == []


def test_gpl_stub_red():
    meta = {"pkg": _meta(**{"License-Expression": "GPL-3.0-only"})}
    assert check(meta) != []


def test_missing_metadata_red():
    assert check({"pkg": _meta()}) == ["pkg: license 元数据缺失（三级均无）"]


def test_gate_green_for_whitelisted_mix():
    meta = {
        "a": _meta(**{"License-Expression": "MIT"}),
        "b": _meta(License="Apache License, Version 2.0"),
        "c": _meta(Classifier="License :: OSI Approved :: BSD License"),
        "d": _meta(**{"License-Expression": "MIT OR BSD-3-Clause"}),
    }
    assert check(meta) == []


@pytest.mark.parametrize(
    "bad",
    ["GPL-3.0", "AGPL-3.0-only", "SSPL-1.0", "UNLICENSED", "UNKNOWN", "LGPL-3.0"],
)
def test_copyleft_family_all_red(bad):
    meta = {"pkg": _meta(**{"License-Expression": bad})}
    assert check(meta) != []
